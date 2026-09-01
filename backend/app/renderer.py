"""Final clip assembly: cut + reframe + subtitles + effects via ffmpeg."""
import shutil
import subprocess

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"


def clip_segment(video_path, start, end, out_path):
    dur = end - start
    subprocess.run([
        FFMPEG, "-ss", str(start), "-t", str(dur), "-i", video_path,
        "-c", "copy", "-avoid_negative_ts", "make_zero", "-y", out_path,
    ], check=True, capture_output=True)
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
