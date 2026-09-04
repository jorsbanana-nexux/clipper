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


def _build_duo_tracks(frames: list[FrameFaces]) -> tuple[list[float], list[float], list[float]]:
    """Turn raw per-frame face detections into TWO STABLE identity tracks.

    v0.3.3 — this is the "brain" that was MISSING before: the old reframe_duo
    never looked at face positions at all, it just cut the frame in half by
    GEOMETRY (left half / right half), so decor sitting in one half (a plant
    wall, a shelf) got treated exactly like a speaker. Real footage doesn't
    obey a 50/50 split — one person can dominate more of the frame, sit off-
    centre, or the camera can be uneven. This tracks the ACTUAL two faces:

    - Frame with >=2 faces: the two LARGEST are sorted left->right by centre-x
      and assigned to the "left" / "right" identity (stable seating order —
      podcast guests essentially never swap physical sides mid-take).
    - Frame with exactly 1 face: assigned to whichever identity it is
      POSITIONALLY closest to (keeps identity from flip-flopping when the
      camera briefly only catches one person, e.g. a reaction close-up).
    - Frame with 0 faces (cut/occlusion): both identities CARRY FORWARD their
      last known position rather than snapping to frame-centre (0.5), so the
      crop doesn't jump on a missed detection.

    Returns (ts, cx_left, cx_right) — raw (pre-smoothing) per-timestamp centre-x
    (0..1) for each identity, aligned to `ts`.
    """
    if not frames:
        return [], [], []
    ts = [f.t for f in frames]
    left_track: list[float] = []
    right_track: list[float] = []
    last_left: float | None = None
    last_right: float | None = None
    for f in frames:
        faces = sorted(f.faces, key=lambda x: -x.size)[:2]
        if len(faces) >= 2:
            cxs = sorted(x.cx for x in faces)
            l, r = cxs[0], cxs[1]
        elif len(faces) == 1:
            c = faces[0].cx
            if last_left is None and last_right is None:
                l, r = c, c
            elif last_left is None:
                l, r = c, last_right
            elif last_right is None:
                l, r = last_left, c
            elif abs(c - last_left) <= abs(c - last_right):
                l, r = c, last_right
            else:
                l, r = last_left, c
        else:
            l = last_left if last_left is not None else 0.28
            r = last_right if last_right is not None else 0.72
        left_track.append(l)
        right_track.append(r)
        last_left, last_right = l, r
    return ts, left_track, right_track


def _fit_crop_box(W: int, H: int, out_w: int, out_h: int, cx_norm: float) -> tuple[int, int, int, int]:
    """Largest out_w:out_h box that fits inside a WxH source, horizontally
    centred on cx_norm (0..1), never distorting aspect ratio."""
    target_ar = out_w / out_h
    src_ar = W / H
    if src_ar >= target_ar:
        # source is relatively wider -> crop width, keep full height
        crop_h = H
        crop_w = max(2, int(round(H * target_ar)))
        crop_w = min(crop_w, W)
        max_x = max(0, W - crop_w)
        x = int(np.clip(cx_norm * W - crop_w / 2, 0, max_x))
        return x, 0, crop_w, crop_h
    # source is relatively taller -> crop height, keep full width, slight
    # upward bias so heads aren't cut off by a pure centre-crop
    crop_w = W
    crop_h = max(2, int(round(W / target_ar)))
    crop_h = min(crop_h, H)
    max_y = max(0, H - crop_h)
    y = int(np.clip(max_y * 0.35, 0, max_y))
    return 0, y, crop_w, crop_h


def _reframe_duo_facetrack(video_path: str, output_path: str, ts: list[float],
                           cx_top: list[float], cx_bot: list[float],
                           ass_path: str | None = None) -> str | None:
    """Real split-screen: each band crop-follows ITS OWN tracked identity.

    Decodes once, composites two independently-tracked crops (top identity /
    bottom identity) into the 1080x1920 canvas per frame, encodes once. Same
    decode/cv2/encode-pipe pattern as the solo crop-follow, so it inherits the
    same reliability (no cv2.VideoCapture/VideoWriter) and the same smooth,
    clamped-movement camera language — just doubled, one crop per band.
    Returns None (caller falls back) if the source is unusable.
    """
    W, H = _probe_dims(video_path)
    if W <= 0 or H <= 0:
        return None
    TW, TH = config.TARGET_WIDTH, config.TARGET_HEIGHT
    band_h = TH // 2

    tx0, ty0, tw0, th0 = _fit_crop_box(W, H, TW, band_h, cx_top[0] if cx_top else 0.3)
    bx0, by0, bw0, bh0 = _fit_crop_box(W, H, TW, band_h, cx_bot[0] if cx_bot else 0.7)
    if tw0 < 8 or th0 < 8 or bw0 < 8 or bh0 < 8:
        return None

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
    prev_x_top, prev_x_bot = None, None
    max_move_top = max(2.0, tw0 * 0.18)
    max_move_bot = max(2.0, bw0 * 0.18)
    try:
        while True:
            raw = dec.stdout.read(frame_bytes)
            if not raw or len(raw) < frame_bytes:
                break
            frame = np.frombuffer(raw, np.uint8).reshape((H, W, 3))
            t = idx / fps

            ct = _xcx_at(t, ts, cx_top) if ts else 0.3
            cb = _xcx_at(t, ts, cx_bot) if ts else 0.7

            xt, yt, wt, ht = _fit_crop_box(W, H, TW, band_h, ct)
            xt -= xt % 2
            if prev_x_top is not None:
                xt = int(np.clip(xt, prev_x_top - max_move_top, prev_x_top + max_move_top))
                xt -= xt % 2
            prev_x_top = xt

            xb, yb, wb, hb = _fit_crop_box(W, H, TW, band_h, cb)
            xb -= xb % 2
            if prev_x_bot is not None:
                xb = int(np.clip(xb, prev_x_bot - max_move_bot, prev_x_bot + max_move_bot))
                xb -= xb % 2
            prev_x_bot = xb

            top_region = frame[yt:yt + ht, xt:xt + wt]
            bot_region = frame[yb:yb + hb, xb:xb + wb]
            top_band = cv2.resize(top_region, (TW, band_h), interpolation=cv2.INTER_AREA)
            bot_band = cv2.resize(bot_region, (TW, band_h), interpolation=cv2.INTER_AREA)
            canvas = np.vstack([top_band, bot_band])
            enc.stdin.write(canvas.tobytes())
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


def reframe_duo(video_path: str, output_path: str, ass_path: str | None = None) -> str:
    """Two-speaker split-screen -> stacked top & bottom bands (9:16), each band
    crop-following ITS OWN tracked speaker (v0.3.3 — see _build_duo_tracks).

    v0.3.3 BUGFIX (the "kaku"/robotic split complaint): the old version split
    the frame into a static LEFT half / RIGHT half by pure geometry, with NO
    face detection at all. Decor sitting in one half of the shot (a plant
    wall, a shelf) was rendered exactly like a speaker, and a person who
    wasn't centred in their half got cropped badly. Now: faces are detected
    over time, each identity is tracked with the SAME EMA smoothing used for
    the smooth solo crop-follow, and each band's crop glides to follow its own
    speaker. Falls back to the old static split ONLY if face detection finds
    nothing at all (detector unavailable) — never crashes the render.
    """
    frames = analyze_faces_all(video_path, sample_interval=0.4)
    ts, cx_l_raw, cx_r_raw = _build_duo_tracks(frames)
    if ts and len(ts) >= 2:
        cx_top = _ema_smooth(cx_l_raw, config.FACE_SMOOTH_ALPHA)
        cx_bot = _ema_smooth(cx_r_raw, config.FACE_SMOOTH_ALPHA)
        try:
            result = _reframe_duo_facetrack(video_path, output_path, ts, cx_top, cx_bot, ass_path)
            if result:
                return result
        except Exception:
            pass  # any decode/encode hiccup -> fall through to the static split
    return _reframe_duo_static_fallback(video_path, output_path, ass_path)


def _reframe_duo_static_fallback(video_path: str, output_path: str, ass_path: str | None = None) -> str:
    """LAST-RESORT duo split when face detection finds nothing at all (e.g.
    MediaPipe/Haar both unavailable in this environment). Static 50/50 left/
    right halves stacked top/bottom — geometry-only, no face awareness. This
    used to be the ONLY behaviour (v0.3.2 and earlier); now it is only the
    fallback for a genuinely faceless duo segment, which should be rare since
    jobs._validate_duo_with_faces already downgrades duo->single upstream
    when two faces aren't consistently visible.
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
    """Blur-pad reframe (no usable faces). v0.3.1 BUGFIX: `ass_path` used to be
    ACCEPTED BUT IGNORED — faceless content (screen recordings, slides, game
    footage) was silently rendered WITHOUT its subtitles. Now the subtitle +
    effects chain is folded into this same encode, matching the crop-follow
    and duo paths."""
    TW, TH = config.TARGET_WIDTH, config.TARGET_HEIGHT
    vf = (
        f"split[bg][fg];"
        f"[bg]scale={TW}:{TH}:force_original_aspect_ratio=increase,crop={TW}:{TH},"
        f"gblur=sigma=20[bg];"
        f"[fg]scale={TW}:-2[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2,"
        + renderer.effects_vf(ass_path)
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
