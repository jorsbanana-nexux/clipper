"""Viral-moment detection: an LLM analyses the transcript and picks the best clips.

Backends: "gemini" (free Google AI Studio tier, default) or "openai".

v0.2: speaker turns (diarization) are injected into the prompt so the model can
(a) prefer two-person exchanges and (b) return which speaker(s) are active.

v0.3 (research-driven — answers the top complaints about EVERY clipper
platform: "AI picks the safe boring parts", "clips are repetitive",
"no control", "bad metadata for posting"):
- HUMAN STEER: optional user keywords + free-text editing instruction.
- MULTI-DIMENSION SCORING (hook / payoff / emotion / quotability / energy).
- DIVERSITY: the prompt explicitly forbids near-duplicate moments.
- POSTING METADATA: a ready caption + hashtags in the CONTENT's language.
- LANGUAGE-AWARE output (title/reason/hook/caption follow the content language,
  e.g. Indonesian content -> Indonesian metadata — no global platform does this).
"""
import json
import time
from textwrap import dedent

from . import config
from .models import HighlightAnalysis

# BUGFIX (v0.3.4): `genai_types` used to be imported LOCALLY inside
# _analyze_gemini() and referenced from a DIFFERENT function, _gemini_generate()
# — Python does not share a function's local names with its callees (no
# closure here, they're sibling top-level functions), so every real Gemini
# call raised `NameError: name 'genai_types' is not defined` the moment it
# reached client.models.generate_content(). Moved to a module-level LAZY
# import: still optional (ANALYSIS_BACKEND=openai users may not have
# google-genai installed at all), but now visible to every function in this
# file instead of only the one that happened to import it.
try:
    from google import genai as _genai
    from google.genai import types as _genai_types
except ImportError:
    _genai = None
    _genai_types = None


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


def _build_prompt(segments, max_clips, min_dur, max_dur, turns,
                  keywords: str = "", instruction: str = "") -> str:
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

    # HUMAN STEER (v0.3): the user gets a vote BEFORE rendering. This is the
    # single biggest differentiator vs Opus/Vizard/Klap, whose users constantly
    # complain the AI "didn't use the good parts" with no way to steer it.
    steer_block = ""
    if (keywords or "").strip():
        steer_block += (
            f"\n        THE USER SPECIFICALLY WANTS CLIPS ABOUT: {keywords.strip()}\n"
            "        Strongly prefer moments matching these topics when they exist; "
            "use your own judgment ONLY when nothing genuinely good matches.\n"
        )
    if (instruction or "").strip():
        steer_block += (
            f"\n        THE USER'S EDITING INSTRUCTION (highest priority): {instruction.strip()}\n"
            "        Follow it like a client brief from a paying customer.\n"
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
        {steer_block}
        THE MEAT (mandatory structure per clip — no exceptions):
        - HOOK: the first seconds must grab ("wait, what did he just say?").
        - INTI: the core problem / surprising idea / the story being built.
        - KONKLUSI: the payoff — punchline, answer, or takeaway. If a moment
          has NO payoff, it is NOT a clip. Skip it entirely.

        CUT TIMING (accuracy matters — this is the #1 complaint):
        - Choose the START at the first word of the thought (never mid-sentence).
        - Choose the END EXACTLY when the point lands / the punchline is delivered.
          Do NOT extend past it — trailing words after the payoff kill the clip.
        - NEVER include trailing silence, "um / yeah / so..." filler, or the
          topic change that comes AFTER the payoff. If the transcript shows a
          pause or the speaker trailing off, END THE CLIP THERE. Dead air at
          the end = a broken clip.

        DIVERSITY (v0.3 — the #2 complaint is repetitive clips):
        - The {max_clips} moments must cover DIFFERENT ideas/angles of the
          conversation. Never return two moments about the same point.
        - If the material only supports fewer good clips, return fewer —
          5 excellent, distinct clips beat 8 repetitive ones.

        SCORING (multi-dimension, be honest and calibrated):
        - For every clip fill 'scores': hook (grab of the first seconds),
          payoff (satisfaction of the ending), emotion (emotional charge),
          quotability (shareable one-liner quality), energy (pacing / no dead
          air). 1-10 each, no inflation — a mediocre moment must NOT get 8s.
        - 'viral_score' = your overall 1-10 judgement, roughly the average of
          the five dimensions for a real clip.

        POSTING METADATA (v0.3 — creators need this to publish):
        - 'caption': a ready-to-post social caption for THIS clip. Write it in
          the SAME LANGUAGE as the video content. First-person, punchy, 1-2
          sentences, NO hashtags inside the caption text.
        - 'hashtags': 3-8 lowercase hashtags WITHOUT the '#' symbol, relevant
          to the clip and likely searched by the target audience.

        LANGUAGE RULE (critical — no global platform does this):
        - Whatever language the CONTENT is in, write title, reason, hook,
          caption and hashtags in THAT language. If the content is Indonesian,
          metadata is Indonesian. If English, English. Mixed speech -> follow
          the dominant language.

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
        steer_block=steer_block,
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
    if _genai is None or _genai_types is None:
        raise RuntimeError(
            "google-genai not installed. Run: pip install -U google-genai")

    client = _genai.Client(api_key=config.GEMINI_API_KEY)
    # v0.3.1: MODEL FALLBACK CHAIN. Model utama 404/deprecated atau sibuk ->
    # otomatis lanjut ke model gratis berikutnya. Analysis tidak pernah mati
    # hanya karena Google mempensiunkan/menyibukkan satu model.
    models = [config.GEMINI_MODEL] + [
        m for m in getattr(config, "GEMINI_FALLBACK_MODELS", []) if m
    ]
    last_model_err: Exception | None = None
    for model_name in models:
        try:
            return _gemini_generate(client, model_name, prompt)
        except Exception as e:
            last_model_err = e
            msg = str(e)
            fatal = ("API key" in msg or "permission" in msg.lower())
            if fatal:
                raise  # wrong key -> trying other models won't help
            continue  # model 404/503/429 -> try the next model in the chain
    raise last_model_err if last_model_err else RuntimeError("Gemini: no models configured")


def _gemini_generate(client, model_name: str, prompt: str) -> HighlightAnalysis:
    """One model, with transient (503/429) retry + honest JSON parsing."""
    max_attempts = max(1, getattr(config, "GEMINI_RETRIES", 4))
    last_err: Exception | None = None
    for attempt in range(max_attempts):
        try:
            resp = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=_genai_types.GenerateContentConfig(
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


def find_viral_moments(segments, max_clips, min_dur, max_dur, turns=None,
                       keywords: str = "", instruction: str = "") -> HighlightAnalysis:
    """Pick the viral moments — with a HARD offline guarantee (v0.4).

    v0.4: the analysis can no longer kill the pipeline. Every commercial
    clipper needs a cloud key; Clipper now has three tiers:
      1. ANALYSIS_BACKEND=local         -> offline heuristic analyzer only.
      2. gemini/openai with a valid key  -> LLM analysis (best quality).
      3. LLM key missing OR the call fails for ANY reason -> automatic
         fallback to the offline heuristic analyzer. The job NEVER dies with
         "GEMINI_API_KEY not set" or a 503 storm again.
    """
    from . import analyzer_local
    backend = getattr(config, "ANALYSIS_BACKEND", "gemini").strip().lower()

    if backend == "local":
        return analyzer_local.analyze(segments, max_clips, min_dur, max_dur,
                                      keywords=keywords, instruction=instruction)

    prompt = _build_prompt(segments, max_clips, min_dur, max_dur, turns,
                           keywords=keywords, instruction=instruction)
    key_ready = (config.GEMINI_API_KEY if backend == "gemini" else config.OPENAI_API_KEY)
    if not key_ready:
        # No key configured: go straight to the offline path (no exception, no
        # 500 — the job just works).
        return analyzer_local.analyze(segments, max_clips, min_dur, max_dur,
                                      keywords=keywords, instruction=instruction)
    try:
        if backend == "gemini":
            return _analyze_gemini(prompt)
        if backend == "openai":
            return _analyze_openai(prompt)
    except Exception as e:
        # Key was set but the API failed (quota, 503 storm, model retired,
        # network down...). Degrade gracefully to offline instead of dying.
        import sys
        print(f"[analyzer] {backend} failed ({e}); falling back to the offline "
              f"heuristic analyzer", file=sys.stderr)
    # unknown backend, or the API call above failed -> offline guarantees the job
    return analyzer_local.analyze(segments, max_clips, min_dur, max_dur,
                                  keywords=keywords, instruction=instruction)
