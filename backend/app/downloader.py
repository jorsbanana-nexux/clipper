"""Video download and segment extraction via yt-dlp.

Strategy (matches the "download only selected parts" requirement):
1. download_audio_only  -> pull just the audio track + metadata (light).
2. download_segment     -> pull ONLY a time range of the video for each clip.
"""
import os
import shutil
import subprocess
from pathlib import Path

import yt_dlp

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"


def _quiet_opts(extra: dict) -> dict:
    opts = {"quiet": True, "no_warnings": True, "noplaylist": True}
    opts.update(extra)
    return opts


def extract_metadata(url: str) -> dict:
    with yt_dlp.YoutubeDL(_quiet_opts({"skip_download": True})) as ydl:
        return ydl.extract_info(url, download=False)


def download_audio_only(url: str, out_dir: str) -> tuple[str, dict]:
    """Download only the audio track (mp3) + return (path, info_dict)."""
    os.makedirs(out_dir, exist_ok=True)
    outtmpl = os.path.join(out_dir, "audio.%(ext)s")
    opts = _quiet_opts({
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "128"}],
    })
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
    candidates = [p for p in Path(out_dir).glob("audio.*")]
    if not candidates:
        raise RuntimeError("Audio download produced no file")
    return str(candidates[0]), info


def _range_callback(start: float, end: float):
    def ranges(info_dict, ydl):
        return [{"start_time": start, "end_time": end}]
    return ranges


def download_segment(url: str, start: float, end: float, out_dir: str) -> str:
    """Download ONLY [start, end] seconds of the video. Falls back to full+cut."""
    os.makedirs(out_dir, exist_ok=True)
    outtmpl = os.path.join(out_dir, "seg.%(ext)s")
    try:
        opts = _quiet_opts({
            "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
            "outtmpl": outtmpl,
            "download_ranges": _range_callback(start, end),
            "force_keyframes_at_cuts": True,
            "merge_output_format": "mp4",
        })
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        segs = [p for p in Path(out_dir).glob("seg.*")]
        if segs:
            return str(segs[0])
        raise RuntimeError("range download produced no file")
    except Exception:
        return download_full_and_cut(url, start, end, out_dir)


def download_full_and_cut(url: str, start: float, end: float, out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    outtmpl = os.path.join(out_dir, "full.%(ext)s")
    opts = _quiet_opts({
        "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        "outtmpl": outtmpl,
        "merge_output_format": "mp4",
    })
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
    full = [p for p in Path(out_dir).glob("full.*") if p.suffix in (".mp4", ".webm", ".mkv")][0]
    cut = os.path.join(out_dir, "cut.mp4")
    dur = end - start
    subprocess.run([
        FFMPEG, "-ss", str(start), "-t", str(dur), "-i", str(full),
        "-c", "copy", "-avoid_negative_ts", "make_zero", "-y", cut,
    ], check=True, capture_output=True)
    return cut
