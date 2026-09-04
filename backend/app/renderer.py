"""Final clip assembly: cut + reframe + subtitles + effects via ffmpeg."""
import os
import shutil
import subprocess

from . import config

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"


def _fpath(p: str) -> str:
    """Normalise a filesystem path for embedding inside an ffmpeg filtergraph.

    Backslash is an ESCAPE character in ffmpeg filter parsing, so a Windows path
    like C:\\out\\clip\\subs.ass would have its backslashes stripped (file not
    found). Forward slashes are accepted on Windows and fix the ass= lookup.
    """
    return p.replace("\\", "/")


def effects_vf(ass_path: str | None = None) -> str:
    """FFmpeg -vf suffix for subtitles + viral effects. Reused so a reframe pass
    and the subtitle/effects pass can be merged into ONE encode (faster batch)."""
    chain = (
        f"eq=contrast=1.06:saturation=1.15:brightness=0.01,"
        f"unsharp=5:5:0.6:5:5:0.0"
    )
    if ass_path and os.path.exists(ass_path):
        chain = f"ass={_fpath(ass_path)}," + chain
    return chain


def encode_video(src: str, out_path: str, vf: str, audio: str = "copy") -> str:
    """Encode once from `src` to `out_path` with a filtergraph, using the global
    speed preset. Single-pass = the core batch speedup (fewer re-encodes)."""
    subprocess.run([
        FFMPEG, "-i", src, "-vf", vf,
        "-c:v", "libx264", "-preset", config.FFMPEG_PRESET, "-crf", str(config.FFMPEG_CRF),
        "-c:a", audio, "-pix_fmt", "yuv420p", "-y", out_path,
    ], check=True, capture_output=True)
    return out_path


def burn_subtitles_and_effects(video_path, ass_path, out_path):
    return encode_video(video_path, out_path, effects_vf(ass_path), audio="copy")


def cut_audio(src: str, start: float, end: float, out_path: str, sample_rate: int = 16000) -> str:
    """Cut [start,end] of an audio/video track to a mono 16 kHz WAV.

    Used as the diarization input (pyannote expects ~16 kHz mono). Only runs on
    short per-clip segments, so the WAV stays small.
    """
    dur = end - start
    subprocess.run([
        FFMPEG, "-ss", str(start), "-t", str(dur), "-i", src,
        "-vn", "-ac", "1", "-ar", str(sample_rate), "-y", out_path,
    ], check=True, capture_output=True)
    return out_path


def make_thumbnail(video_path, out_path, at_seconds=1.0):
    subprocess.run([
        FFMPEG, "-ss", str(at_seconds), "-i", video_path,
        "-frames:v", "1", "-q:v", "2", "-y", out_path,
    ], check=True, capture_output=True)
    return out_path


def verify_output(video_path: str, expect_min_duration: float = 1.0) -> dict:
    """Confirm the rendered file has a video stream + audio stream and a sane
    duration. Returns a dict for logging; raises RuntimeError on a broken file.
    """
    if not os.path.exists(video_path) or os.path.getsize(video_path) == 0:
        raise RuntimeError(f"Output missing or empty: {video_path}")

    probe = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration", "-show_streams",
         "-of", "json", video_path],
        capture_output=True, text=True,
    )
    if probe.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {video_path}: {probe.stderr[-300:]}")

    try:
        import json as _json
        info = _json.loads(probe.stdout)
    except Exception:
        raise RuntimeError(f"Could not parse ffprobe output for {video_path}")

    streams = info.get("streams", [])
    has_video = any(s.get("codec_type") == "video" for s in streams)
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    dur = float(info.get("format", {}).get("duration") or 0.0)

    if not has_video:
        raise RuntimeError("No video stream in output")
    if not has_audio:
        raise RuntimeError("No audio stream in output")
    if dur < expect_min_duration:
        raise RuntimeError(f"Output duration {dur:.2f}s < expected {expect_min_duration}s")

    return {"has_video": has_video, "has_audio": has_audio, "duration": round(dur, 2)}


def probe_duration(video_path: str) -> float:
    """Duration in seconds via ffprobe (0.0 on failure)."""
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", video_path],
        capture_output=True, text=True,
    )
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


def convert_aspect(src: str, out_path: str, aspect: str) -> str:
    """Convert the native 9:16 render to 1:1 or 4:5 in ONE cheap final pass.

    Face-safe by construction: the vertical video is scaled to fit the target
    width and padded with a blurred version of itself (never a hard crop that
    could decapitate the speaker). 9:16 is a no-op copy.
    """
    dims = config.ASPECTS.get(aspect)
    if not dims or dims == (config.TARGET_WIDTH, config.TARGET_HEIGHT):
        shutil.copyfile(src, out_path)
        return out_path
    tw, th = dims
    vf = (
        f"split[bg][fg];"
        f"[bg]scale={tw}:{th}:force_original_aspect_ratio=increase,"
        f"crop={tw}:{th},gblur=sigma=20[bg];"
        f"[fg]scale={tw}:-2[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2"
    )
    return encode_video(src, out_path, vf, audio="copy")
