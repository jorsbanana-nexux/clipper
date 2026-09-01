"""Face tracking + smart reframe to 9:16 (1080x1920)."""
import os
import shutil
import subprocess
from dataclasses import dataclass

import cv2
import numpy as np

from . import config

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"


@dataclass
class FaceSample:
    t: float
    cx: float


def _detect_faces_mediapipe(frame_bgr):
    import mediapipe as mp
    mp_face = mp.solutions.face_detection
    with mp_face.FaceDetection(model_selection=1, min_detection_confidence=0.5) as det:
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        res = det.process(rgb)
        if not res.detections:
            return []
        h, w = frame_bgr.shape[:2]
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


def _dominant_face(faces):
    if not faces:
        return None
    faces = sorted(faces, key=lambda f: -f[1])
    return faces[0][0]


def analyze_faces(video_path: str, sample_interval: float = 0.5) -> list[FaceSample]:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return []
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, int(fps * sample_interval))
    samples = []
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
            cx = _dominant_face(faces)
            if cx is not None:
                samples.append(FaceSample(t=t, cx=cx))
        idx += 1
    cap.release()
    return samples


def _smooth(samples, window=5):
    if not samples:
        return []
    cxs = [s.cx for s in samples]
    out = []
    for i, s in enumerate(samples):
        lo = max(0, i - window // 2)
        hi = min(len(cxs), i + window // 2 + 1)
        out.append(FaceSample(t=s.t, cx=float(np.mean(cxs[lo:hi]))))
    return out


def _cx_at(samples, t):
    if not samples:
        return 0.5
    if t <= samples[0].t:
        return samples[0].cx
    if t >= samples[-1].t:
        return samples[-1].cx
    for i in range(len(samples) - 1):
        a, b = samples[i], samples[i + 1]
        if a.t <= t <= b.t:
            if b.t == a.t:
                return a.cx
            f = (t - a.t) / (b.t - a.t)
            return a.cx + (b.cx - a.cx) * f
    return samples[-1].cx


def reframe_to_vertical(video_path, output_path, samples):
    if samples:
        return _reframe_crop_follow(video_path, output_path, samples)
    return _reframe_blur_pad(video_path, output_path)


def _reframe_crop_follow(video_path, output_path, samples):
    smooth = _smooth(samples)
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    TW, TH = config.TARGET_WIDTH, config.TARGET_HEIGHT

    scale = TH / H
    sw = int(W * scale)
    max_crop_x = sw - TW

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    vw = cv2.VideoWriter(output_path + ".v.mp4", fourcc, fps, (TW, TH))
    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        t = idx / fps
        cx = _cx_at(smooth, t)
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
