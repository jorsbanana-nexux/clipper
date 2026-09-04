"""ASS subtitle generation — word-by-word karaoke styles + preset engine.

Design goals (editor-aware, viewer-focused):
- Big, ultra-bold, high-contrast text (thick dark outline + shadow) so it stays
  readable over any busy or facial background — no need to carefully avoid faces.
- Word-by-word animation: the ACTIVE (being-spoken) word pops (scale bounce +
  colour flash) while the rest stay white — the Mr Beast feel. The `karaoke`
  preset instead keeps spoken words filled (progressive \\kf fill).
- v0.3 STYLE PRESETS: mrbeast | hormozi | minimal | karaoke | none — selected
  per job (ClipRequest.subtitle_style). Answers the "no creative control"
  complaint every clipper platform gets.
- Auto-fit: text is grouped so it never exceeds MAX_SUBTITLE_LINES (2) lines.
- Positioning is layout-aware: `mode="duo"` lifts text into the safe center zone
  so it sits between the two split-screen faces instead of over the lower one.
"""
import os
import re
from pathlib import Path

from . import config

# Sentence punctuation stripped from words so captions look clean and efficient.
_PUNCT = re.compile(r"[.,!?;:…—–\u2026]+")


def _fmt_ts(seconds: float) -> str:
    cs = int(round(seconds * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _resolve_font(font_name: str) -> str:
    """Return the font family name to use in ASS. If config.SUBTITLE_FONT is an
    exact filename in config.FONT_DIR, prefer its stem (matches the font's own
    family name registered at render time)."""
    if config.FONT_DIR and font_name:
        d = Path(config.FONT_DIR)
        if d.exists():
            for cand in d.iterdir():
                if cand.suffix.lower() in (".ttf", ".otf") and cand.stem.lower() == font_name.lower():
                    return cand.stem
    return font_name


def _clean_word(word: str) -> str:
    """STRICT clean style: subtitle text is 100% clean.

    ALL punctuation is removed — periods, commas, question marks, apostrophes,
    dashes, everything. Only letters/digits survive ("don't" -> "dont",
    "viral!" -> "viral", "so..." -> "so").
    """
    return re.sub(r"[^\w]", "", word, flags=re.UNICODE)


def _max_chars_per_line(width: int, font_size: int) -> int:
    safe = int(width * 0.92)
    per_char = max(4.0, font_size * 0.52)
    return max(4, int(safe / per_char))


def _build_groups(words: list[dict], width: int, height: int, p: dict) -> list[list[dict]]:
    """Group words into short cues, driven by the preset's pacing knobs.

    Pacing rules (viewer-friendly, adapts to speech speed):
    - Target ~p["words"] words per cue by default.
    - But a cue must stay on screen at least p["min_dur"] seconds. When a
      speaker talks FAST (so the target word count would flash by too quickly),
      we keep joining words into the SAME cue until it meets the minimum duration
      (capped at p["overflow"]). When they talk SLOWLY, fewer words sit longer —
      calm, not rushed.
    - Also respects MAX_SUBTITLE_LINES (never wraps into a wall of text).
    """
    size = p["size"]
    budget = _max_chars_per_line(width, size)
    max_lines = max(1, config.MAX_SUBTITLE_LINES)
    max_words = max(1, p["words"])
    min_dur = max(0.0, p["min_dur"])
    overflow = max(max_words, p["overflow"])

    def _lines_for(text: str) -> int:
        if not text:
            return 0
        return max(1, -(-len(text) // budget))

    cleaned = [(w, _clean_word(w["word"])) for w in words]
    cleaned = [(w, c) for w, c in cleaned if c]
    if not cleaned:
        return []

    # Sentence-aware cues (viewer perspective): a cue NEVER mixes sentences.
    # When a word ends with sentence-final punctuation the cue closes right
    # after it, so each caption block reads as 1 clean, complete thought
    # ("cukup 2 kalimat, bersih, tidak banyak") instead of splicing the tail
    # of one sentence onto the head of the next.
    sent_end = re.compile(r"[.!?…]+$")

    groups: list[list[dict]] = []
    cur: list[dict] = []
    cur_text = ""
    for w, c in cleaned:
        sentence_done = bool(sent_end.search(w["word"].strip()))
        candidate = (cur_text + " " + c).strip()
        if _lines_for(candidate) > max_lines:
            # would overflow the line budget -> close current cue and start new
            if cur:
                groups.append(cur)
            cur = [w]
            cur_text = c
            if sentence_done:
                groups.append(cur)
                cur = []
                cur_text = ""
            continue
        cur.append(w)
        cur_text = candidate
        dur = cur[-1]["end"] - cur[0]["start"]
        if sentence_done or len(cur) >= max_words and dur >= min_dur:
            groups.append(cur)
            cur = []
            cur_text = ""
        elif len(cur) >= overflow:
            groups.append(cur)
            cur = []
            cur_text = ""
    if cur:
        groups.append(cur)
    return groups


def _pop_tags(w: dict, line_start: float, p: dict, next_start: float | None = None) -> str:
    """Per-word pop animation: colour flash + bounce (100->POP->DIP->100).

    STRICT spec:
    - Every word renders WHITE with the style's thick black stroke. ONLY the
      word being spoken flashes to the accent colour, then returns to white
      the moment the word ends.
    - Scale bounce synchronised per word, settling back to 100% exactly when
      the word ends.
    All \\t() times are MILLISECONDS relative to the cue (Dialogue) start.
    """
    peak = int(round(max(1.0, float(p.get("pop", 1.20))) * 100))
    dip = int(round(min(1.0, max(0.5, float(p.get("dip", 0.95)))) * 100))
    ms0 = max(0, int(round((w["start"] - line_start) * 1000)))
    ms1 = max(ms0 + 40, int(round((w["end"] - line_start) * 1000)))
    # BUGFIX v0.3.3 ("warna biru menyeret/smear ke kanan"): Whisper word
    # timestamps can be tight or slightly overlapping on fast speech, so this
    # word's colour-fade-back-to-white window could still be running when the
    # NEXT word's own pop-to-blue window starts -> two words read as tinted
    # at once, which looks exactly like a colour smear dragging rightward.
    # Clamp: this word must be back to white before the next one starts.
    if next_start is not None:
        next_ms0 = int(round((next_start - line_start) * 1000))
        ms1 = min(ms1, max(ms0 + 40, next_ms0))
    span = ms1 - ms0
    t40 = ms0 + int(span * 0.4)
    t75 = ms0 + int(span * 0.75)
    pop_col = p["pop_color"]
    base_col = p["base_color"]
    # 40ms colour ramps read as instant on a phone but never flicker.
    return (
        f"{{\\t({ms0},{t40},\\fscx{peak}\\fscy{peak})"
        f"\\t({t40},{t75},\\fscx{dip}\\fscy{dip})"
        f"\\t({t75},{ms1},\\fscx100\\fscy100)"
        f"\\t({ms0},{ms0 + 40},\\c{pop_col})"
        f"\\t({ms1},{ms1 + 40},\\c{base_col})}}"
    )


def _karaoke_tags(w: dict, line_start: float, p: dict, next_start: float | None = None) -> str:
    """Progressive-fill karaoke: spoken words STAY highlighted (\\kf).

    The cue's SecondaryColour is the fill colour; \\kf fills the word over its
    spoken duration, so words stay highlighted once spoken (classic karaoke).
    """
    fill_end = next_start if (next_start is not None and next_start > w["end"]) else w["end"]
    dur_ms = max(20, int(round((fill_end - w["start"]) * 1000)))
    delay_ms = max(0, int(round((w["start"] - line_start) * 1000)))
    peak = int(round(max(1.0, float(p.get("pop", 1.10))) * 100))
    return f"{{\\kf{dur_ms}\\t({delay_ms},{delay_ms + 40},\\fscx{peak}\\fscy{peak})}}"



# ============================ v0.4 SUPERCLIP LAYER ============================
# Hook title overlay + animated progress bar — the retention visuals every
# commercial clipper charges for, generated as plain ASS (still ONE encode).

_HOOK_SAFE_TOP = 0.085   # hook text baseline (fraction of height) — below the
                         # platform UI strip, above faces at headroom.
_BAR_MARGIN = 0.050      # progress bar side margins (fraction of width)
_BAR_H = 10              # progress bar thickness (px @ PlayResY)


def _hook_events(hook_text: str, duration: float, width: int, height: int,
                 p: dict, font: str) -> list[str]:
    """Dialogue events for the top HOOK title: pops in, holds ~3.5s, fades out.

    Reads as a poster headline: big, bold, max 2 lines, thick outline, no
    punctuation (consistent with the strict caption style).
    """
    raw = (hook_text or "").strip()
    if not raw:
        return []
    text = re.sub(r"\s+", " ", raw)
    text = re.sub(r"[.!?…]+$", "", text).strip()
    if p.get("uppercase", False):
        text = text.upper()
    size = min(84, max(56, int(p.get("size", 100) * 0.60)))
    budget = max(8, int((width * 0.9) / (size * 0.52)))
    words = text.split()
    lines, cur = [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > budget:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
        if len(lines) == 2:
            break
    if cur and len(lines) < 2:
        lines.append(cur)
    text = "\\N".join(l for l in lines if l)
    if not text:
        return []
    show = min(3.8, max(2.2, duration * 0.5))
    fad_ms = 160
    return [(
        f"Dialogue: 1,{_fmt_ts(0.0)},{_fmt_ts(show)},Hook,,0,0,0,,"
        # scale pop-in 70->100% in the first 220ms + fade in/out
        f"{{\\fad({fad_ms},350)\\t(0,220,\\fscx100\\fscy100)}}"
        f"{{\\fscx70\\fscy70}}"
        f"{text}"
    )]


def _progress_bar_events(duration: float, width: int, height: int,
                         p: dict) -> list[str]:
    """Thin accent progress bar pinned at the very top edge, filling 0->100%
    across the whole clip via an animated \\clip rectangle (libass-native,
    smooth per-frame, no stepping).

    Two stacked events: a dim track (full width, always visible) + a bright
    accent bar whose visible right edge sweeps with \\t().
    """
    if duration <= 0:
        return []
    x0 = int(width * _BAR_MARGIN)
    x1 = int(width * (1 - _BAR_MARGIN))
    y0 = int(height * 0.016)
    y1 = y0 + _BAR_H
    full_w = x1 - x0
    accent = p.get("pop_color", "&H00FFE500")
    dim = "&H50FFFFFF"
    dur_ms = int(round(duration * 1000))
    dim_event = (
        f"Dialogue: 2,{_fmt_ts(0.0)},{_fmt_ts(duration)},Bar,,0,0,0,,"
        f"{{\\an7\\pos({x0},{y0})\\1c{dim}\\3a&HFF&\\4a&HFF&\\p1}}"
        f"m 0 0 l {full_w} 0 l {full_w} {_BAR_H} l 0 {_BAR_H}{{\\p0}}"
    )
    # Animated right edge: libass does NOT interpolate \t(\clip(...)) reliably
    # (tested: the clip stays at its FINAL value). Drawings DO scale with
    # \fscx, so we animate \fscx 1->100% over the clip with \an7 (top-left
    # anchor) so the bar grows rightward — verified by pixel comparison.
    accent_event = (
        f"Dialogue: 3,{_fmt_ts(0.0)},{_fmt_ts(duration)},Bar,,0,0,0,,"
        f"{{\\an7\\pos({x0},{y0})\\1c{accent}\\3a&HFF&\\4a&HFF&"
        f"\\fscx1\\t(0,{dur_ms},\\fscx100)\\p1}}"
        f"m 0 0 l {full_w} 0 l {full_w} {_BAR_H} l 0 {_BAR_H}{{\\p0}}"
    )
    return [dim_event, accent_event]


# Emoji keyword map (Submagic-style contextual emoji). Opt-in via
# CLIPPER_EMOJI=1 — requires an emoji-capable font on the render machine.
_EMOJI_MAP = [
    (re.compile(r"\b(uang|dollar|rp|milion|milyar|money|rich|kaya|salary|gaji)\b", re.I), "💰"),
    (re.compile(r"\b(api|hot|panas|fire|viral|trending)\b", re.I), "🔥"),
    (re.compile(r"\b(cinta|sayang|love|pacar|gebetan)\b", re.I), "❤️"),
    (re.compile(r"\b(otak|pikir|brain|ide|idea|pintar|smart)\b", re.I), "🧠"),
    (re.compile(r"\b(makan|food|diet|lapar|enak)\b", re.I), "🍔"),
    (re.compile(r"\b(cepat|kilat|fast|speed|sekejap)\b", re.I), "⚡"),
    (re.compile(r"\b(mati|bahaya|danger|seram|scary|zombie)\b", re.I), "💀"),
    (re.compile(r"\b(ketawa|lucu|haha|funny)\b", re.I), "😂"),
    (re.compile(r"\b(tips|cara|langkah|step|panduan)\b", re.I), "👇"),
    (re.compile(r"\b(berat|susah|payah|hard|sulit)\b", re.I), "💪"),
    (re.compile(r"\b(dunia|world|global|indonesia)\b", re.I), "🌍"),
]


def _cue_emoji(words: list[dict]) -> str:
    for w in words:
        for rx, em in _EMOJI_MAP:
            if rx.search(w["word"]):
                return em
    return ""


def words_to_srt(words: list[dict], style: str = "minimal") -> str:
    """Grouped, readable SRT (v0.4): platform-portable captions that creators
    can import into CapCut/Premiere or upload as closed captions."""
    p = config.get_subtitle_preset(style) or {"words": 4, "min_dur": 1.0, "overflow": 7}
    groups = _build_groups(words, 1080, 1920, {"words": 4, "min_dur": 1.0,
                                              "overflow": 7, "size": 80})
    def _srt_ts(t: float) -> str:
        ms = int(round(t * 1000))
        h, ms = divmod(ms, 3600000)
        m, ms = divmod(ms, 60000)
        s, ms = divmod(ms, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
    out = []
    for i, g in enumerate(groups, 1):
        text = " ".join((w["word"] or "").strip() for w in g if (w["word"] or "").strip())
        if not text:
            continue
        out.append(f"{i}\n{_srt_ts(g[0]['start'])} --> {_srt_ts(g[-1]['end'])}\n{text}\n")
    return "\n".join(out)


def words_to_ass(words: list[dict], width: int, height: int, mode: str = "single",
                 style: str = "mrbeast", hook_text: str = "",
                 emoji: bool = False, progress_bar: bool = False,
                 clip_duration: float = 0.0) -> str:
    """Build the full ASS document for a clip.

    `style` selects a config.SUBTITLE_PRESETS preset ("none" -> empty doc so
    the render pipeline skips the burn-in entirely).
    """
    p = config.get_subtitle_preset(style)
    if not p:  # "none"
        return ""
    font = _resolve_font(p.get("font", config.SUBTITLE_FONT))
    size = p["size"]
    uppercase = bool(p.get("uppercase", False))

    fontdir_line = ""
    if config.FONT_DIR and os.path.isdir(config.FONT_DIR):
        fontdir_line = f"fontsdir: {config.FONT_DIR}\n"

    base_col = p["base_color"]
    pop_col = p["pop_color"]
    back_col = p["back_color"]
    outline = p["outline"]
    shadow = p["shadow"]
    margin_lr = int(width * 0.03)

    # Layout-aware vertical position (editor/audience perspective):
    # - single: face sits in the upper area (headroom), so bottom ~13% is clear.
    # - duo:    faces occupy top & bottom bands; lift text into the center seam
    #           so it reads between the two speakers instead of over the lower one.
    if mode == "duo":
        margin_v = int(height * 0.46)   # center seam between the two faces
    else:
        # Perspektif penonton (referensi video MrBeast + UI TikTok/Shorts):
        # teks duduk di sepertiga bawah, tepat DI ATAS zona UI platform
        # (tombol, caption, progress bar memakan ~15-20% bawah layar),
        # sekaligus tidak menutupi wajah yang berada di area atas-tengah.
        margin_v = int(height * 0.22)

    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {width}\n"
        f"PlayResY: {height}\n"
        "WrapStyle: 2\n"
        "ScaledBorderAndShadow: yes\n"
        f"{fontdir_line}\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Word,{font},{size},{base_col},{pop_col},"
        f"&H00000000,{back_col},-1,0,0,0,100,100,0,0,1,{outline},{shadow},2,{margin_lr},{margin_lr},{margin_v},1\n"
        # v0.4 overlay styles: Hook (top title) + Bar (progress bar drawing)
        f"Style: Hook,{font},{int(min(84, max(56, size * 0.60)))},{base_col},{pop_col},"
        f"&H00000000,{back_col},-1,0,0,0,100,100,0,0,1,{max(6, outline)},{shadow},8,{margin_lr},{margin_lr},{int(height * _HOOK_SAFE_TOP)},1\n"
        f"Style: Bar,{font},20,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    groups = _build_groups(words, width, height, p)
    tag_fn = _karaoke_tags if p.get("karaoke") else _pop_tags
    out = [header]
    # v0.4 SUPERCLIP overlay layer (burned in the SAME single encode)
    if config.PROGRESS_BAR and progress_bar and clip_duration > 0:
        out.extend(_progress_bar_events(clip_duration, width, height, p))
    if config.HOOK_TEXT and hook_text:
        out.extend(_hook_events(hook_text, clip_duration or 3.5, width, height, p, font))
    for group in groups:
        start = group[0]["start"]
        end = group[-1]["end"]
        # BUGFIX v0.3.1 (layar): WrapStyle=2 membuat libass TIDAK membungkus
        # otomatis — cue 11..20 karakter akan dirender SATU baris yang menembus
        # tepi layar. Solusi: hitung batas karakter per baris dari preset,
        # lalu sisipkan \N manual sebagai pemotong baris (maks 2 baris).
        budget = _max_chars_per_line(width, size)
        max_lines = max(1, config.MAX_SUBTITLE_LINES)
        parts: list[str] = []
        line_len = 0
        lines_used = 1
        for i, w in enumerate(group):
            cleaned = _clean_word(w["word"])
            if not cleaned:
                continue
            if uppercase:
                cleaned = cleaned.upper()
            next_start = group[i + 1]["start"] if i + 1 < len(group) else None
            piece = f"{tag_fn(w, start, p, next_start)}{cleaned}"
            add = len(cleaned) + (1 if line_len else 0)   # +1 = spasi antar kata
            if line_len and line_len + add > budget and lines_used < max_lines:
                parts.append("\\N")                    # pemotong baris manual
                line_len = 0
                add = len(cleaned)
                lines_used += 1
            parts.append(piece)
            line_len += add
        if not parts:
            continue
        text = " ".join(parts)
        if emoji:
            em = _cue_emoji(group)
            if em:
                text = f"{text} {em}"
        out.append(f"Dialogue: 0,{_fmt_ts(start)},{_fmt_ts(end)},Word,,0,0,0,,{text}")

    return "\n".join(out) + "\n"
