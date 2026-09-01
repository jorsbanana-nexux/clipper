"""Speech-to-text with word-level timestamps via OpenAI Whisper."""
from openai import OpenAI

from . import config


def transcribe(audio_path: str, language: str | None = None) -> dict:
    if not config.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set. Provide it via environment.")

    client = OpenAI(api_key=config.OPENAI_API_KEY)
    with open(audio_path, "rb") as fh:
        resp = client.audio.transcriptions.create(
            model=config.WHISPER_MODEL,
            file=fh,
            response_format="verbose_json",
            timestamp_granularities=["word"],
            language=language,
        )

    data = resp if isinstance(resp, dict) else getattr(resp, "model_dump", lambda: dict(resp))()

    if not data.get("text", "").strip():
        raise RuntimeError("Whisper returned empty transcription (audio may be silent).")
    return data


def words_from_transcript(data: dict) -> list[dict]:
    words = data.get("words") or []
    out = []
    for w in words:
        out.append({
            "word": w.get("word", "").strip(),
            "start": float(w.get("start", 0.0)),
            "end": float(w.get("end", 0.0)),
        })
    return [w for w in out if w["word"]]


def segments_from_transcript(data: dict) -> list[dict]:
    return data.get("segments") or []
