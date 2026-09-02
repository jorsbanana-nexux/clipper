"""Viral-moment detection: an LLM analyses the transcript and picks the best clips.

Backends: "gemini" (free Google AI Studio tier, default) or "openai".

B2 (v0.2): when speaker turns (diarization) are provided, they are injected into
the prompt so the model can (a) prefer two-person exchanges and (b) return which
speaker(s) are active in each moment. This feeds dynamic layout selection.
"""
import json
from textwrap import dedent

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


def _build_prompt(segments, max_clips, min_dur, max_dur, turns) -> str:
    has_turns = bool(turns)
    turns_block = _format_turns(turns) if has_turns else "(no speaker diarization available)"
    if has_turns:
        speaker_instruction = (
            "Speaker diarization IS available. For each viral moment, fill the "
            "'speaker' field with the PRIMARY speaker label and 'speakers' with ALL "
            "labels active in that window. Prefer moments where two speakers exchange "
            "(disagreement, interruption, rapid back-and-forth) - those tend to go viral."
        )
    else:
        speaker_instruction = (
            "Speaker diarization is NOT available. Leave 'speaker' empty and "
            "'speakers' empty."
        )
    return dedent("""
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


def _analyze_gemini(prompt: str) -> HighlightAnalysis:
    """Free Google AI Studio (Gemini) backend — needs GEMINI_API_KEY.

    Uses the modern `google-genai` SDK with `response_schema=HighlightAnalysis`
    (mirrors OpenAI structured output). Older `gemini-2.x`/`1.5` models are
    deprecated; use a current model such as gemini-3.5-flash (see GEMINI_MODEL).
    """
    if not config.GEMINI_API_KEY:
        raise RuntimeError(
            "ANALYSIS_BACKEND=gemini but GEMINI_API_KEY is empty. "
            "Get a free key at https://aistudio.google.com/apikey and set it in .env "
            "(or set ANALYSIS_BACKEND=openai to use OpenAI).")
    try:
        from google import genai
        from google.genai import types as genai_types
    except ImportError:
        raise RuntimeError(
            "google-genai not installed. Run: pip install -U google-genai")

    client = genai.Client(api_key=config.GEMINI_API_KEY)
    resp = client.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=HighlightAnalysis,
            temperature=0.2,
        ),
    )
    # google-genai returns a typed object via `parsed`; fall back to text parse.
    parsed = getattr(resp, "parsed", None)
    if parsed is not None:
        return parsed
    raw = getattr(resp, "text", "") or ""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    try:
        return HighlightAnalysis.model_validate_json(raw)
    except Exception as e:
        raise RuntimeError(f"Gemini returned non-JSON / invalid response: {e}") from e


def _analyze_openai(prompt: str) -> HighlightAnalysis:
    if not config.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set. Provide it via environment.")
    from openai import OpenAI
    client = OpenAI(api_key=config.OPENAI_API_KEY)
    resp = client.beta.chat.completions.parse(
        model=config.ANALYSIS_MODEL,
        messages=[
            {"role": "system", "content": "You are an expert short-form video editor."},
            {"role": "user", "content": prompt},
        ],
        response_format=HighlightAnalysis,
        # reasoning_effort is only accepted by o-series reasoning models; gate.
        **({"reasoning_effort": config.ANALYSIS_REASONING} if config.ANALYSIS_REASONING else {}),
    )
    result = resp.choices[0].message.parsed
    if result is None:
        raise RuntimeError("AI analysis returned an incomplete response.")
    return result


def find_viral_moments(segments, max_clips, min_dur, max_dur, turns=None) -> HighlightAnalysis:
    prompt = _build_prompt(segments, max_clips, min_dur, max_dur, turns)
    backend = getattr(config, "ANALYSIS_BACKEND", "gemini")
    if backend == "gemini":
        return _analyze_gemini(prompt)
    if backend == "openai":
        return _analyze_openai(prompt)
    raise RuntimeError(f"Unknown ANALYSIS_BACKEND: {backend}")
