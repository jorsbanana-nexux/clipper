"""Viral-moment detection: an LLM analyses the transcript and picks the best clips.

Backends: "gemini" (free Google AI Studio tier, default) or "openai".

B2 (v0.2): when speaker turns (diarization) are provided, they are injected into
the prompt so the model can (a) prefer two-person exchanges and (b) return which
speaker(s) are active in each moment. This feeds dynamic layout selection.
"""
import json
import time
from textwrap import dedent

from . import config
from .models import HighlightAnalysis


def _format_segments(segments: list[dict], limit: int = 0,
                      max_chars: int | None = None) -> str:
    """Format transcript segments for the LLM prompt.

    BUGFIX(critical): this used to hard-cap at 200 segments, silently dropping
    70-80% of the transcript on any video longer than ~15 minutes — the LLM
    could then only pick "viral moments" from the opening minutes. Now the full
    transcript is sent, bounded only by a generous character budget (Gemini
    flash has a 1M-token context; 400k chars is ~100k tokens, i.e. even a
    3-hour podcast fits).
    """
    if max_chars is None:
        max_chars = getattr(config, "TRANSCRIPT_MAX_CHARS", 400_000)
    lines = []
    total = 0
    count = 0
    for s in segments:
        if limit and count >= limit:
            break
        start = s.get("start", 0.0)
        text = (s.get("text") or "").strip().replace("\n", " ")
        line = f"[{start:7.2f}s] {text}"
        if total + len(line) > max_chars:
            break
        lines.append(line)
        total += len(line) + 1
        count += 1
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
        You are an elite short-form video editor who thinks like a HUMAN editor,
        not a robot. Given a podcast transcript with timestamps, find the {max_clips}
        moments that a skilled clip editor would actually cut — the "meat" of the
        conversation that makes people stop scrolling, rewatch and share.

        HOW A HUMAN EDITOR THINKS (follow this mindset):
        - Hunt for the SUBSTANCE, not surface noise. Pick moments that deliver a
          genuinely valuable, surprising or emotionally charged idea — not mere
          transitions, greetings, small talk, or rambling filler.
        - Each clip must be ONE complete thought with a clear arc: a strong hook
          up front, a build, and a satisfying payoff / punchline / takeaway at the
          end. A clip without a payoff feels flat and boring.

        CUT TIMING (accuracy matters — this is the #1 complaint):
        - Choose the START at the first word of the thought (never mid-sentence).
        - Choose the END EXACTLY when the point lands / the punchline is delivered.
          Do NOT extend past it — trailing words after the payoff kill the clip.
        - Each clip must be {min_dur}-{max_dur} seconds.
        - Use the EXACT timestamps from the transcript. Never invent times.
        - Avoid overlaps between clips.

        Prefer moments with: strong hooks, surprising claims, quotable lines,
        emotional peaks, concrete actionable tips, conflicts, or payoffs.
        Rank them by viral potential (best first).

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
    max_attempts = max(1, getattr(config, "GEMINI_RETRIES", 4))
    last_err: Exception | None = None
    for attempt in range(max_attempts):
        try:
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
        except Exception as e:
            last_err = e
            msg = str(e)
            transient = ("503" in msg or "429" in msg
                         or "UNAVAILABLE" in msg or "RESOURCE_EXHAUSTED" in msg
                         or "high demand" in msg)
            if transient and attempt < max_attempts - 1:
                time.sleep(1.5 * (attempt + 1))  # backoff: 1.5s, 3s, ...
                continue
            raise  # not transient, or ran out of retries
    raise last_err


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
