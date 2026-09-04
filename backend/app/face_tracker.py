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
from . import renderer

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"


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


def _make_mediapipe_detector():
    """Instantiate the MediaPipe face detector once (model load is expensive)."""
    try:
        import mediapipe as mp
        return mp.solutions.face_detection.FaceDetection(
            model_selection=1, min_detection_confidence=0.5)
    except Exception:
        return None


def _make_haar_cascade():
    """Load the OpenCV Haar cascade once, returning None if unavailable."""
    try:
        casc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        return casc if not casc.empty() else None
    except Exception:
        return None


def _detect_faces_mediapipe(frame_rgb, det) -> list:
    try:
        res = det.process(frame_rgb)
    except Exception:
        return []  # OpenCV/MediaPipe hiccup -> treat as no face
    if not res.detections:
        return []
    out = []
    for d in res.detections:
        bb = d.location_data.relative_bounding_box
        cx = bb.xmin + bb.width / 2
        out.append((cx, bb.width, float(d.score[0])))
    return out


def _detect_faces_haar(frame_rgb, casc) -> list:
    try:
        gray = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2GRAY)
        h, w = frame_rgb.shape[:2]
        faces = casc.detectMultiScale(gray, 1.1, 5, minSize=(20, 20))
    except Exception:
        return []
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
    """Return the DOMINANT face per sample (single-speaker crop-follow helper).

    Use analyze_faces_all() for multi-speaker layouts. Both share the same
    underlying detection; this one just collapses each frame to the largest face.
    """
    frames = analyze_faces_all(video_path, sample_interval)
    out = []
    for fr in frames:
        # per frame, pick the largest face (closest to camera)
        faces = sorted(fr.faces, key=lambda f: -f.size)
        if faces:
            out.append(FaceSample(t=fr.t, cx=faces[0].cx, size=faces[0].size, confidence=faces[0].confidence))
    return out


def analyze_faces_all(video_path: str, sample_interval: float = 0.5) -> list[FrameFaces]:
    """Detect faces on a sparse, downscaled frame stream from ffmpeg.

    Decodes only a few fps at small resolution via system ffmpeg -> fast on CPU
    and no cv2.VideoCapture (removes the slow full-frame loop AND the
    'Unknown C++ exception from OpenCV' source). MediaPipe first, cv2 Haar
    fallback on the same small frames. Normalised cx (0..1) is scale-invariant.
    """
    mp_det = _make_mediapipe_detector()
    haar_casc = _make_haar_cascade()
    frames: list[FrameFaces] = []

    W, H = _probe_dims(video_path)
    if W <= 0 or H <= 0:
        return []
    out_fps = 1.0 / max(0.1, sample_interval)   # e.g. 2 fps
    scale = min(1.0, 640.0 / max(W, 1))
    dw = max(2, int(W * scale))
    dh = max(2, int(H * scale))
    vf = f"scale={dw}:{dh},fps={out_fps}"
    frame_bytes = dw * dh * 3

    proc = None
    try:
        proc = subprocess.Popen(
            [FFMPEG, "-v", "error", "-i", video_path, "-vf", vf,
             "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        idx = 0
        while True:
            try:
                raw = proc.stdout.read(frame_bytes)
            except Exception:
                raw = None
            if not raw or len(raw) < frame_bytes:
                break
            frame = np.frombuffer(raw, np.uint8).reshape((dh, dw, 3))
            t = idx / out_fps
            try:
                faces = _detect_faces_mediapipe(frame, mp_det) if mp_det is not None else []
                if not faces and haar_casc is not None:
                    faces = _detect_faces_haar(frame, haar_casc)
            except Exception:
                faces = []  # any detection failure on this frame -> skip
            if faces:
                dets = _sort_faces(faces)
                for d in dets:
                    d.t = t
                frames.append(FrameFaces(t=t, faces=dets))
            idx += 1
    except Exception:
        frames = []
    finally:
        if proc is not None:
            try:
                if proc.stdout is not None:
                    proc.stdout.close()
                proc.kill()
            except Exception:
                pass
        try:
            if mp_det is not None:
                mp_det.close()
        except Exception:
            pass
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


def _ema_smooth(cxs: list[float], alpha: float = 0.28) -> list[float]:
    """Bidirectional EMA (forward pass + backward pass, averaged).

    A single forward EMA always LAGS behind fast speaker changes — the camera
    arrives late and the pan feels stiff. The full sample list is known before
    rendering, so we also smooth BACKWARD: the two passes cancel most of the
    lag while keeping the glide. Pans now ease in and out around each speaker
    change instead of jerking. alpha 0..1; lower = smoother, higher = snappier.
    """
    if not cxs:
        return []
    fwd = [cxs[0]]
    for v in cxs[1:]:
        fwd.append(fwd[-1] + alpha * (v - fwd[-1]))
    bwd = [cxs[-1]]
    for v in reversed(cxs[:-1]):
        bwd.append(bwd[-1] + alpha * (v - bwd[-1]))
    bwd.reverse()
    return [(f + b) / 2.0 for f, b in zip(fwd, bwd)]


def has_two_speakers(video_path: str, min_ratio: float = 0.35,
                     sample_interval: float = 0.5) -> bool:
    """True when two faces are visible in >= min_ratio of sampled frames.
    Used as a diarization-free fallback to auto-enable split-screen duo."""
    frames = analyze_faces_all(video_path, sample_interval)
    if not frames:
        return False
    two = sum(1 for f in frames if len(f.faces) >= 2)
    return two / len(frames) >= min_ratio


def face_counts_over_time(video_path: str, sample_interval: float = 0.5) -> list[tuple]:
    """Return [(t, n_faces)] sampled over the clip (local timeline 0..duration).

    Used to decide, per time-window, whether two people are ACTUALLY visible.
    Timing from diarization says *when someone talks*; this says *whether both
    are on screen* — the two can differ when the camera cuts between close-ups.
    """
    frames = analyze_faces_all(video_path, sample_interval)
    return [(f.t, len(f.faces)) for f in frames]



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
            if b == a:
                return cxs[i]
            ratio = (t - a) / (b - a)
            return cxs[i] + (cxs[i + 1] - cxs[i]) * ratio
    return cxs[-1]


def reframe_to_vertical(video_path: str, output_path: str, samples: list[FaceSample],
                        ass_path: str | None = None) -> str:
    """Single-speaker crop-follow (v0.1 behavior). When `ass_path` is given, the
    subtitle + effects are folded into the SAME encode pass (faster batch)."""
    if samples:
        return _reframe_crop_follow(video_path, output_path, samples, ass_path)
    return _reframe_blur_pad(video_path, output_path, ass_path)


def _probe_dims(video_path: str) -> tuple[int, int]:
    """Return (width, height) of the first video stream via ffprobe."""
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", video_path],
        capture_output=True, text=True,
    )
    try:
        w, h = out.stdout.strip().split(",")
        return int(w), int(h)
    except Exception:
        return 1920, 1080


def reframe_duo(video_path: str, output_path: str, ass_path: str | None = None) -> str:
    """Two-speaker split-screen -> stacked top & bottom bands (9:16).

    Splits the source into LEFT and RIGHT halves (for two speakers sitting
    side-by-side), scales each half to a 1080x960 band, then stacks them
    vertically. When `ass_path` is given, subtitle + effects are folded into the
    SAME encode pass (faster batch). Audio is copied (timing unchanged).
    """
    TW, TH = config.TARGET_WIDTH, config.TARGET_HEIGHT
    band_h = TH // 2
    W, H = _probe_dims(video_path)
    if W < 8 or H < 8:
        return _reframe_blur_pad(video_path, output_path, ass_path)
    half_w = W // 2

    vf = (
        f"[0:v]split=2[left][right];"
        f"[left]crop={half_w}:{H}:0:0,"
        f"scale={TW}:{band_h}:force_original_aspect_ratio=increase,"
        f"crop={TW}:{band_h}[left];"
        f"[right]crop={W-half_w}:{H}:{half_w}:0,"
        f"scale={TW}:{band_h}:force_original_aspect_ratio=increase,"
        f"crop={TW}:{band_h}[right];"
        f"[left][right]vstack=inputs=2"
    )
    if ass_path:
        vf += "," + renderer.effects_vf(ass_path)

    subprocess.run([
        FFMPEG, "-i", video_path, "-vf", vf,
        "-c:v", "libx264", "-preset", config.FFMPEG_PRESET, "-crf", str(config.FFMPEG_CRF),
        "-c:a", "copy", "-y", output_path,
    ], check=True, capture_output=True)
    return output_path


def _reframe_crop_follow(video_path, output_path, samples, ass_path=None):
    """Face-follow crop to 9:16 via ffmpeg PIPE decode + cv2 crop + ffmpeg encode.

    Root cause of "Unknown C++ exception from OpenCV": reading/writing frames
    through cv2.VideoCapture / cv2.VideoWriter — OpenCV's bundled decoder crashes
    on certain H.264/VP9 frames. Here we DECODE with system ffmpeg (reliable) to
    raw BGR frames, process with cv2 on guaranteed-valid numpy arrays, then ENCODE
    with system ffmpeg. Audio is muxed back from the source (stays in sync).

    Framing improvements (from evaluation):
    - ZOOM-OUT: the subject is placed at ~FACE_ZOOM of the canvas height on a
      blurred background with headroom, so the face is smaller and comfortable
      instead of an aggressive full-height closeup.
    - SMOOTH, DIRECTED pans: centre-x is EMA-smoothed (FACE_SMOOTH_ALPHA) and
      per-frame movement is clamped, so the camera glides to the speaker and
      never jerks or lags behind.
    - Blur-pad is used only when the source is geometrically too narrow to crop.
    """
    if not samples:
        return _reframe_blur_pad(video_path, output_path)
    ts = [s.t for s in samples]
    cxs = _ema_smooth([s.cx for s in samples], config.FACE_SMOOTH_ALPHA)
    W, H = _probe_dims(video_path)
    if W <= 0 or H <= 0:
        return _reframe_blur_pad(video_path, output_path)
    TW, TH = config.TARGET_WIDTH, config.TARGET_HEIGHT
    zoom = config.FACE_ZOOM
    if zoom <= 0.0 or zoom > 1.0:
        zoom = 1.0
    headroom = float(np.clip(config.FACE_HEADROOM, 0.0, 0.5))

    # Full-height 9:16 region (same aspect as output -> no distortion).
    region_w = int(round(H * TW / TH))
    if region_w < 8:
        return _reframe_blur_pad(video_path, output_path)
    max_crop_x = W - region_w
    if max_crop_x < 0:
        return _reframe_blur_pad(video_path, output_path)

    fg_w = max(8, int(round(TW * zoom)))
    fg_h = max(8, int(round(TH * zoom)))
    fg_x = max(0, (TW - fg_w) // 2)
    fg_y = int((TH - fg_h) * headroom)

    fps = _probe_fps(video_path)
    frame_bytes = W * H * 3
    vpath = output_path + ".v.mp4"

    dec = subprocess.Popen(
        [FFMPEG, "-i", video_path, "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    enc = subprocess.Popen(
        [FFMPEG, "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
         "-s", f"{TW}x{TH}", "-r", str(fps), "-i", "-",
         "-vf", renderer.effects_vf(ass_path),
         "-threads", "0", "-c:v", "libx264", "-preset", config.FFMPEG_PRESET,
         "-crf", str(config.FFMPEG_CRF), "-pix_fmt", "yuv420p", vpath],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    idx = 0
    prev_crop = None
    max_move = max(2.0, region_w * 0.18)
    try:
        while True:
            raw = dec.stdout.read(frame_bytes)
            if not raw or len(raw) < frame_bytes:
                break
            frame = np.frombuffer(raw, np.uint8).reshape((H, W, 3))
            t = idx / fps
            cx = _xcx_at(t, ts, cxs)
            target = int(np.clip(cx * W - region_w / 2, 0, max_crop_x))
            target -= target % 2
            if prev_crop is not None:
                target = int(np.clip(target, prev_crop - max_move, prev_crop + max_move))
                target -= target % 2
            prev_crop = target

            region = frame[:, target:target + region_w]
            fg = cv2.resize(region, (fg_w, fg_h), interpolation=cv2.INTER_AREA)
            # Blurred background = same scene scaled to canvas + strong blur.
            bg = cv2.resize(frame, (TW, TH), interpolation=cv2.INTER_AREA)
            bg = cv2.GaussianBlur(bg, (0, 0), sigmaX=18)
            bg[fg_y:fg_y + fg_h, fg_x:fg_x + fg_w] = fg
            enc.stdin.write(bg.tobytes())
            idx += 1
    finally:
        dec.stdout.close()
        dec.wait()
        if enc.stdin is not None:
            enc.stdin.close()
        enc.wait()
    _mux_audio(video_path, vpath, output_path)
    try:
        os.remove(vpath)
    except OSError:
        pass
    return output_path


def _probe_fps(video_path: str) -> float:
    """Return the video frame rate via ffprobe (default 30.0)."""
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", video_path],
        capture_output=True, text=True,
    )
    try:
        num, den = out.stdout.strip().split("/")
        num, den = float(num), float(den)
        fps = num / den if den else 30.0
    except Exception:
        fps = 30.0
    # Some videos report 0/1 or a non-sensical fps; a non-positive value would
    # break time math (idx/fps) and the -r encoder arg. Clamp to a sane default.
    if not fps or fps < 1.0 or fps > 120.0:
        return 30.0
    return fps


def _reframe_blur_pad(video_path, output_path, ass_path=None):
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
        "-c:v", "libx264", "-preset", config.FFMPEG_PRESET, "-crf", str(config.FFMPEG_CRF), "-c:a", "aac", "-y", output_path,
    ], check=True, capture_output=True)
    return output_path


def _mux_audio(video_src, video_no_audio, output):
    subprocess.run([
        FFMPEG, "-i", video_no_audio, "-i", video_src,
        "-map", "0:v:0", "-map", "1:a:0?", "-c:v", "libx264", "-preset", config.FFMPEG_PRESET,
        "-crf", str(config.FFMPEG_CRF), "-c:a", "aac", "-shortest", "-y", output,
    ], check=True, capture_output=True)
