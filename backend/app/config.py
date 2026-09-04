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
# Higher-quality FREE option: gemini-3.8-flash is Google's most intelligent
# Flash model (best for complex analysis like viral-moment detection) and is
# still free on the AI Studio free tier. Slower fallbacks: gemini-3.7-flash,
# gemini-3.6-flash. Use gemini-2.5-pro for max reasoning if you accept stricter
# free-tier rate limits (it is also free).
GEMINI_MODEL: str = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
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
# Font size is auto-scaled to fit max 2 lines on the safe area. This is the
# base size before auto-fit. Mr Beast style = big, bold, high-contrast.
SUBTITLE_SIZE: int = int(os.environ.get("CLIPPER_SUBTITLE_SIZE", "100"))
# Max subtitle lines shown at once (2 = standard vertical-video safe area).
MAX_SUBTITLE_LINES: int = int(os.environ.get("CLIPPER_SUBTITLE_LINES", "2"))
# Karaoke word-pop colours. Base = colour of not-yet-spoken words (white);
# pop = colour the ACTIVE (being-spoken) word fills to. In ASS the karaoke
# fill uses SecondaryColour, so we set Base=Primary and Pop=Secondary.
# Mr Beast brand yellow. ASS colour format is &HAABBGGRR, so yellow #FFD600
# (R=FF,G=D6,B=00) is &H0000D6FF — NOT &H00D600FF (that is magenta).
SUBTITLE_BASE_COLOR: str = os.environ.get("CLIPPER_SUBTITLE_BASE_COLOR", "&H00FFFFFF")
SUBTITLE_POP_COLOR: str = os.environ.get("CLIPPER_SUBTITLE_POP_COLOR", "&H0000D6FF")
# Thick dark outline = readable over any busy/facial background (Mr Beast look).
SUBTITLE_OUTLINE: int = int(os.environ.get("CLIPPER_SUBTITLE_OUTLINE", "8"))
SUBTITLE_SHADOW: int = int(os.environ.get("CLIPPER_SUBTITLE_SHADOW", "3"))
# Back box opacity (semi-transparent) behind text for readability on any frame.
SUBTITLE_BACK_COLOR: str = os.environ.get("CLIPPER_SUBTITLE_BACK_COLOR", "&H70141014")
# Scale-pop animation: the ACTIVE word scales up to this fraction (1.0 = off).
# Mr Beast style uses a punchy per-word pop that reads instantly on rewatches.
SUBTITLE_POP: float = float(os.environ.get("CLIPPER_SUBTITLE_POP", "1.18"))

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

# --- Face framing (camera) ---
# Zoom-out factor for the 9:16 crop-follow. 1.0 = tight full-height fill (face
# fills frame); <1.0 zooms out: subject is scaled down and placed on a blurred
# background with headroom, so the face is smaller and framing is comfortable.
FACE_ZOOM: float = float(os.environ.get("CLIPPER_FACE_ZOOM", "0.86"))
# Camera smoothing: alpha of the exponential moving average on face centre-x
# (lower = smoother/slower to catch up; higher = snappier/more jitter).
FACE_SMOOTH_ALPHA: float = float(os.environ.get("CLIPPER_FACE_SMOOTH", "0.28"))
# Headroom: where the subject sits vertically on the canvas (0=top, 1=bottom).
FACE_HEADROOM: float = float(os.environ.get("CLIPPER_FACE_HEADROOM", "0.30"))

# --- Duo split-screen ---
# Pre-switch: how many seconds BEFORE the 2nd speaker's turn the screen should
# already be split, so the transition is smooth and never feels late.
DUO_LEAD_SEC: float = float(os.environ.get("CLIPPER_DUO_LEAD_SEC", "2.5"))
# Auto-duo fallback: when diarization is unavailable/fails, switch to split-screen
# automatically if two faces are detected. Lets duo work WITHOUT a HuggingFace
# token (this fixes "split-screen never appears even though I set the token").
DUO_AUTO_FACES: bool = os.environ.get("CLIPPER_DUO_AUTO_FACES", "1") in ("1", "true", "yes", "on")
# Min fraction of sampled frames that must show 2 faces before auto-duo kicks in.
DUO_AUTO_FACE_RATIO: float = float(os.environ.get("CLIPPER_DUO_AUTO_FACE_RATIO", "0.35"))
# When diarization is available, a DUO segment is only kept if two faces are
# actually visible in that window (>= this fraction of samples). Prevents a
# split-screen from showing an empty half when the camera cuts to close-ups.
DUO_FACE_RATIO: float = float(os.environ.get("CLIPPER_DUO_FACE_RATIO", "0.4"))

# --- Cut accuracy ---
# After downloading a segment, re-trim it precisely to the exact [start, end]
# window so the video NEVER runs past the chosen point (fixes keyframe overshoot
# that made clips include irrelevant trailing content).
PRECISE_TRIM: bool = os.environ.get("CLIPPER_PRECISE_TRIM", "1") in ("1", "true", "yes", "on")
# Trailing padding after the highlighted moment (small = clip stops crisply at
# the punchline instead of rambling on). Head padding stays at PADDING_SEC.
TAIL_SEC: float = float(os.environ.get("CLIPPER_TAIL_SEC", "0.35"))
