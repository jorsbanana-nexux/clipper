"""Viral-moment detection: GPT analyses the transcript and picks the best clips."""
from textwrap import dedent

from openai import OpenAI

from . import config
from .models import HighlightAnalysis


def _format_segments(segments: list[dict], limit: int = 200) -> str:
    lines = []
    for s in segments[:limit]:
        start = s.get("start", 0.0)
        text = (s.get("text") or "").strip().replace("\n", " ")
        lines.append(f"[{start:7.2f}s] {text}")
    return "\n".join(lines)


def find_viral_moments(transcript_text, segments, max_clips, min_dur, max_dur) -> HighlightAnalysis:
    if not config.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set. Provide it via environment.")

    prompt = dedent("""
        You are an elite short-form video editor. Given a podcast transcript with
        timestamps, pick the {max_clips} most viral-worthy, emotionally engaging
        moments that would make people rewatch and share.

        Rules:
        - Each clip must be {min_dur}-{max_dur} seconds and capture ONE complete thought.
        - Prefer: strong hooks, surprising claims, quotable lines, emotional peaks,
          concrete tips, conflicts, or payoffs.
        - Use the exact timestamps from the transcript. Never invent times.
        - Avoid overlaps between clips.
        - Return them ranked by viral potential (best first).

        Transcript segments (start time in seconds, then text):
        {segments}
    """).format(max_clips=max_clips, min_dur=int(min_dur), max_dur=int(max_dur), segments=_format_segments(segments))

    client = OpenAI(api_key=config.OPENAI_API_KEY)
    resp = client.beta.chat.completions.parse(
        model=config.ANALYSIS_MODEL,
        messages=[
            {"role": "system", "content": "You are an expert short-form video editor."},
            {"role": "user", "content": prompt},
        ],
        response_format=HighlightAnalysis,
        reasoning_effort="minimal",
    )
    result = resp.choices[0].message.parsed
    if result is None:
        raise RuntimeError("AI analysis returned an incomplete response.")
    return result
