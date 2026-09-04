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


def layout_timeline(turns: list[dict], start: float, end: float,
                    lead: float = 2.5, min_solo: float = 5.0) -> list[dict]:
    """Time-segmented layout plan covering [start, end], for in-clip switching.

    Behaviour (per spec):
    - A clip with <2 distinct speakers is solo the whole way.
    - Otherwise, once a 2nd speaker is heard, the screen is SPLIT (duo) — the
      split appears `lead` seconds BEFORE the 2nd speaker talks (timely, never
      late), and stays duo through the exchange.
    - If a speaker is alone again for longer than `min_solo`, the duo closes
      back to solo.

    Returns [{start, end, layout}] ordered and contiguous.
    """
    if not turns:
        return [{"start": start, "end": end, "layout": LAYOUT_SINGLE}]

    distinct = {t.get("speaker", "?") for t in turns if t.get("start") is not None}
    if len(distinct) < 2:
        return [{"start": start, "end": end, "layout": LAYOUT_SINGLE}]

    # Segment by every turn boundary.
    boundaries = {start, end}
    for t in turns:
        boundaries.add(max(start, min(end, t.get("start", start))))
        boundaries.add(max(start, min(end, t.get("end", end))))
    pts = sorted(boundaries)
    base: list[list] = []
    for a, b in zip(pts, pts[1:]):
        if b - a < 1e-6:
            continue
        mid = (a + b) / 2
        active = speakers_in_window(turns, mid - 1e-9, mid + 1e-9)
        base.append([a, b, len(active)])  # count of active speakers

    # Seen-based duo: once 2 distinct speakers have appeared, it's a conversation
    # -> duo (timely, since it triggers exactly when the 2nd speaker starts).
    seen: set = set()
    plan: list[list] = []
    for a, b, n in base:
        mid = (a + b) / 2
        active = speakers_in_window(turns, mid - 1e-9, mid + 1e-9)
        seen.update(active)
        layout = LAYOUT_DUO if len(seen) >= 2 else LAYOUT_SINGLE
        plan.append([a, b, layout])

    # Pull every DUO segment's start back by `lead` so the split appears before
    # the 2nd speaker actually starts.
    for s in plan:
        if s[2] == LAYOUT_DUO:
            s[0] = max(start, s[0] - lead)

    # Rebuild contiguous (DUO wins over an adjacent SINGLE it was extended into).
    merged: list[list] = []
    for a, b, c in plan:
        if not merged:
            merged.append([a, b, c])
            continue
        last = merged[-1]
        if a < last[1]:
            if c == LAYOUT_DUO:
                last[1] = a
                merged.append([a, b, c])
            else:
                a = last[1]
                if b > a:
                    merged.append([a, b, c])
        else:
            merged.append([a, b, c])

    # Close duo back to solo when one speaker is alone for too long.
    final: list[list] = []
    for a, b, c in merged:
        if c == LAYOUT_DUO and (b - a) >= min_solo:
            mid = (a + b) / 2
            active = speakers_in_window(turns, mid - 1e-9, mid + 1e-9)
            if len(active) < 2:
                c = LAYOUT_SINGLE
        final.append([a, b, c])

    result = [{"start": a, "end": b, "layout": c} for a, b, c in final if b > a]
    if not result:
        result = [{"start": start, "end": end, "layout": LAYOUT_SINGLE}]
    return result
