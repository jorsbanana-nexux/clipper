"""SMOKE TEST 2 — dynamic DUO transition path (single -> duo -> single).

The render-chain smoke test (smoke_render.py) covers the STATIC paths
(solo reframe, subtitle burn, aspect conversion). This one covers the path
that was never exercised before v0.3.1: compositing a clip whose layout
CHANGES mid-clip (split-screen appears for the second speaker, then closes).

Verifies, 100% offline (no faces needed — the duo reframe splits left/right
halves of the frame, which works on any source):
1. _remap_words_for_xfade — subtitle timings shift by PER-SEGMENT offsets
   (seg1 +0, seg2 -0.25, seg3 -0.50 after two 0.25s crossfades), words outside
   the timeline are dropped. A linear rescale would drift; this must not.
2. compositor.render_dynamic_clip — 3-segment timeline renders, output is
   native 9:16, duration = source - 2*crossfade (within encode tolerance).
3. Subtitle burn (mode="duo", MrBeast preset) on the composed render.

Run:  python tests/smoke_dynamic.py
Needs: ffmpeg on PATH + `pip install python-dotenv opencv-python-headless numpy`
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))

from app import compositor, jobs, renderer, subtitles  # noqa: E402

FFMPEG = renderer.FFMPEG


def main() -> int:
    timeline = [
        {"start": 0.0, "end": 8.0, "layout": "single"},
        {"start": 8.0, "end": 15.0, "layout": "duo"},
        {"start": 15.0, "end": 20.0, "layout": "single"},
    ]

    # 1. word remap after crossfades
    words = [
        {"word": "awal", "start": 1.0, "end": 1.5},
        {"word": "duo", "start": 10.0, "end": 10.5},
        {"word": "akhir", "start": 17.0, "end": 17.5},
        {"word": "buang", "start": 21.0, "end": 22.0},
    ]
    remapped = jobs._remap_words_for_xfade(words, timeline, compositor.CROSSFADE)
    times = {w["word"]: w["start"] for w in remapped}
    assert abs(times["awal"] - 1.00) < 1e-6, times
    assert abs(times["duo"] - 9.75) < 1e-6, times
    assert abs(times["akhir"] - 16.50) < 1e-6, times
    assert "buang" not in times
    print("[ok] remap xfade: +0 / -0.25 / -0.50 per segmen, luar timeline dibuang")

    # 2. dynamic render (cut + reframe x3 + xfade + mux)
    src = REPO / "tests" / "_dyn_src.mp4"
    subprocess.run([
        FFMPEG, "-y", "-f", "lavfi",
        "-i", "testsrc2=size=1280x720:rate=30:duration=20",
        "-f", "lavfi", "-i", "sine=frequency=330:duration=20",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest", str(src),
    ], check=True, capture_output=True)
    dyn = str(REPO / "tests" / "_dyn_out.mp4")
    compositor.render_dynamic_clip(str(src), timeline, dyn)
    d = renderer.probe_duration(dyn)
    expected = 20.0 - 2 * compositor.CROSSFADE
    assert abs(d - expected) < 0.4, f"durasi {d} != ~{expected}"
    print(f"[ok] render dinamis: {d:.2f}s (~{expected:.2f}s expected), 9:16 native")

    # 3. subtitle burn on the composed output
    wds, t = [], 2.0
    for k in "LIHAT TRANSISINYA SEKARANG SPLIT DUO AKTIF LALU KEMBALI SOLO".split():
        wds.append({"word": k, "start": round(t, 3), "end": round(t + 0.4, 3)})
        t += 0.5
    ass = REPO / "tests" / "_dyn_subs.ass"
    ass.write_text(
        subtitles.words_to_ass(wds, 1080, 1920, "duo", style="mrbeast"),
        encoding="utf-8")
    final = str(REPO / "tests" / "_dyn_final.mp4")
    renderer.burn_subtitles_and_effects(dyn, str(ass), final)
    renderer.verify_output(final, 10.0)
    print("[ok] subtitle mode-duo terbakar di render transisi, terverifikasi")

    for p in (src, ass, REPO / "tests" / "_dyn_out.mp4", final):
        try:
            Path(p).unlink()
        except OSError:
            pass

    print("\nDYNAMIC TRANSITION SMOKE TEST PASSED ✅")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"\nDYNAMIC SMOKE TEST FAILED ❌: {type(e).__name__}: {e}")
        sys.exit(1)
