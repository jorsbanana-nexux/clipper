"""Layout engine: single / duo / share templates + dynamic switching (v0.2).

Template semantics:
- "single": one speaker, crop-follow the active face (existing v0.1 behavior).
- "duo":   two speakers, split-screen (two stacked horizontal bands).
- "share": screen-share focus (reserved; falls back to single for now).

Dynamic switching = the layout can change over time within a clip. v0.2 renders
ONE template per clip (chosen from diarization); finer in-clip switching is the
documented B5 step and uses layout_timeline().
"""
LAYOUT_SINGLE = "single"
LAYOUT_DUO = "duo"
LAYOUT_SHARE = "share"


def speakers_in_window(turns: list[dict], start: float, end: float) -> list[str]:
    """Unique speaker labels active within the [start, end] window."""
    active = set()
    for t in turns or []:
        s = t.get("start", 0.0)
        e = t.get("end", 0.0)
        if e >= start and s <= end:
            active.add(t.get("speaker", "SPEAKER_0"))
    return sorted(active)


def choose_template(turns: list[dict], start: float, end: float) -> str:
    """Pick a layout for a clip window [start, end]."""
    spk = speakers_in_window(turns, start, end)
    if len(spk) >= 2:
        return LAYOUT_DUO
    return LAYOUT_SINGLE


def layout_timeline(turns: list[dict], start: float, end: float) -> list[dict]:
    """Time-segmented layout plan covering [start, end], for in-clip switching.

    Returns [{start, end, layout}] ordered. Used by B5; v0.2 renders per-clip.
    """
    boundaries = {start, end}
    for t in turns or []:
        s = max(start, min(end, t.get("start", start)))
        e = max(start, min(end, t.get("end", end)))
        boundaries.add(s)
        boundaries.add(e)
    pts = sorted(boundaries)
    segs = []
    for a, b in zip(pts, pts[1:]):
        if b - a < 1e-6:
            continue
        mid = (a + b) / 2
        spk = speakers_in_window(turns, mid - 1e-9, mid + 1e-9)
        layout = LAYOUT_DUO if len(spk) >= 2 else LAYOUT_SINGLE
        segs.append({"start": a, "end": b, "layout": layout})
    return segs
