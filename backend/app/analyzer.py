"""Viral-moment detection: GPT analyses the transcript and picks the best clips.

B2 (v0.2): when speaker turns (diarization) are provided, they are injected into
the prompt so the model can (a) prefer two-person exchanges and (b) return which
speaker(s) are active in each moment. This feeds dynamic layout selection.
"""
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


def _format_turns(turns: list[dict], limit: int = 300) -> str:
    lines = []
    for t in (turns or [])[:limit]:
        spk = t.get("speaker", "SPEAKER_?")
        start = t.get("start", 0.0)
        end = t.get("end", 0.0)
        lines.append(f"[{start:7.2f}-{end:7.2f}] {spk}")
    return "\n".join(lines)


def find_viral_moments(transcript_text, segments, max_clips, min_dur, max_dur, turns=None) -> HighlightAnalysis:
    if not config.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set. Provide it via environment.")

    has_turns = bool(turns)
    turns_block = _format_turns(turns) if has_turns else "(no speaker diarization available)"

    if has_turns:
        speaker_instruction = (
            "Speaker diarization IS available. For each viral moment, fill the "
            "'speaker' field with the PRIMARY speaker label and 'speakers' with ALL "
            "labels active in that window. Prefer moments where two speakers exchange "
            "(disagreement, interruption, rapid back-and-forth) - those tend to go viral."
        )
        fill_note = ""
    else:
        speaker_instruction = (
            "Speaker diarization is NOT available. Leave 'speaker' empty and "
            "'speakers' empty."
        )
        fill_note = ""

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

        {speaker_instruction}

        Transcript segments (start time in seconds, then text):
        {segments}

        Speaker turns (start-end, then label):
        {turns}
    """).format(
        max_clips=max_clips,
        min_dur=int(min_dur),
        max_dur=int(max_dur),
        segments=_format_segments(segments),
        turns=turns_block,
        speaker_instruction=speaker_instruction,
    )

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
