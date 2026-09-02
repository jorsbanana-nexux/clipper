"""Speech-to-text with word-level timestamps via OpenAI Whisper.

Handles the hard 25 MiB file limit transparently: files larger than that are
split into chunks, each chunk is transcribed, then results are merged with
correct timestamp offsets. This makes long podcasts work on the fallback
(full-audio) path.
"""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from openai import OpenAI

from . import config

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"

# OpenAI audio transcriptions hard limit is 25 MiB per request.
MAX_WHISPER_BYTES = 25 * 1024 * 1024
# Chunk under that limit with headroom (mp3 overhead, timing slop).
TARGET_CHUNK_BYTES = 20 * 1024 * 1024


def _probe_duration(audio_path: str) -> float:
    """Duration in seconds via ffprobe."""
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
        capture_output=True, text=True,
    )
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


def _transcribe_single(audio_path: str, client: OpenAI, language: str | None) -> dict:
    """Transcribe one file. Returns the data as-is (may be empty for a
    near-silent trailing chunk). Callers decide whether empty is fatal."""
    with open(audio_path, "rb") as fh:
        resp = client.audio.transcriptions.create(
            model=config.WHISPER_MODEL,
            file=fh,
            response_format="verbose_json",
            timestamp_granularities=["word"],
            language=language,
        )
    return resp if isinstance(resp, dict) else getattr(resp, "model_dump", lambda: dict(resp))()


def _shift(data: dict, offset: float) -> dict:
    """Add `offset` seconds to every word/segment timestamp."""
    words = []
    for w in data.get("words") or []:
        w = dict(w)
        w["start"] = float(w.get("start", 0.0)) + offset
        w["end"] = float(w.get("end", 0.0)) + offset
        words.append(w)
    segments = []
    for s in data.get("segments") or []:
        s = dict(s)
        s["start"] = float(s.get("start", 0.0)) + offset
        s["end"] = float(s.get("end", 0.0)) + offset
        segments.append(s)
    data["words"] = words
    data["segments"] = segments
    return data


def _merge(chunks: list[dict]) -> dict:
    """Merge chunk transcriptions into one (concatenate text, words, segments)."""
    text = " ".join(c.get("text", "") for c in chunks)
    words = []
    segments = []
    for c in chunks:
        words.extend(c.get("words") or [])
        segments.extend(c.get("segments") or [])
    return {
        "text": text,
        "words": words,
        "segments": segments,
        "language": (chunks[0].get("language") if chunks else None),
    }


def _split_audio(audio_path: str, chunk_sec: float, tmp_dir: str) -> list[str]:
    """Split audio into ~chunk_sec pieces via stream copy (fast, no re-encode).

    FIX(bug): the chunk container must keep the SOURCE extension so `-c copy`
    stays valid. Labelling every chunk '.mp3' corrupts the container when the
    source is actually opus/vorbis/webm (mislabeled mux -> Whisper can't read).
    """
    src_ext = Path(audio_path).suffix or ".mp3"
    pattern = os.path.join(tmp_dir, f"chunk_%03d{src_ext}")
    subprocess.run([
        FFMPEG, "-i", audio_path, "-f", "segment", "-segment_time", str(chunk_sec),
        "-c", "copy", "-y", pattern,
    ], check=True, capture_output=True)
    return sorted(str(p) for p in Path(tmp_dir).glob(f"chunk_*{src_ext}"))


def _transcribe_local(audio_path: str, language: str | None) -> dict:
    """Free local transcription via faster-whisper (0 OpenAI cost).

    faster-whisper is the same engine WhisperX uses for transcription; it gives
    word-level timestamps locally. Runs on CPU (compute_type=int8) so it works
    on low-RAM laptops. Model size via WHISPER_MODEL_SIZE (small/tiny/base).
    """
    from faster_whisper import WhisperModel

    size = getattr(config, "WHISPER_MODEL_SIZE", "small")
    model = WhisperModel(size, device="cpu", compute_type="int8")
    segments_iter, info = model.transcribe(
        audio_path, language=language, word_timestamps=True, vad_filter=True)

    words: list[dict] = []
    segments: list[dict] = []
    text_parts: list[str] = []
    for s in segments_iter:
        t = (s.text or "").strip()
        if t:
            text_parts.append(t)
        segments.append({"start": float(s.start), "end": float(s.end), "text": t})
        for w in (s.words or []):
            wd = (w.word or "").strip()
            if wd:
                words.append({"word": wd, "start": float(w.start), "end": float(w.end)})
    return {
        "text": " ".join(text_parts),
        "words": words,
        "segments": segments,
        "language": getattr(info, "language", None),
    }


def transcribe(audio_path: str, language: str | None = None) -> dict:
    if getattr(config, "WHISPER_BACKEND", "local") == "local":
        return _transcribe_local(audio_path, language)

    if not config.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set. Provide it via environment.")

    client = OpenAI(api_key=config.OPENAI_API_KEY)
    size = os.path.getsize(audio_path)

    if size <= MAX_WHISPER_BYTES:
        data = _transcribe_single(audio_path, client, language)
        if not data.get("text", "").strip():
            raise RuntimeError("Whisper returned empty transcription (audio may be silent).")
        return data

    # Large file -> split into chunks under 25 MiB, transcribe, and merge.
    duration = max(_probe_duration(audio_path), 1.0)
    bytes_per_sec = size / duration
    # seconds per chunk targeting TARGET_CHUNK_BYTES (with a 30s floor to avoid many files)
    chunk_sec = max(30.0, (TARGET_CHUNK_BYTES / bytes_per_sec) * 0.9)

    tmp_dir = tempfile.mkdtemp(prefix="whisper_chunk_")
    try:
        chunks_paths = _split_audio(audio_path, chunk_sec, tmp_dir)
        results = []
        offset = 0.0
        for cp in chunks_paths:
            chunk_dur = max(_probe_duration(cp), 0.0)
            try:
                data = _transcribe_single(cp, client, language)
            except Exception:
                data = {"text": "", "words": [], "segments": []}
            # Keep offset advancing even if this chunk is silent/failed, so the
            # timestamps of later chunks remain correct.
            if data.get("text", "").strip() or data.get("words") or data.get("segments"):
                results.append(_shift(data, offset))
            offset += chunk_dur
        if not results:
            raise RuntimeError("Whisper returned no transcription for any chunk (audio may be silent).")
        return _merge(results)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


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
