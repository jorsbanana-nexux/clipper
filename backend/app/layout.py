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
    - Once 2 distinct speakers have been heard (conversation started), the
      screen is SPLIT (duo). The split appears `lead` seconds BEFORE the 2nd
      speaker actually starts (timely, never late) and stays duo through the
      back-and-forth.
    - If one speaker is alone (or nobody) for `min_solo`+ seconds, the duo
      closes back to solo; it re-opens (with `lead` pre-roll) when a 2nd
      speaker speaks again.

    Returns [{start, end, layout}] ordered and contiguous.
    """
    if not turns:
        return [{"start": start, "end": end, "layout": LAYOUT_SINGLE}]
    distinct = {t.get("speaker", "?") for t in turns if t.get("start") is not None}
    if len(distinct) < 2:
        return [{"start": start, "end": end, "layout": LAYOUT_SINGLE}]

    # --- boundary grid from every turn edge ---
    boundaries = {start, end}
    for t in turns:
        boundaries.add(max(start, min(end, t.get("start", start))))
        boundaries.add(max(start, min(end, t.get("end", end))))
    pts = sorted(boundaries)
    intervals: list[list] = []
    for a, b in zip(pts, pts[1:]):
        if b - a < 1e-6:
            continue
        mid = (a + b) / 2
        active = speakers_in_window(turns, mid - 1e-9, mid + 1e-9)
        intervals.append([a, b, active])

    # --- assign layout per interval ---
    # Before the 2nd distinct speaker appears: solo. After: duo, EXCEPT we close
    # back to solo when a solo-only (or silent) run reaches `min_solo`.
    layout_by_iv: list[list] = []
    seen: set = set()
    solo_run = 0.0
    for a, b, active in intervals:
        seen |= set(active)
        seen_duo = len(seen) >= 2
        n = len(active)
        if not seen_duo:
            layout = LAYOUT_SINGLE
            solo_run = 0.0
        elif n >= 2:
            solo_run = 0.0
            layout = LAYOUT_DUO
        else:
            solo_run += (b - a)
            layout = LAYOUT_SINGLE if solo_run >= min_solo else LAYOUT_DUO
        layout_by_iv.append([a, b, layout])

    # --- coalesce contiguous same-layout runs ---
    runs: list[list] = []
    for a, b, c in layout_by_iv:
        if b <= a:
            continue
        if runs and runs[-1][2] == c:
            runs[-1][1] = b
        else:
            runs.append([a, b, c])

    # --- apply lead to the START of each duo run (never before clip start) ---
    # Pulling the split back by `lead` makes it appear BEFORE the 2nd speaker
    # actually starts. A duo run follows a single run, so pulling it back cuts
    # into that single run; overlap is resolved below (duo wins).
    for r in runs:
        if r[2] == LAYOUT_DUO:
            r[0] = max(start, r[0] - lead)

    # --- resolve overlaps, duo wins; drop empty segments ---
    resolved: list[list] = []
    for a, b, c in runs:
        if b <= a:
            continue
        if not resolved:
            resolved.append([a, b, c])
            continue
        last = resolved[-1]
        if a < last[1]:
            if c == LAYOUT_DUO:
                last[1] = a
                resolved.append([a, b, c])
            else:
                a = last[1]
                if b > a:
                    resolved.append([a, b, c])
        else:
            resolved.append([a, b, c])

    # --- coalesce again (drop any emptied segments) ---
    final: list[list] = []
    for a, b, c in resolved:
        if b <= a:
            continue
        if final and final[-1][2] == c:
            final[-1][1] = b
        else:
            final.append([a, b, c])

    result = [{"start": a, "end": b, "layout": c} for a, b, c in final]
    if not result:
        result = [{"start": start, "end": end, "layout": LAYOUT_SINGLE}]
    return result
