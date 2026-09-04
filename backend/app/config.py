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
# Mr Beast style: the brand font is Komika Axis (extra-bold). If you put a
# Komika Axis .ttf/.otf in CLIPPER_FONT_DIR (or repo/fonts), libass resolves it;
# otherwise it falls back to the closest bold system font.
SUBTITLE_FONT: str = os.environ.get("CLIPPER_SUBTITLE_FONT", "Komika Axis")
# Font size is auto-scaled to fit max 2 lines on the safe area. This is the
# base size before auto-fit. Mr Beast style = big, bold, high-contrast.
SUBTITLE_SIZE: int = int(os.environ.get("CLIPPER_SUBTITLE_SIZE", "100"))
# Max subtitle lines shown at once (2 = standard vertical-video safe area).
MAX_SUBTITLE_LINES: int = int(os.environ.get("CLIPPER_SUBTITLE_LINES", "2"))
# Karaoke word-pop colours. Base = colour of not-yet-spoken words (white);
# pop = colour the ACTIVE (being-spoken) word fills to. In ASS the karaoke
# fill uses SecondaryColour, so we set Base=Primary and Pop=Secondary.
# ASS colour format is &HAABBGGRR.
# Active (being-spoken) word = bright saturated BLUE (Mr Beast highlighter).
# #1E90FF = R=1E, G=90, B=FF -> &H00FF901E. Rest of words stay WHITE.
SUBTITLE_BASE_COLOR: str = os.environ.get("CLIPPER_SUBTITLE_BASE_COLOR", "&H00FFFFFF")
# STRICT Mr Beast: ONLY the active word flashes to YELLOW (&HAABBGGRR,
# yellow = 0000FFFF in BGR) and returns to white when the word ends.
SUBTITLE_POP_COLOR: str = os.environ.get("CLIPPER_SUBTITLE_POP_COLOR", "&H0000FFFF")
# Thick dark outline = readable over any busy/facial background (Mr Beast look).
SUBTITLE_OUTLINE: int = int(os.environ.get("CLIPPER_SUBTITLE_OUTLINE", "8"))
SUBTITLE_SHADOW: int = int(os.environ.get("CLIPPER_SUBTITLE_SHADOW", "3"))
# Back box opacity (semi-transparent) behind text for readability on any frame.
SUBTITLE_BACK_COLOR: str = os.environ.get("CLIPPER_SUBTITLE_BACK_COLOR", "&H70141014")
# Scale-pop animation: the ACTIVE word scales up to this fraction (1.0 = off).
# Mr Beast style uses a punchy per-word pop that reads instantly on rewatches.
# STRICT Mr Beast bounce: active word jumps to 120% (POP), dips to 95% (DIP),
# settles back to 100% exactly when the word ends.
SUBTITLE_POP: float = float(os.environ.get("CLIPPER_SUBTITLE_POP", "1.20"))
SUBTITLE_DIP: float = float(os.environ.get("CLIPPER_SUBTITLE_DIP", "0.95"))
# How many words per subtitle cue (Mr Beast style = short, ~2). Keeps text
# glanceable instead of a wall of text.
MAX_SUBTITLE_WORDS: int = int(os.environ.get("CLIPPER_SUBTITLE_WORDS", "2"))
# Minimum a cue stays on screen (seconds). Prevents fast speakers from making
# subtitles flicker/chaotic: when speech is faster than this, more words are
# joined into the same cue (up to MAX_SUBTITLE_WORDS_OVERFLOW) instead of rushing.
MIN_SUBTITLE_DUR: float = float(os.environ.get("CLIPPER_SUBTITLE_MIN_DUR", "0.9"))
MAX_SUBTITLE_WORDS_OVERFLOW: int = int(os.environ.get("CLIPPER_SUBTITLE_WORDS_OVERFLOW", "5"))

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
# If you drop a Komika Axis .ttf/.otf in <repo>/fonts it is used automatically.
_DEFAULT_FONTS = _REPO_ROOT / "fonts"
FONT_DIR: str = os.environ.get(
    "CLIPPER_FONT_DIR", str(_DEFAULT_FONTS) if _DEFAULT_FONTS.is_dir() else "")

# Retention: delete job output folders older than N days (0 = keep forever).
RETENTION_DAYS: float = float(os.environ.get("CLIPPER_RETENTION_DAYS", "7"))

# --- Transcript analysis budget (analyzer) ---
# Max characters of transcript sent to the analysis LLM in one prompt.
# 400k chars is roughly 100k tokens — comfortably inside Gemini flash's
# 1M-token context and covers even 3-hour podcasts in full.
TRANSCRIPT_MAX_CHARS: int = int(os.environ.get("CLIPPER_TRANSCRIPT_MAX_CHARS", "400000"))

# yt-dlp resilience (optional).
YDL_COOKIES_FILE: str = os.environ.get("YDL_COOKIES_FILE", "")   # path to cookies.txt
YDL_PROXY: str = os.environ.get("YDL_PROXY", "")                 # e.g. http://127.0.0.1:8888
YDL_RETRIES: int = int(os.environ.get("YDL_RETRIES", "3"))

# Clip rendering concurrency (BATCH / performance).
# Default is CPU-aware so a local machine is used fully but not overloaded:
# min(8, max(2, cpu_count//2)). Tune via CLIPPER_MAX_PARALLEL (e.g. 1 for a
# weak laptop, 8 for a beefy desktop) to render 10-100 clips fast & stably.
def _default_parallel() -> int:
    try:
        n = os.cpu_count() or 4
    except Exception:
        n = 4
    return max(2, min(8, n // 2))
MAX_PARALLEL: int = int(os.environ.get("CLIPPER_MAX_PARALLEL", str(_default_parallel())))

# --- FFmpeg speed/quality (BATCH / performance) ---
# Preset trades encode speed vs CPU. `veryfast` is ~2-3x faster than `fast` with
# near-equal visual quality at a slightly higher CRF — best for local batch.
FFMPEG_PRESET: str = os.environ.get("CLIPPER_FFMPEG_PRESET", "veryfast")
FFMPEG_CRF: int = int(os.environ.get("CLIPPER_FFMPEG_CRF", "21"))

# --- Face framing (camera) ---
# Zoom-out factor for the 9:16 crop-follow. 1.0 = tight full-height fill (face
# fills frame); <1.0 zooms out: subject is scaled down and placed on a blurred
# background with headroom, so the face is smaller and framing is comfortable.
# 0.80 = comfortable zoom-OUT with headroom (was 0.86: too tight on the face).
FACE_ZOOM: float = float(os.environ.get("CLIPPER_FACE_ZOOM", "0.80"))
# Camera smoothing: alpha of the exponential moving average on face centre-x
# (lower = smoother/slower to catch up; higher = snappier/more jitter).
FACE_SMOOTH_ALPHA: float = float(os.environ.get("CLIPPER_FACE_SMOOTH", "0.20"))
# Headroom: where the subject sits vertically on the canvas (0=top, 1=bottom).
FACE_HEADROOM: float = float(os.environ.get("CLIPPER_FACE_HEADROOM", "0.32"))

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
