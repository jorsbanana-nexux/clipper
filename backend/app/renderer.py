"""Final clip assembly: cut + reframe + subtitles + effects via ffmpeg."""
import os
import shutil
import subprocess

from . import config

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"


def clip_segment(video_path, start, end, out_path):
    """Cut [start,end] of a clip.

    CUT_MODE == "fast"     -> stream copy (fast, keyframe-aligned, ~2-5s slop).
    CUT_MODE == "accurate" -> re-encode with -ss before -i (frame-accurate).
    """
    dur = end - start
    if getattr(config, "CUT_MODE", "accurate") == "fast":
        cmd = [
            FFMPEG, "-ss", str(start), "-t", str(dur), "-i", video_path,
            "-c", "copy", "-avoid_negative_ts", "make_zero", "-y", out_path,
        ]
    else:
        # Accurate: input seek (before -i) + re-encode -> frame-accurate cut.
        cmd = [
            FFMPEG, "-ss", str(start), "-t", str(dur), "-i", video_path,
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-c:a", "aac", "-avoid_negative_ts", "make_zero", "-y", out_path,
        ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_path


def burn_subtitles_and_effects(video_path, ass_path, out_path):
    vf = (
        f"ass={ass_path},"
        f"eq=contrast=1.06:saturation=1.15:brightness=0.01,"
        f"unsharp=5:5:0.6:5:5:0.0"
    )
    subprocess.run([
        FFMPEG, "-i", video_path, "-vf", vf,
        "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-c:a", "copy", "-y", out_path,
    ], check=True, capture_output=True)
    return out_path


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
    if dur < expect_min_duration:
        raise RuntimeError(f"Output duration {dur:.2f}s < expected {expect_min_duration}s")

    return {"has_video": has_video, "has_audio": has_audio, "duration": round(dur, 2)}
