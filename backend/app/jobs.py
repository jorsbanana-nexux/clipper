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
import shutil
import uuid
from pathlib import Path

from . import config, downloader, transcriber, analyzer, subtitles, face_tracker, renderer, diarization, layout, compositor
from .models import ClipInfo, JobStatus


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

    def update(self, **kw):
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


async def _render_one_clip(job, url, hl, index, used_captions, caption_lang, full_words, work_dir):
    """Render a single clip end-to-end. Returns a ClipInfo, or raises on error."""
    pad = config.PADDING_SEC
    padded_start = max(0.0, hl.start_time - pad)
    padded_end = hl.end_time + pad

    seg_dir = work_dir / f"clip_{index}"
    seg_dir.mkdir(exist_ok=True)

    raw_path = await asyncio.to_thread(
        downloader.download_segment, url, padded_start, padded_end, str(seg_dir))

    local_words: list[dict] = []
    aseg: str | None = None
    if used_captions:
        try:
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
    if diarization.diarization_available():
        try:
            diar_audio = str(seg_dir / "diar_audio.wav")
            diar_src = aseg if aseg else raw_path
            await asyncio.to_thread(renderer.cut_audio, diar_src, 0.0, padded_end - padded_start, diar_audio)
            turns = await asyncio.to_thread(diarization.diarize, diar_audio)
        except Exception:
            turns = []

    if config.LAYOUT_MODE in ("single", "duo"):
        clip_layout = config.LAYOUT_MODE
        timeline = [{"start": 0.0, "end": padded_end - padded_start, "layout": clip_layout}]
    elif turns:
        # FIX(bug): `turns` are LOCAL — they come from `cut_audio(diar_src,
        # 0.0, padded_len)` on the already-downloaded segment, so time 0 is the
        # start of `raw_path` (== padded_start in the absolute video). The
        # layout timeline must therefore be computed in LOCAL coordinates too.
        # Previously we built it from absolute hl times and then subtracted
        # padded_start again in rel_timeline — a double-shift that misaligned
        # the single/duo switches.
        loc_dur = padded_end - padded_start
        timeline = layout.layout_timeline(turns, 0.0, loc_dur)
        timeline = [s for s in timeline if s["end"] > s["start"]]
    else:
        clip_layout = layout.choose_template([], 0.0, 0.0)
        timeline = [{"start": 0.0, "end": padded_end - padded_start, "layout": clip_layout}]

    vertical = str(seg_dir / "vertical.mp4")
    distinct = {s.get("layout") for s in timeline}
    dynamic_layout = len(timeline) > 1 and len(distinct) > 1
    job.update(status="rendering", stage=f"render_{index}/reframe",
               message=f"Clip {index}: membingkai ulang 9:16 + tracking wajah")
    if dynamic_layout:
        await asyncio.to_thread(compositor.render_dynamic_clip, raw_path, timeline, vertical)
    elif timeline and timeline[0].get("layout") == "duo":
        await asyncio.to_thread(face_tracker.reframe_duo, raw_path, vertical)
    else:
        samples = await asyncio.to_thread(face_tracker.analyze_faces, raw_path)
        await asyncio.to_thread(face_tracker.reframe_to_vertical, raw_path, vertical, samples)

    # B5 sync fix: xfade crossfades shorten the output by (n-1)*CROSSFADE, so the
    # real video is a bit shorter than (padded_end - padded_start). Subtitle times
    # are in local [0, target_dur]; scale them to the ACTUAL rendered duration so
    # word-by-word captions stay exactly in sync with the (slightly compressed)
    # dynamic video instead of running past the end / drifting.
    if dynamic_layout and local_words:
        target_dur = padded_end - padded_start
        actual_dur = renderer.probe_duration(vertical)
        if actual_dur > 0.0 and actual_dur < target_dur * 0.999:
            scale = actual_dur / target_dur
            local_words = [
                {**w, "start": w["start"] * scale, "end": w["end"] * scale}
                for w in local_words
            ]

    ass_path = str(seg_dir / "subs.ass")
    if local_words:
        job.update(status="rendering", stage=f"reframe_{index}/subs",
                   message=f"Clip {index}: membakar subtitle word-by-word + efek")
        ass_content = subtitles.words_to_ass(local_words, config.TARGET_WIDTH, config.TARGET_HEIGHT)
        Path(ass_path).write_text(ass_content, encoding="utf-8")

    final = str(seg_dir / "final.mp4")
    if local_words:
        await asyncio.to_thread(renderer.burn_subtitles_and_effects, vertical, ass_path, final)
    else:
        shutil.copy(vertical, final)

    await asyncio.to_thread(renderer.verify_output, final, max(1.0, (padded_end - padded_start) * 0.5))

    thumb = str(seg_dir / "thumb.jpg")
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
        # speaker-aware. On the captions path we may not have the full audio yet,
        # so diarization is skipped there (turns = []).
        analysis_turns: list[dict] = []
        if diarization.diarization_available() and not used_captions and audio_path:
            try:
                full_audio = str(work_dir / "diar_full.wav")
                await asyncio.to_thread(renderer.cut_audio, audio_path, 0.0, duration, full_audio)
                analysis_turns = await asyncio.to_thread(diarization.diarize, full_audio)
            except Exception:
                analysis_turns = []
        analysis = await asyncio.to_thread(
            analyzer.find_viral_moments,
            analysis_segments, request.max_clips,
            config.MIN_CLIP_SEC, config.MAX_CLIP_SEC, analysis_turns,
        )
        highlights = analysis.highlights[:request.max_clips]

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
                job.update(status="rendering", stage=f"render_{i + 1}",
                           progress=0.45 + 0.55 * (i / total),
                           message=f"Rendering clip {i + 1}/{total}: {hl.title}")
                clip = await _render_one_clip(
                    job, request.url, hl, i + 1,
                    used_captions, caption_lang, full_words, work_dir)
                async with lock:
                    done += 1
                    job.update(progress=0.45 + 0.55 * (done / total),
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
