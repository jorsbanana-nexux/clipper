"""Face tracking + smart reframe to 9:16 (1080x1920), with multi-face support.

v0.2 additions:
- detect MULTIPLE faces per frame (sorted by size / confidence)
- track the movement of each face across time (for split-screen & dynamic switch)
- active-speaker selection is delegated to diarization (when available)
- single-face crop-follow (v0.1) still works as the default; blur-pad fallback
  when no face is detected.

Uses MediaPipe first, with OpenCV Haar cascade as a fallback detector.
"""
import os
import shutil
import subprocess
from dataclasses import dataclass, field

import cv2
import numpy as np

from . import config

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"


@dataclass
class FaceSample:
    t: float
    cx: float                          # normalised 0..1 (centre x)
    size: float = 0.0                  # normalised face width 0..1
    confidence: float = 0.0


@dataclass
class FrameFaces:
    """All faces detected at one timestamp."""
    t: float
    faces: list[FaceSample] = field(default_factory=list)


def _detect_faces_mediapipe(frame_bgr):
    import mediapipe as mp
    mp_face = mp.solutions.face_detection
    with mp_face.FaceDetection(model_selection=1, min_detection_confidence=0.5) as det:
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        res = det.process(rgb)
        if not res.detections:
            return []
        out = []
        for d in res.detections:
            bb = d.location_data.relative_bounding_box
            cx = bb.xmin + bb.width / 2
            out.append((cx, bb.width, float(d.score[0])))
        return out


def _detect_faces_haar(frame_bgr):
    casc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    h, w = frame_bgr.shape[:2]
    faces = casc.detectMultiScale(gray, 1.1, 5, minSize=(30, 30))
    out = []
    for (x, y, fw, fh) in faces:
        cx = (x + fw / 2) / w
        out.append((cx, fw / w, 1.0))
    return out


def _sort_faces(faces: list[tuple[float, float, float]]) -> list[FaceSample]:
    """Sort by size (dominant first), keep max 3, normalise to FaceSample."""
    faces = sorted(faces, key=lambda f: -f[1])[:3]
    return [FaceSample(t=0.0, cx=cx, size=size, confidence=conf) for cx, size, conf in faces]


def analyze_faces(video_path: str, sample_interval: float = 0.5) -> list[FaceSample]:
    """DEPRECATED alias kept for v0.1 callers — returns dominant face only."""
    frames = analyze_faces_all(video_path, sample_interval)
    out = []
    for fr in frames:
        # per frame, pick the largest face (closest to camera)
        faces = sorted(fr.faces, key=lambda f: -f.size)
        if faces:
            out.append(FaceSample(t=fr.t, cx=faces[0].cx, size=faces[0].size, confidence=faces[0].confidence))
    return out


def analyze_faces_all(video_path: str, sample_interval: float = 0.5) -> list[FrameFaces]:
    """Return per-frame face detections (all faces) for multi-speaker layouts."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return []
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, int(fps * sample_interval))
    frames: list[FrameFaces] = []
    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % step == 0:
            t = idx / fps
            faces = _detect_faces_mediapipe(frame)
            if not faces:
                faces = _detect_faces_haar(frame)
            if faces:
                dets = _sort_faces(faces)
                for d in dets:
                    d.t = t
                frames.append(FrameFaces(t=t, faces=dets))
        idx += 1
    cap.release()
    return frames


def _smooth_series(cxs: list[float], window: int = 5) -> list[float]:
    if not cxs:
        return []
    out = []
    for i in range(len(cxs)):
        lo = max(0, i - window // 2)
        hi = min(len(cxs), i + window // 2 + 1)
        out.append(float(np.mean(cxs[lo:hi])))
    return out


def _xcx_at(t, ts: list[float], cxs: list[float]) -> float:
    """Interpolate a centre-x series at time t."""
    if not ts:
        return 0.5
    if t <= ts[0]:
        return cxs[0]
    if t >= ts[-1]:
        return cxs[-1]
    for i in range(len(ts) - 1):
        a, b = ts[i], ts[i + 1]
        if a <= t <= b:
            f = (t - b + (b - a)) / (b - a) if b != a else 0
            # linear interpolation
            return cxs[i] + (cxs[i + 1] - cxs[i]) * ((t - a) / (b - a))
    return cxs[-1]


def reframe_to_vertical(video_path: str, output_path: str, samples: list[FaceSample]) -> str:
    """Single-speaker crop-follow (v0.1 behavior)."""
    if samples:
        return _reframe_crop_follow(video_path, output_path, samples)
    return _reframe_blur_pad(video_path, output_path)


def reframe_duo(video_path: str, output_path: str) -> str:
    """Two-speaker split-screen: stacked top & bottom bands (9:16)."""
    TW, TH = config.TARGET_WIDTH, config.TARGET_HEIGHT
    band_h = TH // 2
    vf = (
        f"[0:v]split=2[top][bot];"
        f"[top]scale={TW}:{band_h}:force_original_aspect_ratio=increase,"
        f"crop={TW}:{band_h},gblur=sigma=2[top];"
        f"[bot]scale={TW}:{band_h}:force_original_aspect_ratio=increase,"
        f"crop={TW}:{band_h},gblur=sigma=2[bot];"
        f"[top][bot]vstack=inputs=2"
    )
    subprocess.run([
        FFMPEG, "-i", video_path, "-vf", vf,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-c:a", "copy", "-y", output_path,
    ], check=True, capture_output=True)
    return output_path


def _reframe_crop_follow(video_path, output_path, samples):
    ts = [s.t for s in samples]
    cxs = [s.cx for s in samples]
    cxs = _smooth_series(cxs)
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    TW, TH = config.TARGET_WIDTH, config.TARGET_HEIGHT

    scale = TH / H
    sw = int(W * scale)
    max_crop_x = max(0, sw - TW)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    vw = cv2.VideoWriter(output_path + ".v.mp4", fourcc, fps, (TW, TH))
    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        t = idx / fps
        cx = _xcx_at(t, ts, cxs)
        cx_scaled = cx * sw
        crop_x = int(np.clip(cx_scaled - TW / 2, 0, max_crop_x))
        scaled = cv2.resize(frame, (sw, TH), interpolation=cv2.INTER_AREA)
        cropped = scaled[:, crop_x:crop_x + TW]
        vw.write(cropped)
        idx += 1
    cap.release()
    vw.release()
    _mux_audio(video_path, output_path + ".v.mp4", output_path)
    os.remove(output_path + ".v.mp4")
    return output_path


def _reframe_blur_pad(video_path, output_path):
    TW, TH = config.TARGET_WIDTH, config.TARGET_HEIGHT
    vf = (
        f"split[bg][fg];"
        f"[bg]scale={TW}:{TH}:force_original_aspect_ratio=increase,crop={TW}:{TH},"
        f"gblur=sigma=20[bg];"
        f"[fg]scale={TW}:-2[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2"
    )
    subprocess.run([
        FFMPEG, "-i", video_path, "-vf", vf,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-c:a", "aac", "-y", output_path,
    ], check=True, capture_output=True)
    return output_path


def _mux_audio(video_src, video_no_audio, output):
    subprocess.run([
        FFMPEG, "-i", video_no_audio, "-i", video_src,
        "-map", "0:v:0", "-map", "1:a:0?", "-c:v", "libx264", "-preset", "fast",
        "-crf", "23", "-c:a", "aac", "-shortest", "-y", output,
    ], check=True, capture_output=True)
