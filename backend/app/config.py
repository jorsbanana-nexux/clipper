"""Central configuration for the Clipper backend.

All values come from environment variables with sensible defaults, so the
service can be deployed anywhere (local, Docker, a VPS) without code changes.

A `.env` file at the REPO ROOT is loaded automatically (python-dotenv), so
users can store credentials there by editing `.env` (copy from `.env.example`).
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# Repo root is three levels up from this file (backend/app/config.py).
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_REPO_ROOT / ".env", override=False)  # env vars win over .env

# --- AI (bring your own key) ---
OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")
WHISPER_MODEL: str = os.environ.get("WHISPER_MODEL", "whisper-1")
# FIX(bug): 'gpt-5.4-mini' is not a real OpenAI model and would 404 at runtime.
# Default to a widely-available structured-output model (gpt-4o-mini).
# Override via env: ANALYSIS_MODEL=gpt-5 ...
ANALYSIS_MODEL: str = os.environ.get("ANALYSIS_MODEL", "gpt-4o-mini")
# Optional reasoning effort for o-series reasoning models ONLY. Leave empty for
# standard models (gpt-4o-mini etc.) which reject the parameter.
ANALYSIS_REASONING: str = os.environ.get("ANALYSIS_REASONING", "").strip()

# --- FREE backends (no OpenAI cost) ---
# Whisper: "local" = faster-whisper runs on THIS machine (0 cost); "openai" = API.
# Default "local" avoids any OpenAI billing by design. On a low-RAM PC use the
# small "tiny" or "base" size via WHISPER_MODEL_SIZE.
WHISPER_BACKEND: str = os.environ.get("WHISPER_BACKEND", "local")
WHISPER_MODEL_SIZE: str = os.environ.get("WHISPER_MODEL_SIZE", "small")
# Analysis LLM: "gemini" (free Google AI Studio tier) or "openai".
ANALYSIS_BACKEND: str = os.environ.get("ANALYSIS_BACKEND", "gemini")
GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")
# Current, non-deprecated Gemini model (gemini-2.x/1.5 are removed/404).
GEMINI_MODEL: str = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
# Auto-retry count on transient Gemini errors (503 high demand / 429 quota).
GEMINI_RETRIES: int = int(os.environ.get("GEMINI_RETRIES", "4"))

# --- Output / storage ---
OUTPUT_DIR: Path = Path(os.environ.get("CLIPPER_OUTPUT_DIR", "./output"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# --- CORS ---
# Allowed origins. The Next.js frontend uses server-side rewrites, so the
# browser never calls the backend cross-origin in the default dev setup.
# Restrict to explicit localhost origins; override for a public deploy.
CORS_ORIGINS: list[str] = [
    o.strip()
    for o in os.environ.get(
        "CLIPPER_CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,"
        "http://localhost:8000,http://127.0.0.1:8000",
    ).split(",")
    if o.strip()
]

# --- Clip defaults ---
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
MAX_PARALLEL: int = int(os.environ.get("CLIPPER_MAX_PARALLEL", "3"))
