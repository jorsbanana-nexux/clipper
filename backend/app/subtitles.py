"""ASS subtitle generation with word-by-word (karaoke) highlighting.

A2 (Fase A): if config.FONT_DIR is set, the ASS script includes a `fontsdir`
line so ffmpeg encodes with the bundled font instead of silently falling back
to a system default (which can render incorrectly or look different).
"""
import os
from pathlib import Path

from . import config


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


def words_to_ass(words: list[dict], width: int, height: int) -> str:
    font = _resolve_font(config.SUBTITLE_FONT)
    size = config.SUBTITLE_SIZE

    fontdir_line = ""
    if config.FONT_DIR and os.path.isdir(config.FONT_DIR):
        fontdir_line = f"fontsdir: {config.FONT_DIR}\n"

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
        f"Style: Word,{font},{size},&H0030D6FF,&H00FFFFFF,"
        "&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,0,2,30,30,300,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    lines = []
    chunk = []
    CHUNK = 4
    for w in words:
        chunk.append(w)
        if len(chunk) >= CHUNK:
            lines.append(chunk)
            chunk = []
    if chunk:
        lines.append(chunk)

    out = [header]
    for group in lines:
        start = group[0]["start"]
        end = group[-1]["end"]
        total_cs = max(1, int(round((end - start) * 100)))
        dur_total = max(1e-6, sum(max(0.0, w["end"] - w["start"]) for w in group))
        parts = []
        for w in group:
            d = max(0.02, w["end"] - w["start"])
            k = max(1, int(round((d / dur_total) * total_cs)))
            parts.append(f"{{\\k{k}}}{w['word']}")
        text = " ".join(parts)
        out.append(f"Dialogue: 0,{_fmt_ts(start)},{_fmt_ts(end)},Word,,0,0,0,,{text}")

    return "\n".join(out) + "\n"
