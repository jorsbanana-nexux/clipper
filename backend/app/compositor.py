"""Dynamic speaker switching (B5): render a clip as a sequence of layout
segments (single / duo) and crossfade between them.

Video-only segments are rendered per timeline window, normalised to a canonical
9:16 stream, then concatenated with `xfade`. The original clip audio is muxed
back at the end — so audio stays perfectly in sync regardless of layout changes.
"""
import shutil
import subprocess

from . import config, face_tracker
from .layout import LAYOUT_DUO

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"
CROSSFADE = 0.25  # seconds


def _probe_duration(path: str) -> float:
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True,
    )
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


def _cut_video(video_path: str, start: float, end: float, out_path: str) -> str:
    """Frame-accurate re-encode cut (B5 accuracy over `-c copy` speed)."""
    dur = end - start
    subprocess.run([
        FFMPEG, "-ss", str(start), "-t", str(dur), "-i", video_path,
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-avoid_negative_ts", "make_zero", "-y", out_path,
    ], check=True, capture_output=True)
    return out_path


def _normalize_video_only(video_path: str, out_path: str) -> str:
    """Canonical 9:16 stream, no audio, uniform fps/pix_fmt/sar for safe xfade."""
    TW, TH = config.TARGET_WIDTH, config.TARGET_HEIGHT
    subprocess.run([
        FFMPEG, "-i", video_path,
        "-vf", f"scale={TW}:{TH},setsar=1,fps=30,format=yuv420p",
        "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-y", out_path,
    ], check=True, capture_output=True)
    return out_path


def _render_segment(video_path: str, start: float, end: float, use_duo: bool, out_path: str) -> str:
    """Cut [start,end], reframe (single crop-follow / duo), normalise, drop audio."""
    cut = out_path + ".cut.mp4"
    _cut_video(video_path, start, end, cut)
    reframed = out_path + ".ref.mp4"
    if use_duo:
        face_tracker.reframe_duo(cut, reframed)
    else:
        samples = face_tracker.analyze_faces(cut)
        face_tracker.reframe_to_vertical(cut, reframed, samples)
    _normalize_video_only(reframed, out_path)
    return out_path


def _xfade_concat(seg_files: list[str], out_path: str) -> str:
    """Concatenate N normalised video-only segments with crossfade."""
    n = len(seg_files)
    if n == 0:
        raise RuntimeError("no segments to concat")
    if n == 1:
        subprocess.run(["cp", seg_files[0], out_path], check=True, capture_output=True)
        return out_path

    durations = [_probe_duration(p) for p in seg_files]
    cmd = [FFMPEG]
    for p in seg_files:
        cmd += ["-i", p]

    fc = []
    prev = "[0:v]"
    for i in range(1, n):
        offset = sum(durations[:i]) - i * CROSSFADE
        out_label = f"[x{i}]" if i < n - 1 else "[vout]"
        fc.append(
            f"{prev}[{i}:v]xfade=transition=fade:duration={CROSSFADE}:offset={offset:.4f}{out_label}"
        )
        prev = out_label

    cmd += ["-filter_complex", ";".join(fc), "-map", "[vout]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-y", out_path]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_path


def _mux_audio(video_no_audio: str, audio_src: str, out_path: str) -> str:
    """Attach the original clip's full audio (starts at 0) to the composed video."""
    subprocess.run([
        FFMPEG, "-i", video_no_audio, "-i", audio_src,
        "-map", "0:v:0", "-map", "1:a:0?", "-c:v", "copy", "-c:a", "aac",
        "-shortest", "-y", out_path,
    ], check=True, capture_output=True)
    return out_path


def render_dynamic_clip(raw_path: str, timeline: list[dict], out_path: str) -> str:
    """Compose a clip from a layout timeline (relative to clip start = 0).

    timeline: [{start, end, layout}]  (times relative to raw_path start)
    """
    seg_files = []
    for i, seg in enumerate(timeline):
        seg_out = out_path + f".seg{i}.mp4"
        _render_segment(
            raw_path,
            seg["start"], seg["end"],
            seg.get("layout") == LAYOUT_DUO,
            seg_out,
        )
        seg_files.append(seg_out)

    video_only = out_path + ".video.mp4"
    _xfade_concat(seg_files, video_only)
    _mux_audio(video_only, raw_path, out_path)

    # cleanup intermediate files
    for p in seg_files:
        try:
            os.remove(p)
        except OSError:
            pass
    for suf in (".video.mp4",):
        try:
            os.remove(out_path + suf)
        except OSError:
            pass
    return out_path


def rel_timeline(timeline: list[dict], clip_start: float) -> list[dict]:
    """Shift absolute layout timeline to clip-relative (0-based) times."""
    out = []
    for seg in timeline:
        out.append({
            "start": max(0.0, seg["start"] - clip_start),
            "end": seg["end"] - clip_start,
            "layout": seg["layout"],
        })
    return [s for s in out if s["end"] > s["start"]]
