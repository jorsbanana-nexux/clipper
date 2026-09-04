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

    groups: list[list[dict]] = []
    cur: list[dict] = []
    cur_text = ""
    for w, c in cleaned:
        candidate = (cur_text + " " + c).strip()
        if _lines_for(candidate) > max_lines:
            # would overflow the line budget -> close current cue and start new
            if cur:
                groups.append(cur)
            cur = [w]
            cur_text = c
            continue
        cur.append(w)
        cur_text = candidate
        dur = cur[-1]["end"] - cur[0]["start"]
        if len(cur) >= max_words and dur >= min_dur:
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


def words_to_ass(words: list[dict], width: int, height: int, mode: str = "single",
                 style: str = "mrbeast") -> str:
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
        margin_v = int(height * 0.34)

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
        f"&H00000000,{back_col},-1,0,0,0,100,100,0,0,1,{outline},{shadow},2,{margin_lr},{margin_lr},{margin_v},1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    groups = _build_groups(words, width, height, p)
    tag_fn = _karaoke_tags if p.get("karaoke") else _pop_tags
    out = [header]
    for group in groups:
        start = group[0]["start"]
        end = group[-1]["end"]
        parts = []
        for i, w in enumerate(group):
            cleaned = _clean_word(w["word"])
            if not cleaned:
                continue
            if uppercase:
                cleaned = cleaned.upper()
            next_start = group[i + 1]["start"] if i + 1 < len(group) else None
            parts.append(f"{tag_fn(w, start, p, next_start)}{cleaned}")
        if not parts:
            continue
        text = " ".join(parts)
        out.append(f"Dialogue: 0,{_fmt_ts(start)},{_fmt_ts(end)},Word,,0,0,0,,{text}")

    return "\n".join(out) + "\n"
