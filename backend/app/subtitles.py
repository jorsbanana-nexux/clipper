"""ASS subtitle generation — Mr Beast style word-by-word karaoke + pop animation.

Design goals (editor-aware, viewer-focused):
- Big, ultra-bold, high-contrast text (thick dark outline + shadow) so it stays
  readable over any busy or facial background — no need to carefully avoid faces.
- Word-by-word karaoke fill (`\\kf`): the ACTIVE (being-spoken) word fills with an
  accent colour while the rest stay white.
- Per-word scale POP (`\\t \\fscx/\\fscy`): the active word scales up then back,
  the "punchy" Mr Beast feel that makes text glanceable on rewatch.
- Auto-fit: text is grouped so it never exceeds MAX_SUBTITLE_LINES (2) lines.
- Positioning is layout-aware: `mode="duo"` lifts text into the safe center zone
  so it sits between the two split-screen faces instead of over the lower one.
"""
import os
import re
from pathlib import Path

from . import config

# Sentence punctuation stripped from words so captions look clean and efficient.
# Internal apostrophes are kept so contractions like "don't" stay readable.
_PUNCT = re.compile(r"[.,!?;:…—–\u2026]+")
_WORD_CHARS = r"\w'’"


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
    """STRICT Mr Beast style: subtitle text is 100% clean.

    ALL punctuation is removed — periods, commas, question marks, apostrophes,
    dashes, everything. Only letters/digits survive ("don't" -> "dont",
    "viral!" -> "viral", "so..." -> "so").
    """
    return re.sub(r"[^\w]", "", word, flags=re.UNICODE)


def _max_chars_per_line(width: int, font_size: int) -> int:
    safe = int(width * 0.92)
    per_char = max(4.0, font_size * 0.52)
    return max(4, int(safe / per_char))


def _build_groups(words: list[dict], width: int, height: int) -> list[list[dict]]:
    """Group words into short cues (Mr Beast style, ~MAX_SUBTITLE_WORDS words).

    Pacing rules (viewer-friendly, adapts to speech speed):
    - Target ~MAX_SUBTITLE_WORDS (2) words per cue by default.
    - But a cue must stay on screen at least MIN_SUBTITLE_DUR seconds. When a
      speaker talks FAST (so 2 words would flash by too quickly / feel chaotic),
      we keep joining words into the SAME cue until it meets the minimum duration
      (capped at MAX_SUBTITLE_WORDS_OVERFLOW). When they talk SLOWLY, 2 words
      naturally sit longer — calm, not rushed.
    - Also respects MAX_SUBTITLE_LINES (never wraps into a wall of text).
    """
    size = config.SUBTITLE_SIZE
    budget = _max_chars_per_line(width, size)
    max_lines = max(1, config.MAX_SUBTITLE_LINES)
    max_words = max(1, config.MAX_SUBTITLE_WORDS)
    min_dur = max(0.0, config.MIN_SUBTITLE_DUR)
    overflow = max(max_words, config.MAX_SUBTITLE_WORDS_OVERFLOW)

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


def _word_tags(w: dict, line_start: float) -> str:
    """Per-word Mr Beast animation: colour flash + bounce (100->120->95->100).

    STRICT spec:
    - Every word renders WHITE with the style's thick black stroke. ONLY the
      word being spoken flashes to the accent colour, then returns to white
      the moment the word ends. (The old \\kf karaoke kept spoken words
      coloured forever — not the Mr Beast look.)
    - Scale bounce synchronised per word: jump to 120% as the word starts,
      dip to 95%, settle back to 100% exactly when the word ends.
    All \\t() times are MILLISECONDS relative to the cue (Dialogue) start.
    """
    peak = int(round(max(1.0, float(getattr(config, "SUBTITLE_POP", 1.20))) * 100))
    dip = int(round(min(1.0, max(0.5, float(getattr(config, "SUBTITLE_DIP", 0.95)))) * 100))
    ms0 = max(0, int(round((w["start"] - line_start) * 1000)))
    ms1 = max(ms0 + 40, int(round((w["end"] - line_start) * 1000)))
    span = ms1 - ms0
    t40 = ms0 + int(span * 0.4)
    t75 = ms0 + int(span * 0.75)
    pop_col = config.SUBTITLE_POP_COLOR
    base_col = config.SUBTITLE_BASE_COLOR
    # 40ms colour ramps read as instant on a phone but never flicker.
    return (
        f"{{\\t({ms0},{t40},\\fscx{peak}\\fscy{peak})"
        f"\\t({t40},{t75},\\fscx{dip}\\fscy{dip})"
        f"\\t({t75},{ms1},\\fscx100\\fscy100)"
        f"\\t({ms0},{ms0 + 40},\\c{pop_col})"
        f"\\t({ms1},{ms1 + 40},\\c{base_col})}}"
    )


def words_to_ass(words: list[dict], width: int, height: int, mode: str = "single") -> str:
    font = _resolve_font(config.SUBTITLE_FONT)
    size = config.SUBTITLE_SIZE

    fontdir_line = ""
    if config.FONT_DIR and os.path.isdir(config.FONT_DIR):
        fontdir_line = f"fontsdir: {config.FONT_DIR}\n"

    base_col = config.SUBTITLE_BASE_COLOR   # white — words not yet spoken
    pop_col = config.SUBTITLE_POP_COLOR     # accent — the word being spoken
    back_col = config.SUBTITLE_BACK_COLOR
    outline = config.SUBTITLE_OUTLINE
    shadow = config.SUBTITLE_SHADOW
    margin_lr = int(width * 0.03)

    # Layout-aware vertical position (editor/audience perspective):
    # - single: face sits in the upper area (headroom), so bottom ~13% is clear.
    # - duo:    faces occupy top & bottom bands; lift text into the center seam
    #           so it reads between the two speakers instead of over the lower one.
    # STRICT Mr Beast placement: max 2 lines centred on the screen (never
    # glued to the bottom edge). With \an2 (bottom-centre) this MarginV lifts
    # the text block so it sits in the middle of the screen, below the face.
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

    groups = _build_groups(words, width, height)
    out = [header]
    for group in groups:
        start = group[0]["start"]
        end = group[-1]["end"]
        parts = []
        for w in group:
            cleaned = _clean_word(w["word"])
            if not cleaned:
                continue
            parts.append(f"{_word_tags(w, start)}{cleaned}")
        if not parts:
            continue
        text = " ".join(parts)
        out.append(f"Dialogue: 0,{_fmt_ts(start)},{_fmt_ts(end)},Word,,0,0,0,,{text}")

    return "\n".join(out) + "\n"
