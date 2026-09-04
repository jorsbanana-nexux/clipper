"""ASS subtitle generation with word-by-word (karaoke) highlighting.

A2 (Fase A): if config.FONT_DIR is set, the ASS script includes a `fontsdir`
line so ffmpeg encodes with the bundled font instead of silently falling back
to a system default (which can render incorrectly or look different).
"""
import os
import re
from pathlib import Path

from . import config

# Sentence punctuation stripped from words so captions look clean and efficient
# (per spec: remove all commas/periods). Internal apostrophes are kept so
# contractions like "don't" stay readable.
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
                    # Use the file stem as the family for reliable matching.
                    return cand.stem
    return font_name


def _clean_word(word: str) -> str:
    """Remove sentence punctuation from a word (keep internal apostrophes).
    Strips ALL leading/trailing non-word chars, not just one."""
    w = _PUNCT.sub("", word)
    w = re.sub(rf"^[{_WORD_CHARS}]*[^\w'’]+", "", w)
    w = re.sub(rf"[^\w'’]+[{_WORD_CHARS}]*$", "", w)
    return w


def _max_chars_per_line(width: int, font_size: int) -> int:
    """Rough glyph budget per line. Average glyph width ~0.52 * font size;
    cap at 92% of the safe area so text never touches the edges."""
    safe = int(width * 0.92)
    per_char = max(4.0, font_size * 0.52)
    return max(4, int(safe / per_char))


def _build_groups(words: list[dict], width: int, height: int) -> list[list[dict]]:
    """Group words so each displayed group fits in at most MAX_SUBTITLE_LINES
    lines. Greedy: add a word if the resulting text still fits; otherwise start
    a new group. This guarantees text never exceeds the allowed line count."""
    size = config.SUBTITLE_SIZE
    budget = _max_chars_per_line(width, size)
    max_lines = max(1, config.MAX_SUBTITLE_LINES)

    def _lines_for(text: str) -> int:
        if not text:
            return 0
        return max(1, -(-len(text) // budget))

    groups: list[list[dict]] = []
    cur: list[dict] = []
    cur_text = ""
    for w in words:
        cleaned = _clean_word(w["word"])
        if not cleaned:
            continue
        candidate = (cur_text + " " + cleaned).strip()
        if _lines_for(candidate) <= max_lines:
            cur.append(w)
            cur_text = candidate
        else:
            if cur:
                groups.append(cur)
            cur = [w]
            cur_text = cleaned
    if cur:
        groups.append(cur)
    return groups


def words_to_ass(words: list[dict], width: int, height: int) -> str:
    font = _resolve_font(config.SUBTITLE_FONT)
    size = config.SUBTITLE_SIZE

    fontdir_line = ""
    if config.FONT_DIR and os.path.isdir(config.FONT_DIR):
        fontdir_line = f"fontsdir: {config.FONT_DIR}\n"

    base_col = config.SUBTITLE_BASE_COLOR   # white — words not yet spoken
    pop_col = config.SUBTITLE_POP_COLOR     # accent — the word being spoken
    back_col = config.SUBTITLE_BACK_COLOR
    outline = config.SUBTITLE_OUTLINE
    margin_v = int(height * 0.16)  # ~16% from bottom = clear of like/comment UI
    margin_lr = int(width * 0.03)

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
        f"&H00000000,{back_col},-1,0,0,0,100,100,0,0,1,{outline},2,2,{margin_lr},{margin_lr},{margin_v},1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    groups = _build_groups(words, width, height)
    out = [header]
    for group in groups:
        start = group[0]["start"]
        end = group[-1]["end"]
        total_cs = max(1, int(round((end - start) * 100)))
        dur_total = max(1e-6, sum(max(0.0, w["end"] - w["start"]) for w in group))
        parts = []
        for w in group:
            d = max(0.02, w["end"] - w["start"])
            # \kf = karaoke fade: the active word smoothly fades to the pop
            # colour, driven by the word's real duration (accurate sync).
            k = max(1, int(round((d / dur_total) * total_cs)))
            parts.append(f"{{\\kf{k}}}{_clean_word(w['word'])}")
        text = " ".join(parts)
        out.append(f"Dialogue: 0,{_fmt_ts(start)},{_fmt_ts(end)},Word,,0,0,0,,{text}")

    return "\n".join(out) + "\n"
