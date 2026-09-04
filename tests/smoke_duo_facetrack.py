"""SMOKE TEST 3 — face-aware duo split (v0.3.3).

Covers the biggest real bug found from the owner's own screenshots: the OLD
reframe_duo split the frame into a STATIC left-half/right-half by geometry,
with ZERO face detection. Decor sitting in one half of the shot (a plant
wall) got rendered exactly like a speaker. This test proves the NEW
face-tracked duo reframe actually follows tracked positions, offline —
no real face detector needed for the render-math half; the identity-tracking
"brain" is tested with mocked detections (no video needed at all).

Run:  python tests/smoke_duo_facetrack.py
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))

from app import face_tracker, renderer, subtitles  # noqa: E402
from app.face_tracker import FaceSample, FrameFaces, _build_duo_tracks, _fit_crop_box  # noqa: E402

FFMPEG = renderer.FFMPEG


def test_tracking_logic() -> None:
    # 2 faces, consistently left/right -> identities never swap
    frames = [
        FrameFaces(t=0.0, faces=[FaceSample(0.0, cx=0.25, size=0.15), FaceSample(0.0, cx=0.75, size=0.15)]),
        FrameFaces(t=0.5, faces=[FaceSample(0.5, cx=0.22, size=0.16), FaceSample(0.5, cx=0.78, size=0.14)]),
    ]
    _, l, r = _build_duo_tracks(frames)
    assert all(x < 0.5 for x in l) and all(x > 0.5 for x in r)
    print("[ok] identitas kiri/kanan stabil, tak pernah tertukar")

    # 1 face only -> sticks to nearest identity, the other carries forward
    frames2 = [
        FrameFaces(t=0.0, faces=[FaceSample(0.0, cx=0.2, size=0.15), FaceSample(0.0, cx=0.8, size=0.15)]),
        FrameFaces(t=0.5, faces=[FaceSample(0.5, cx=0.22, size=0.15)]),
    ]
    _, l2, r2 = _build_duo_tracks(frames2)
    assert abs(l2[1] - 0.22) < 0.01 and abs(r2[1] - r2[0]) < 0.01
    print("[ok] 1 wajah terdeteksi -> nempel identitas terdekat, sisi lain carry-forward")

    # 0 faces (camera cut) -> BOTH carry forward, never snap to centre 0.5
    frames3 = [
        FrameFaces(t=0.0, faces=[FaceSample(0.0, cx=0.15, size=0.15), FaceSample(0.0, cx=0.85, size=0.15)]),
        FrameFaces(t=0.5, faces=[]),
    ]
    _, l3, r3 = _build_duo_tracks(frames3)
    assert abs(l3[1] - 0.15) < 0.01 and abs(r3[1] - 0.85) < 0.01
    print("[ok] 0 wajah -> carry-forward posisi terakhir, tak snap ke tengah")

    x, y, w, h = _fit_crop_box(1920, 1080, 1080, 960, cx_norm=0.5)
    assert abs(w / h - 1080 / 960) < 0.01
    print("[ok] fit_crop_box: aspek tak distorsi, terpusat pada cx")


def test_render_follows_track() -> None:
    out = REPO / "tests" / "_duo_ft"
    out.mkdir(exist_ok=True)
    src = out / "src.mp4"
    subprocess.run([
        FFMPEG, "-y",
        "-f", "lavfi", "-i", "color=c=red:size=640x360:duration=4",
        "-f", "lavfi", "-i", "color=c=green:size=640x360:duration=4",
        "-f", "lavfi", "-i", "sine=frequency=220:duration=4",
        "-filter_complex", "[0:v][1:v]hstack=inputs=2,scale=1280x720[out]",
        "-map", "[out]", "-map", "2:a", "-c:v", "libx264", "-preset", "veryfast",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-r", "30", "-shortest", str(src),
    ], check=True, capture_output=True)

    vertical = str(out / "vertical.mp4")
    face_tracker._reframe_duo_facetrack(str(src), vertical, [0.0, 4.0], [0.2, 0.2], [0.8, 0.8], None)
    renderer.verify_output(vertical, 3.0)

    import cv2
    frame_png = str(out / "frame.png")
    subprocess.run([FFMPEG, "-y", "-ss", "2.0", "-i", vertical, "-frames:v", "1", frame_png],
                    check=True, capture_output=True)
    img = cv2.imread(frame_png)
    h, _ = img.shape[:2]
    top_mean = img[:h // 2, :].reshape(-1, 3).mean(axis=0)
    bot_mean = img[h // 2:, :].reshape(-1, 3).mean(axis=0)
    assert top_mean[2] > top_mean[1] and top_mean[2] > 100, f"band atas seharusnya MERAH: {top_mean}"
    assert bot_mean[1] > bot_mean[2] and bot_mean[1] > 100, f"band bawah seharusnya HIJAU: {bot_mean}"
    print("[ok] band ATAS mengikuti track cx=0.2 (MERAH), band BAWAH mengikuti cx=0.8 (HIJAU)")
    print("     -> tiap band crop-follow identitasnya SENDIRI, bukan belah statis 50/50")

    for p in (src, out / "vertical.mp4", frame_png):
        try:
            Path(p).unlink()
        except OSError:
            pass
    try:
        out.rmdir()
    except OSError:
        pass


def test_subtitle_anti_smear() -> None:
    """Adjacent words with a tiny timestamp overlap must NOT both read as
    tinted at once ("warna biru menyeret ke kanan")."""
    import re
    words = [
        {"word": "cepat", "start": 1.000, "end": 1.150},
        {"word": "sekali", "start": 1.140, "end": 1.300},  # 10ms overlap
    ]
    doc = subtitles.words_to_ass(words, 1080, 1920, "single", style="mrbeast")
    fade_backs = re.findall(r"\\t\((\d+),(\d+),\\c&H00FFFFFF\)", doc)
    pop_ins = re.findall(r"\\t\((\d+),(\d+),\\c&H00FFE500\)", doc)
    assert fade_backs and len(pop_ins) >= 2
    # Without the clamp, word 1 (150ms natural end) would stay FULLY BLUE
    # until 150ms while word 2 (140ms start) is ALSO fully blue from 140ms ->
    # both solid blue at once for ~10ms = the visual "smear/drag" bug. With
    # the clamp, word 1's fade-to-white STARTS at the exact instant word 2's
    # pop-to-blue starts (both = the next word's start) -> a single clean
    # 40ms crossfade handoff, never two words fully coloured simultaneously.
    w1_fade_start = int(fade_backs[0][0])
    w2_pop_start = int(pop_ins[1][0])
    assert w1_fade_start == w2_pop_start == 140, f"handoff tak sinkron: {w1_fade_start} vs {w2_pop_start}"
    print("[ok] anti-smear: kata 1 mulai pudar TEPAT saat kata 2 mulai muncul (crossfade 40ms bersih, tak pernah 2 kata biru solid bersamaan)")


def main() -> int:
    test_tracking_logic()
    test_render_follows_track()
    test_subtitle_anti_smear()
    print("\nDUO FACE-TRACK + ANTI-SMEAR SMOKE TEST PASSED ✅")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"\nSMOKE TEST FAILED ❌: {type(e).__name__}: {e}")
        sys.exit(1)
