"""Central configuration for the Clipper backend.

All values come from environment variables with sensible defaults, so the
service can be deployed anywhere (local, Docker, a VPS) without code changes.
"""
import os
from pathlib import Path

# --- AI (bring your own key) ---
OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")
WHISPER_MODEL: str = os.environ.get("WHISPER_MODEL", "whisper-1")
ANALYSIS_MODEL: str = os.environ.get("ANALYSIS_MODEL", "gpt-5.4-mini")

# --- Output / storage ---
OUTPUT_DIR: Path = Path(os.environ.get("CLIPPER_OUTPUT_DIR", "./output"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# --- Clip defaults ---
DEFAULT_MAX_CLIPS: int = int(os.environ.get("CLIPPER_MAX_CLIPS", "8"))
MIN_CLIP_SEC: float = float(os.environ.get("CLIPPER_MIN_CLIP_SEC", "20"))
MAX_CLIP_SEC: float = float(os.environ.get("CLIPPER_MAX_CLIP_SEC", "75"))
# Padding (seconds) added before/after each clip so the moment is never cut off
PADDING_SEC: float = float(os.environ.get("CLIPPER_PADDING_SEC", "1.5"))

# --- Vertical output (9:16) ---
TARGET_WIDTH: int = 1080
TARGET_HEIGHT: int = 1920

# --- Subtitle style ---
SUBTITLE_FONT: str = os.environ.get("CLIPPER_SUBTITLE_FONT", "Montserrat")
SUBTITLE_SIZE: int = int(os.environ.get("CLIPPER_SUBTITLE_SIZE", "80"))

# --- Multi-speaker (v0.2) ---
# Diarization is OPTIONAL and heavy (torch). Enable only if you have a
# HuggingFace token that accepted the pyannote terms AND enough RAM.
MULTI_SPEAKER: bool = os.environ.get("CLIPPER_MULTI_SPEAKER", "") in ("1", "true", "yes", "on")
HUGGINGFACE_TOKEN: str = os.environ.get("HUGGINGFACE_TOKEN", "")

# Layout template used per clip: "single" (follow active speaker) or "duo"
# (split-screen, two speakers). Empty = auto (decided by diarization).
LAYOUT_MODE: str = os.environ.get("CLIPPER_LAYOUT_MODE", "auto")

# --- Fase A: accuracy & hardening ---
# Cut strategy for clip boundaries: "fast" (stream copy -> keyframe-aligned, ~2-5s
# slop) or "accurate" (re-encode -> frame-accurate, slower/heavier).
CUT_MODE: str = os.environ.get("CLIPPER_CUT_MODE", "accurate")

# Directory with subtitle fonts (optional). If set and non-empty, ASS render uses
# fontsdir=... so the chosen SUBTITLE_FONT is bundled reliably.
FONT_DIR: str = os.environ.get("CLIPPER_FONT_DIR", "")

# Retention: delete job output folders older than N days (0 = keep forever).
RETENTION_DAYS: float = float(os.environ.get("CLIPPER_RETENTION_DAYS", "7"))

# yt-dlp resilience (optional).
YDL_COOKIES_FILE: str = os.environ.get("YDL_COOKIES_FILE", "")   # path to cookies.txt
YDL_PROXY: str = os.environ.get("YDL_PROXY", "")                 # e.g. http://127.0.0.1:8888
YDL_RETRIES: int = int(os.environ.get("YDL_RETRIES", "3"))

# Clip rendering concurrency. Default 1 (sequential) = low-spec friendly.
MAX_PARALLEL: int = int(os.environ.get("CLIPPER_MAX_PARALLEL", "1"))
