"""Video download and segment extraction via yt-dlp.

Strategy (matches the "download only selected parts" requirement):
1. fetch_captions        -> transcript from YouTube captions (0 audio download).
2. download_audio_only   -> full audio track (fallback when no captions).
3. download_segment      -> only a time range of the VIDEO for each clip.
4. download_audio_segment-> only a time range of the AUDIO (per-clip Whisper).
"""
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import urllib.request
from pathlib import Path

import yt_dlp

from . import config

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"


def _ffmpeg_cut(src: str, start: float, end: float, out: str) -> str:
    """Cut [start, end] honoring config.CUT_MODE (A1).

    "accurate" -> re-encode with -ss before -i (frame-accurate, default).
    "fast"     -> stream copy (keyframe-aligned, faster, ~2-5s slop).
    """
    dur = end - start
    if getattr(config, "CUT_MODE", "accurate") == "fast":
        cmd = [
            FFMPEG, "-ss", str(start), "-t", str(dur), "-i", src,
            "-c", "copy", "-avoid_negative_ts", "make_zero", "-y", out,
        ]
    else:
        cmd = [
            FFMPEG, "-ss", str(start), "-t", str(dur), "-i", src,
            "-c:v", "libx264", "-preset", config.FFMPEG_PRESET, "-crf", str(config.FFMPEG_CRF),
            "-c:a", "aac", "-avoid_negative_ts", "make_zero", "-y", out,
        ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out


def precise_trim(src: str, start: float, end: float, out: str) -> str:
    """Re-encode trim to the EXACT [start, end] window (frame-accurate).

    yt-dlp's range download / stream-copy can land on a keyframe PAST the chosen
    end time, so the clip keeps running after the point and drags in irrelevant
    trailing content. This trims to the precise window so the clip stops crisply
    at the punchline.
    """
    dur = max(0.05, end - start)
    cmd = [
        FFMPEG, "-i", src, "-ss", str(start), "-t", str(dur),
        "-c:v", "libx264", "-preset", config.FFMPEG_PRESET, "-crf", str(config.FFMPEG_CRF),
        "-c:a", "aac", "-avoid_negative_ts", "make_zero", "-y", out,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out


def _quiet_opts(extra: dict) -> dict:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "retries": getattr(config, "YDL_RETRIES", 3),
    }
    if getattr(config, "YDL_COOKIES_FILE", ""):
        opts["cookiefile"] = config.YDL_COOKIES_FILE
    if getattr(config, "YDL_PROXY", ""):
        opts["proxy"] = config.YDL_PROXY
    opts.update(extra)
    return opts


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


# Full-download fallback cache: when a range download fails, the FULL source
# is downloaded ONCE per URL (per process) and every later clip cuts from the
# cached file. BUGFIX: previously EACH clip re-downloaded the full video
# (N clips -> up to N x ~1 GB of downloads).
_FULL_CACHE: dict[str, str] = {}
_FULL_CACHE_LOCK = threading.Lock()


def _full_download_cached(url: str, fmt: str, prefix: str) -> str:
    with _FULL_CACHE_LOCK:
        key = f"{prefix}:{url}"
        cached = _FULL_CACHE.get(key)
        if cached and os.path.exists(cached):
            return cached
        cache_dir = os.path.join(tempfile.gettempdir(), "clipper_cache")
        os.makedirs(cache_dir, exist_ok=True)
        h = hashlib.sha1(url.encode()).hexdigest()[:16]
        outtmpl = os.path.join(cache_dir, f"{prefix}_{h}.%(ext)s")
        opts = _quiet_opts({"format": fmt, "outtmpl": outtmpl,
                            "merge_output_format": "mp4"})
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        found = [p for p in Path(cache_dir).glob(f"{prefix}_{h}.*")
                 if p.suffix in (".mp4", ".webm", ".mkv", ".m4a", ".opus", ".mp3")]
        if not found:
            raise RuntimeError("Full download produced no usable file")
        path = str(found[0])
        _FULL_CACHE[key] = path
        return path


def download_full_and_cut(url: str, start: float, end: float, out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    full = _full_download_cached(
        url, "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best", "full")
    cut = os.path.join(out_dir, "cut.mp4")
    _ffmpeg_cut(full, start, end, cut)
    return cut



# ---- captions (no audio download) ----

def _parse_ts(ts: str) -> float:
    parts = ts.strip().split(":")
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s.replace(",", "."))
    m, s = parts
    return int(m) * 60 + float(s.replace(",", "."))


def _strip_tags(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def _parse_vtt_srt(content: str) -> list[dict]:
    # BUGFIX: YouTube auto-caption VTT uses MM:SS.mmm (no hours) for videos
    # under 1 hour — the old regex required HH:MM:SS and matched nothing.
    ts_re = re.compile(
        r"(\d{1,2}:\d{2}:\d{2}[.,]\d{3}|\d{1,2}:\d{2}[.,]\d{3})"
        r"\s*-->\s*"
        r"(\d{1,2}:\d{2}:\d{2}[.,]\d{3}|\d{1,2}:\d{2}[.,]\d{3})")
    segments = []
    lines = content.splitlines()
    i = 0
    while i < len(lines):
        m = ts_re.search(lines[i])
        if m:
            start = _parse_ts(m.group(1))
            end = _parse_ts(m.group(2))
            i += 1
            texts = []
            while i < len(lines) and lines[i].strip() and not ts_re.search(lines[i]):
                t = _strip_tags(lines[i])
                if t:
                    texts.append(t)
                i += 1
            text = " ".join(texts)
            if text:
                segments.append({"start": start, "end": end, "text": text})
        else:
            i += 1
    return segments


def _parse_srv(content: str) -> list[dict]:
    """Parse YouTube srv1/srv3 timed-text XML (auto-captions)."""
    segments = []
    # srv1: <text start="12.08" dur="2.5">hello</text>
    for m in re.finditer(
            r'<text start="([\d.]+)"(?:\s+dur="([\d.]+)")?[^>]*>(.*?)</text>',
            content, re.S):
        start = float(m.group(1))
        dur = float(m.group(2) or 2.0)
        text = _strip_tags(m.group(3))
        if text:
            segments.append({"start": start, "end": start + dur, "text": text})
    if segments:
        return segments
    # srv3: <p t="12080" d="2560"><s>hello</s></p>
    for m in re.finditer(
            r'<p[^>]*\bt="(\d+)"(?:\s+d="(\d+)")?[^>]*>(.*?)</p>',
            content, re.S):
        start = int(m.group(1)) / 1000.0
        dur = int(m.group(2) or 2000) / 1000.0
        text = _strip_tags(m.group(3))
        if text:
            segments.append({"start": start, "end": start + dur, "text": text})
    return segments


def _parse_json3(content: str) -> list[dict]:
    """Parse YouTube json3 caption JSON (auto-captions)."""
    try:
        data = json.loads(content)
    except Exception:
        return []
    segments = []
    for ev in data.get("events", []):
        segs = ev.get("segs") or []
        text = "".join(s.get("utf8", "") for s in segs if s.get("utf8")).strip()
        if not text:
            continue
        start = (ev.get("tStartMs") or 0) / 1000.0
        dur = (ev.get("dDurationMs") or 2000) / 1000.0
        segments.append({"start": start, "end": start + dur, "text": text})
    return segments


def fetch_captions(url: str):
    '''Return (segments, lang, title) from YouTube captions (0 audio download).
    Returns (None, None, None) when captions cannot be fetched or parsed.'''
    try:
        with yt_dlp.YoutubeDL(_quiet_opts({"skip_download": True})) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception:
        return None, None, None

    for group_key in ("subtitles", "automatic_captions"):
        subs = info.get(group_key) or {}
        hinted = (info.get("language") or "").lower()
        langs = sorted(
            list(subs.keys()),
            key=lambda l: (0 if hinted and l.lower().startswith(hinted.split("-")[0]) else (1 if "original" in l.lower() else 2)),
        )
        for lang in langs:
            for entry in subs.get(lang, []):
                ext = entry.get("ext")
                if ext not in ("vtt", "srt", "srv1", "srv3", "json3"):
                    continue
                sub_url = entry.get("url")
                if not sub_url:
                    continue
                try:
                    with urllib.request.urlopen(sub_url, timeout=30) as r:
                        content = r.read().decode("utf-8", errors="replace")
                    # BUGFIX: YouTube auto-captions are often ONLY offered as
                    # json3/srv1/srv3 — filtering them out made fetch_captions
                    # fail and forced the expensive full-audio fallback.
                    if ext == "json3":
                        segs = _parse_json3(content)
                    elif ext in ("srv1", "srv3"):
                        segs = _parse_srv(content)
                    else:
                        segs = _parse_vtt_srt(content)
                    if segs:
                        return segs, (lang.split("-")[0].lower() if lang else None), info.get("title")
                except Exception:
                    continue
    return None, None, None


def download_audio_segment(url: str, start: float, end: float, out_dir: str) -> str:
    '''Download ONLY [start,end] of the audio (for per-clip Whisper subtitles).'''
    os.makedirs(out_dir, exist_ok=True)
    outtmpl = os.path.join(out_dir, "aseg.%(ext)s")
    try:
        opts = _quiet_opts({
            "format": "bestaudio/best",
            "outtmpl": outtmpl,
            "download_ranges": _range_callback(start, end),
            "force_keyframes_at_cuts": True,
        })
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        segs = [p for p in Path(out_dir).glob("aseg.*")]
        if segs:
            return str(segs[0])
        raise RuntimeError("audio range download produced no file")
    except Exception:
        return download_full_audio_and_cut(url, start, end, out_dir)


def download_full_audio_and_cut(url: str, start: float, end: float, out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    # BUGFIX: shares the per-process full-download cache — the full audio is
    # fetched once per URL instead of once per clip.
    full = _full_download_cached(url, "bestaudio/best", "afull")
    cut = os.path.join(out_dir, f"acut{Path(full).suffix}")
    dur = end - start
    subprocess.run([
        FFMPEG, "-ss", str(start), "-t", str(dur), "-i", full,
        "-c", "copy", "-y", cut,
    ], check=True, capture_output=True)
    return cut
