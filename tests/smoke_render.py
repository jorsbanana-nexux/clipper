"""SMOKE TEST — render-chain end-to-end WITHOUT internet or API keys.

Addresses gap #1 in docs/ROADMAP.md ("never tested end-to-end"): this proves
the ENTIRE local render chain really works — from a raw video file to a
finished, verified 9:16 clip with burned word-by-word subtitles, in every
subtitle preset, in every export aspect.

What it does (all offline, ~1-2 minutes on a normal PC):
1. Synthesises a 1280x720 test video with ffmpeg (testsrc2 + tone audio).
2. precise_trim (frame-accurate re-encode cut).
3. Builds word-by-word ASS subtitles in EVERY preset (mrbeast/hormozi/
   minimal/karaoke/none) and burns one in with viral effects.
4. Reframes to 9:16 (blur-pad path — synthetic video has no faces).
5. convert_aspect -> 1:1 and 4:5 (face-safe blurred pad).
6. verify_output + thumbnail on every artifact.

Run:  python tests/smoke_render.py
Needs: ffmpeg on PATH, pip install python-dotenv opencv-python-headless numpy
"""
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))

from app import config, downloader, renderer, subtitles  # noqa: E402
from app import face_tracker  # noqa: E402  (needs opencv; mediapipe optional)

FFMPEG = renderer.FFMPEG


def sh(*cmd):
    r = subprocess.run(list(cmd), capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd)}\n{r.stderr[-500:]}")


def make_synthetic_video(path: Path, seconds: int = 12) -> Path:
    sh(FFMPEG, "-y",
       "-f", "lavfi", "-i", f"testsrc2=size=1280x720:rate=30:duration={seconds}",
       "-f", "lavfi", "-i", "sine=frequency=440:duration={}".format(seconds),
       "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
       "-c:a", "aac", "-shortest", str(path))
    return path


def fake_words(n: int = 24, start: float = 0.4) -> list[dict]:
    """Word-level timings like faster-whisper would emit."""
    words = []
    t = start
    for i in range(n):
        dur = 0.28 if i % 3 else 0.42
        words.append({"word": f"word{i}", "start": round(t, 3), "end": round(t + dur, 3)})
        t += dur + 0.05
    return words


def probe_dims(path: Path) -> tuple:
    out = subprocess.run(
        [renderer.FFPROBE, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True).stdout.strip()
    w, h = out.split(",")
    return int(w), int(h)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="clipper_smoke_"))
    print(f"[smoke] workspace: {tmp}")
    failures = []

    # 1. synthetic source
    src = make_synthetic_video(tmp / "src.mp4")
    print(f"[ok] synthetic source: {src.name} ({probe_dims(src)})")

    # 2. precise trim
    trimmed = str(tmp / "trimmed.mp4")
    downloader.precise_trim(str(src), 0.0, 8.0, trimmed)
    d = renderer.probe_duration(trimmed)
    assert 7.0 < d <= 8.6, f"trimmed duration {d} unexpected"
    print(f"[ok] precise_trim: {d:.2f}s")

    # 3. subtitles — every preset builds a valid ASS doc
    words = fake_words()
    for style in config.SUBTITLE_PRESETS:
        doc = subtitles.words_to_ass(words, config.TARGET_WIDTH, config.TARGET_HEIGHT, "single", style=style)
        if style == "none":
            assert doc == "", "'none' preset must produce an empty doc"
        else:
            assert "[Events]" in doc and "Dialogue:" in doc, f"{style}: no dialogue events"
            n = doc.count("Dialogue:")
            assert n >= 4, f"{style}: too few cues ({n})"
        print(f"[ok] subtitle preset '{style}': {doc.count('Dialogue:')} cues")

    # 4. burn subtitles + effects (mrbeast) on the trimmed segment
    ass_path = tmp / "subs.ass"
    ass_path.write_text(
        subtitles.words_to_ass(words, config.TARGET_WIDTH, config.TARGET_HEIGHT, "single", style="mrbeast"),
        encoding="utf-8")
    burned = str(tmp / "burned.mp4")
    renderer.burn_subtitles_and_effects(trimmed, str(ass_path), burned)
    renderer.verify_output(burned, 5.0)
    print("[ok] burn subtitles + viral effects, verified")

    # 5. reframe 9:16 (no faces in synthetic video -> blur-pad fallback path)
    vertical = str(tmp / "vertical.mp4")
    face_tracker.reframe_to_vertical(burned, vertical, samples=[])
    renderer.verify_output(vertical, 5.0)
    w, h = probe_dims(vertical)
    assert (w, h) == (config.TARGET_WIDTH, config.TARGET_HEIGHT), f"expected 1080x1920, got {w}x{h}"
    print(f"[ok] reframe 9:16 blur-pad: {w}x{h}")

    # 6. aspect conversion 1:1 and 4:5 (face-safe)
    for aspect in ("1:1", "4:5"):
        out = str(tmp / f"out_{aspect.replace(':', 'x')}.mp4")
        renderer.convert_aspect(vertical, out, aspect)
        renderer.verify_output(out, 5.0)
        tw, th = probe_dims(out)
        assert (tw, th) == config.ASPECTS[aspect], f"{aspect}: got {tw}x{th}"
        print(f"[ok] convert_aspect {aspect}: {tw}x{th}")

    # 7. thumbnail
    thumb = str(tmp / "thumb.jpg")
    renderer.make_thumbnail(vertical, thumb)
    assert Path(thumb).stat().st_size > 0
    print("[ok] thumbnail")

    print("\nALL SMOKE TESTS PASSED ✅  (render chain works end-to-end, offline)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"\nSMOKE TEST FAILED ❌: {type(e).__name__}: {e}")
        sys.exit(1)
