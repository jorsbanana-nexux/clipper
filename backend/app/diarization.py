"""Optional speaker diarization via pyannote-audio.

Answers "who is speaking when" — the foundation of multi-speaker layouts and
dynamic speaker switching (v0.2).

OPTIONAL and gated; the pipeline must NEVER crash if it is unavailable:
- Requires CLIPPER_MULTI_SPEAKER=1 and a HUGGINGFACE_TOKEN that has accepted
  the pyannote/speaker-diarization model license.
- Requires the heavy extra deps:  pip install -r requirements-multispeaker.txt
- pyannote.audio pulls in torch (large). On a low-spec machine leave this off.

Diarization is run on a SHORT per-clip audio segment (~60-80s), so it stays fast.
"""
from . import config

MODEL_ID = "pyannote/speaker-diarization-3.1"


def diarization_available() -> bool:
    """True when multi-speaker diarization can actually run."""
    if not config.MULTI_SPEAKER or not config.HUGGINGFACE_TOKEN:
        return False
    try:
        import torch  # noqa: F401
        import pyannote.audio  # noqa: F401
        return True
    except ImportError:
        return False


def diarize(audio_path: str) -> list[dict]:
    """Return [{speaker, start, end}] turns, or [] when unavailable/failed."""
    if not diarization_available():
        return []

    from pyannote.audio import Pipeline

    # HuggingFace renamed use_auth_token -> token; support both.
    try:
        pipeline = Pipeline.from_pretrained(MODEL_ID, token=config.HUGGINGFACE_TOKEN)
    except TypeError:
        pipeline = Pipeline.from_pretrained(MODEL_ID, use_auth_token=config.HUGGINGFACE_TOKEN)

    diarization = pipeline(audio_path)
    turns = []
    for turn, _track, speaker in diarization.itertracks(yield_label=True):
        turns.append({"speaker": speaker, "start": turn.start, "end": turn.end})
    return turns
