"""In-process job manager: async pipeline execution with progress tracking.

Pipeline strategy (light / low-resource friendly):
1. Captions-first: try YouTube/auto captions -> transcript WITHOUT downloading audio.
   (falls back to full-audio download + Whisper only when no captions exist)
2. GPT analyses the transcript text -> picks viral moments.
3. For each moment: download ONLY that video segment + (if captions path)
   only that audio segment -> Whisper for word timestamps -> reframe 9:16
   -> word-by-word subtitles -> effects.

v1 keeps jobs in memory (single-process). Swapping the dict for Redis is a
documented future step for horizontal scaling.
"""
import asyncio
import re
import shutil
import uuid
from pathlib import Path

from . import config, downloader, transcriber, analyzer, subtitles, face_tracker, renderer, diarization, layout, compositor
from .models import ClipInfo, JobStatus


def _remap_words_for_xfade(words: list[dict], timeline: list[dict],
                           crossfade: float) -> list[dict]:
    """Re-time subtitle words onto the crossfaded render timeline.

    Each rendered segment k starts at sum_{j<k} (dur_j - crossfade). A word is
    therefore shifted by a PER-SEGMENT constant offset — never linearly scaled.
    """
    rendered_starts = []
    t = 0.0
    for seg in timeline:
        rendered_starts.append(t)
        t += (seg["end"] - seg["start"]) - crossfade
    out = []
    for w in words:
        mid = (w["start"] + w["end"]) / 2.0
        idx = None
        for i, seg in enumerate(timeline):
            if seg["start"] <= mid < seg["end"]:
                idx = i
                break
        if idx is None:
            continue  # word sits outside any timeline window -> drop it
        off = rendered_starts[idx] - timeline[idx]["start"]
        out.append({**w, "start": w["start"] + off, "end": w["end"] + off})
    return out


def _snap_cut_boundaries(highlights, segments, min_dur: float = 15.0) -> None:
    """The "no dead air" cut rule, enforced in CODE — not just in prompts.

    For every highlight: walk back from the LLM's end time to the last natural
    stopping point — a sentence-final segment, or a segment followed by a
    silence gap. If the LLM left trailing filler/dead air, the end is pulled
    back so the clip stops right after the payoff. Never shortens below
    min_dur. Mutates the highlights in place.
    """
    if not highlights or not segments:
        return
    segs = sorted(
        (s for s in segments
         if s.get("end") is not None and s.get("start") is not None),
        key=lambda s: float(s["start"]))
    if not segs:
        return
    for hl in highlights:
        end = float(hl.end_time)
        floor = float(hl.start_time) + min_dur
        best = None
        # PASS 1 (preferred): the last SENTENCE-FINAL segment in range — cut
        # exactly after the conclusion sentence, even if filler follows it.
        for s in reversed(segs):
            s_end = float(s["end"])
            if s_end > end + 0.25:
                continue
            if s_end <= floor:
                break
            if re.search(r"[.!?…]", s.get("text") or ""):
                best = s_end
                break
        # PASS 2 (fallback): no sentence-final found — stop at the last
        # segment followed by a silence gap (drops trailing dead air anyway).
        if best is None:
            for s in reversed(segs):
                s_end = float(s["end"])
                if s_end > end + 0.25:
                    continue
                if s_end <= floor:
                    break
                nxt = None
                for t in segs:
                    if float(t["start"]) > s_end + 0.01:
                        nxt = t
                        break
                if nxt is None or (float(nxt["start"]) - s_end) >= 0.45:
                    best = s_end
                    break
        if best is not None and end - best >= 0.3:
            hl.end_time = round(best, 3)


def _brief_error(exc: BaseException) -> str:
    """Short human-readable description of a render exception, including ffmpeg
    stderr and return code when available."""
    extra = ""
    if hasattr(exc, "stderr") and exc.stderr:
        try:
            tail = exc.stderr
            if isinstance(tail, bytes):
                tail = tail.decode(errors="replace")
            extra += f" | ffmpeg: {str(tail)[-500:]}"
        except Exception:
            pass
    if hasattr(exc, "returncode") and exc.returncode is not None:
        extra += f" (exit {exc.returncode})"
    return f"[{type(exc).__name__}] {exc}{extra}"


class Job:
    def __init__(self, job_id: str):
        self.job_id = job_id
        self.status = JobStatus(job_id=job_id, status="queued")
        self.task: asyncio.Task | None = None
        self._cancel = False
        # Highest progress ever published. Used to keep the loading bar strictly
        # monotonic (never regresses) even when workers update in parallel.
        self._max_progress = 0.0

    def update(self, **kw):
        # Clamp progress so it never goes backwards (real, honest indicator).
        if "progress" in kw:
            p = max(0.0, min(1.0, float(kw["progress"])))
            if p < self._max_progress:
                p = self._max_progress
            self._max_progress = p
            kw["progress"] = p
        for k, v in kw.items():
            setattr(self.status, k, v)


class JobManager:
    def __init__(self):
        self.jobs: dict[str, Job] = {}

    def create(self) -> Job:
        jid = uuid.uuid4().hex[:12]
        job = Job(jid)
        self.jobs[jid] = job
        return job

    def get(self, jid: str) -> Job | None:
        return self.jobs.get(jid)

    def start(self, job: Job, request):
        job.task = asyncio.create_task(_run_pipeline(job, request))


manager = JobManager()


def _cleanup_old_jobs() -> None:
    """A7: delete job output folders older than config.RETENTION_DAYS."""
    import time
    retention = getattr(config, "RETENTION_DAYS", 7)
    if retention <= 0:
        return
    now = time.time()
    cutoff = retention * 86400
    out = config.OUTPUT_DIR
    if not out.exists():
        return
    for p in out.iterdir():
        if p.is_dir():
            try:
                if now - p.stat().st_mtime > cutoff:
                    shutil.rmtree(p, ignore_errors=True)
            except OSError:
                continue


def _validate_duo_with_faces(timeline: list[dict], counts: list[tuple],
                             ratio: float = 0.4) -> list[dict]:
    """Downgrade any DUO segment that does NOT actually show two faces to SINGLE.

    `counts` = [(t, n_faces)] in LOCAL clip time. A duo window with too few
    two-face samples means the camera cut to a single close-up, so a split-screen
    would show an empty half — switch it to crop-follow instead.
    """
    out: list[dict] = []
    for s in timeline:
        if s["layout"] == layout.LAYOUT_DUO:
            win = [n for (t, n) in counts if s["start"] <= t <= s["end"]]
            if win and sum(1 for n in win if n >= 2) / len(win) < ratio:
                s = dict(s)
                s["layout"] = layout.LAYOUT_SINGLE
        out.append(s)
    # merge adjacent same-layout segments
    merged: list[dict] = []
    for s in out:
        if merged and merged[-1]["layout"] == s["layout"]:
            merged[-1]["end"] = max(merged[-1]["end"], s["end"])
        else:
            merged.append(s)
    return merged


async def _render_one_clip(job, url, hl, index, used_captions, caption_lang, full_words,
                          work_dir, span_start: float = 0.0, span_end: float = 1.0,
                          total_clips: int = 1):
    """Render a single clip end-to-end. Returns a ClipInfo, or raises on error.

    `span_start`/`span_end` delimit this clip's share of the overall progress bar
    (0..1). `report(frac)` is a helper that publishes monotonic progress within
    that span and a message, so the loading indicator moves in REAL time through
    each sub-stage of the clip instead of freezing until it finishes.
    """
    def report(frac: float, msg: str):
        p = span_start + (span_end - span_start) * max(0.0, min(1.0, frac))
        job.update(progress=p, message=f"{msg} ({index}/{total_clips})")

    head_pad = config.PADDING_SEC
    tail_pad = getattr(config, "TAIL_SEC", 0.35)
    padded_start = max(0.0, hl.start_time - head_pad)
    # Small trailing padding so the clip stops crisply at the punchline instead
    # of rambling on past the chosen moment.
    padded_end = hl.end_time + tail_pad

    seg_dir = work_dir / f"clip_{index}"
    seg_dir.mkdir(exist_ok=True)

    report(0.05, "Mengunduh segmen video")
    raw_path = await asyncio.to_thread(
        downloader.download_segment, url, padded_start, padded_end, str(seg_dir))

    # Precise trim to the exact window: yt-dlp range download can land on a
    # keyframe PAST the end, dragging irrelevant trailing content into the clip.
    if getattr(config, "PRECISE_TRIM", True):
        trimmed = str(seg_dir / "seg_trim.mp4")
        report(0.10, "Trim presisi segmen")
        raw_path = await asyncio.to_thread(
            downloader.precise_trim, raw_path, 0.0, padded_end - padded_start, trimmed)

    local_words: list[dict] = []
    aseg: str | None = None
    if used_captions:
        try:
            report(0.15, "Mendapatkan audio + transkrip kata")
            aseg = await asyncio.to_thread(
                downloader.download_audio_segment, url, padded_start, padded_end, str(seg_dir))
            t = await asyncio.to_thread(transcriber.transcribe, aseg, caption_lang)
            local_words = transcriber.words_from_transcript(t)
        except Exception as e:
            job.update(message=f"clip {index}: audio segment Whisper failed ({e}); subtitle skipped")
    else:
        local_words = [
            {**w, "start": w["start"] - padded_start, "end": w["end"] - padded_start}
            for w in full_words
            if w["end"] >= padded_start and w["start"] <= padded_end
        ]

    turns: list[dict] = []
    diar_note = ""
    if diarization.diarization_available():
        try:
            diar_audio = str(seg_dir / "diar_audio.wav")
            diar_src = aseg if aseg else raw_path
            await asyncio.to_thread(renderer.cut_audio, diar_src, 0.0, padded_end - padded_start, diar_audio)
            turns = await asyncio.to_thread(diarization.diarize, diar_audio)
            if not turns:
                diar_note = "diarization returned no speaker turns"
        except Exception as e:
            # Never fail the clip; report why duo may be off so the user isn't
            # left guessing why split-screen didn't appear.
            diar_note = f"diarization unavailable/failed: {e}"

    loc_dur = padded_end - padded_start
    timeline = None
    if config.LAYOUT_MODE in ("single", "duo"):
        clip_layout = config.LAYOUT_MODE
        timeline = [{"start": 0.0, "end": loc_dur, "layout": clip_layout}]
    elif turns:
        # `turns` are LOCAL (cut from the already-downloaded segment), so time 0
        # is the start of `raw_path`. Dynamic timeline: duo when 2+ speakers talk
        # (split appears `lead` BEFORE the 2nd speaker so it's never late), and
        # closes back to solo when a speaker is alone for too long.
        timeline = layout.layout_timeline(turns, 0.0, loc_dur, config.DUO_LEAD_SEC)
        timeline = [s for s in timeline if s["end"] > s["start"]]
        # VIEWER-AWARE: diarization tells us WHEN someone talks, not whether both
        # are visible. If the camera cuts between close-ups (only one face in the
        # duo window), a split-screen would show an empty half. Downgrade such
        # duo segments to single (crop-follow) so it never looks broken.
        if any(s["layout"] == layout.LAYOUT_DUO for s in timeline):
            try:
                counts = await asyncio.to_thread(
                    face_tracker.face_counts_over_time, raw_path)
                if counts and len(counts) >= 3:
                    timeline = _validate_duo_with_faces(
                        timeline, counts, getattr(config, "DUO_FACE_RATIO", 0.4))
            except Exception:
                pass  # keep the diarization-based plan on any analysis error
    elif getattr(config, "DUO_AUTO_FACES", True):
        # Free fallback so split-screen works WITHOUT diarization/token: if two
        # faces are consistently visible, auto-switch the whole clip to duo.
        duo_ratio = getattr(config, "DUO_AUTO_FACE_RATIO", 0.35)
        try:
            two = await asyncio.to_thread(face_tracker.has_two_speakers, raw_path, duo_ratio)
        except Exception:
            two = False
        if two:
            timeline = [{"start": 0.0, "end": loc_dur, "layout": "duo"}]
            job.update(message=f"Clip {index}: 2 wajah terdeteksi -> split-screen (auto-duo)")
        if diar_note:
            job.update(message=f"Clip {index}: {diar_note}")
    if timeline is None:
        clip_layout = layout.choose_template([], 0.0, 0.0)
        timeline = [{"start": 0.0, "end": loc_dur, "layout": clip_layout}]

    distinct = {s.get("layout") for s in timeline}
    dynamic_layout = len(timeline) > 1 and len(distinct) > 1

    vertical = str(seg_dir / "vertical.mp4")
    final = str(seg_dir / "final.mp4")
    ass_path = str(seg_dir / "subs.ass")
    sub_mode = "duo" if any(s.get("layout") == layout.LAYOUT_DUO for s in timeline) else "single"

    job.update(status="rendering", stage=f"render_{index}/reframe")
    report(0.35, "Membingkai ulang 9:16")
    if dynamic_layout:
        await asyncio.to_thread(compositor.render_dynamic_clip, raw_path, timeline, vertical)
        # xfade overlaps neighbouring segments, so the rendered timeline is
        # shorter than the source by (n-1)*CROSSFADE. BUGFIX: the old LINEAR
        # rescale drifted subtitles progressively out of sync after every
        # layout transition; the correct mapping is a PER-SEGMENT offset.
        if local_words:
            local_words = _remap_words_for_xfade(
                local_words, timeline, compositor.CROSSFADE)
        # Build ASS after scaling and burn in a dedicated pass (needed here).
        if local_words:
            Path(ass_path).write_text(
                subtitles.words_to_ass(
                    local_words, config.TARGET_WIDTH, config.TARGET_HEIGHT, sub_mode),
                encoding="utf-8")
            await asyncio.to_thread(renderer.burn_subtitles_and_effects, vertical, ass_path, final)
        else:
            shutil.copy(vertical, final)
    else:
        # Non-dynamic: fold subtitle + effects into the SAME reframe pass ->
        # ONE encode instead of two (the core batch speedup).
        if local_words:
            job.update(status="rendering", stage=f"reframe_{index}/subs")
            report(0.55, "Membakar subtitle word-by-word")
            Path(ass_path).write_text(
                subtitles.words_to_ass(
                    local_words, config.TARGET_WIDTH, config.TARGET_HEIGHT, sub_mode),
                encoding="utf-8")
        if timeline and timeline[0].get("layout") == "duo":
            await asyncio.to_thread(face_tracker.reframe_duo, raw_path, final, ass_path if local_words else None)
        else:
            samples = await asyncio.to_thread(face_tracker.analyze_faces, raw_path)
            await asyncio.to_thread(face_tracker.reframe_to_vertical, raw_path, final, samples, ass_path if local_words else None)

    report(0.85, "Memverifikasi output")
    await asyncio.to_thread(renderer.verify_output, final, max(1.0, (padded_end - padded_start) * 0.5))

    thumb = str(seg_dir / "thumb.jpg")
    report(0.95, "Membuat thumbnail")
    await asyncio.to_thread(renderer.make_thumbnail, final, thumb)

    rel = f"/clips/{job.job_id}/clip_{index}/final.mp4"
    return ClipInfo(
        index=index,
        title=hl.title,
        start_time=hl.start_time,
        end_time=hl.end_time,
        duration=round(hl.end_time - hl.start_time, 2),
        viral_score=hl.viral_score,
        reason=hl.reason,
        hook=hl.hook,
        download_url=rel,
        filename=f"{job.job_id}_clip_{index}.mp4",
    )


async def _run_pipeline(job: Job, request) -> None:
    work_dir = config.OUTPUT_DIR / job.job_id
    work_dir.mkdir(parents=True, exist_ok=True)
    try:
        # ---- 1. transcript: captions-first (no audio) -> fallback full audio ----
        job.update(status="downloading", stage="transcript", progress=0.05,
                   message="Fetching transcript (captions-first)...")
        caption_segments, caption_lang, _ = await asyncio.to_thread(downloader.fetch_captions, request.url)
        used_captions = bool(caption_segments)
        full_words: list[dict] = []
        analysis_segments: list[dict] = []
        duration: float = 0.0
        audio_path: str | None = None

        if used_captions:
            analysis_segments = caption_segments
            job.update(stage="transcript_captions", progress=0.2,
                       message="Transcript ready (captions, no audio downloaded)")
        else:
            job.update(stage="download_audio", message="No captions — downloading audio...")
            audio_path, info = await asyncio.to_thread(downloader.download_audio_only, request.url, str(work_dir))
            duration = float((info or {}).get("duration") or 0.0)
            job.update(stage="transcribe", progress=0.2,
                       message="Transcribing speech (word-level)...")
            transcript = await asyncio.to_thread(transcriber.transcribe, audio_path)
            full_words = transcriber.words_from_transcript(transcript)
            analysis_segments = transcriber.segments_from_transcript(transcript)

        # ---- 2. analysis ----
        job.update(status="analyzing", stage="analyze", progress=0.35,
                   message="Finding viral moments...")
        # B2: run diarization once on the full audio (if enabled) so analysis is
        # speaker-aware (two-person exchanges are preferred for virality).
        # BUGFIX (the "HF duo never activates" bug): this was gated on
        # `not used_captions`, so on the DEFAULT captions path speaker turns
        # were NEVER fed to the analyzer even with HUGGINGFACE_TOKEN +
        # CLIPPER_MULTI_SPEAKER=1. Now, when multi-speaker is enabled, the full
        # audio is fetched once for diarization on EVERY transcript path. When
        # it is NOT enabled the pipeline stays light (solo, smooth crop-follow).
        analysis_turns: list[dict] = []
        if config.MULTI_SPEAKER:
            reason = diarization.unavailable_reason()
            if reason:
                job.update(message=f"multi-speaker OFF: {reason}")
            else:
                job.update(message="multi-speaker ON: running diarization...")
        if diarization.diarization_available():
            try:
                if not audio_path:
                    audio_path, info2 = await asyncio.to_thread(
                        downloader.download_audio_only, request.url, str(work_dir))
                    if not duration:
                        duration = float((info2 or {}).get("duration") or 0.0)
                if audio_path and duration > 0:
                    full_audio = str(work_dir / "diar_full.wav")
                    await asyncio.to_thread(renderer.cut_audio, audio_path, 0.0, duration, full_audio)
                    analysis_turns = await asyncio.to_thread(diarization.diarize, full_audio)
                    if analysis_turns:
                        job.update(message=f"diarization OK: {len(analysis_turns)} speaker turns")
            except Exception as e:
                job.update(message=f"multi-speaker diarization failed: {e}")
                analysis_turns = []
        analysis = await asyncio.to_thread(
            analyzer.find_viral_moments,
            analysis_segments, request.max_clips,
            config.MIN_CLIP_SEC, config.MAX_CLIP_SEC, analysis_turns,
        )
        highlights = analysis.highlights[:request.max_clips]
        # CUT RULE (in code): trim trailing filler/dead air the LLM may have
        # left — every clip must end right after the payoff's final word.
        _snap_cut_boundaries(highlights, analysis_segments, config.MIN_CLIP_SEC)

        # ---- 3. render each clip (bounded by CLIPPER_MAX_PARALLEL) ----
        total = max(1, len(highlights))
        sem = asyncio.Semaphore(max(1, config.MAX_PARALLEL))
        done = 0
        lock = asyncio.Lock()

        async def render_worker(i: int, hl):
            nonlocal done
            async with sem:
                if job._cancel:
                    return None
                job.update(status="rendering", stage=f"render_{i + 1}")
                # Give this clip its own share of the bar [0.45, 1.0], so each
                # clip reports fine-grained progress through its own sub-stages.
                span_start = 0.45 + 0.55 * (i / total)
                span_end = 0.45 + 0.55 * ((i + 1) / total)
                clip = await _render_one_clip(
                    job, request.url, hl, i + 1,
                    used_captions, caption_lang, full_words, work_dir,
                    span_start=span_start, span_end=span_end, total_clips=total)
                async with lock:
                    done += 1
                    job.update(progress=span_end,
                               message=f"Rendered {done}/{total} clips")
                return clip

        # return_exceptions=True -> one failed clip must NOT abort the whole job;
        # failed clips are skipped and the rest are returned.
        rendered = await asyncio.gather(
            *(render_worker(i, hl) for i, hl in enumerate(highlights)),
            return_exceptions=True,
        )
        clips: list = []
        failures = 0
        error_detail = ""
        for c in rendered:
            if isinstance(c, BaseException):
                failures += 1
                error_detail = _brief_error(c)
                continue
            if c is not None:
                clips.append(c)

        if not clips:
            raise RuntimeError(
                f"Semua {failures} clip gagal dirender. Penyebab: {error_detail or 'tidak diketahui'}")
        job.update(status="done", stage="done", progress=1.0,
                   message=f"Ready: {len(clips)} clips", clips=clips)
        _cleanup_old_jobs()

    except Exception as e:
        job.update(status="error", stage="error", error=str(e), message=str(e))
        raise
