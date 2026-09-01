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


async def _run_pipeline(job: Job, request) -> None:
    work_dir = config.OUTPUT_DIR / job.job_id
    work_dir.mkdir(parents=True, exist_ok=True)
    try:
        # ---- 1. transcript: captions-first (no audio) -> fallback full audio ----
        job.update(status="downloading", stage="transcript", progress=0.05,
                   message="Fetching transcript (captions-first)...")
        caption_segments = await asyncio.to_thread(downloader.fetch_captions, request.url)

        title = "Untitled"
        used_captions = bool(caption_segments)
        full_words: list[dict] = []
        analysis_segments: list[dict] = []
        transcript_text: str = ""

        if used_captions:
            transcript_text = " ".join(s.get("text", "") for s in caption_segments)
            analysis_segments = caption_segments
            job.update(stage="transcript_captions", progress=0.2,
                       message="Transcript ready (captions, no audio downloaded)")
        else:
            job.update(stage="download_audio", message="No captions — downloading audio...")
            audio_path, info = await asyncio.to_thread(downloader.download_audio_only, request.url, str(work_dir))
            title = (info or {}).get("title", "Untitled")
            job.update(stage="transcribe", progress=0.2,
                       message="Transcribing speech (word-level)...")
            transcript = await asyncio.to_thread(transcriber.transcribe, audio_path)
            transcript_text = transcript.get("text", "")
            full_words = transcriber.words_from_transcript(transcript)
            analysis_segments = transcriber.segments_from_transcript(transcript)

        # ---- 2. analysis ----
        job.update(status="analyzing", stage="analyze", progress=0.35,
                   message="Finding viral moments...")
        # B2: run diarization once on the full audio (if enabled) so analysis is
        # speaker-aware. On the captions path we may not have the full audio yet,
        # so diarization is skipped there (turns = []).
        analysis_turns: list[dict] = []
        if diarization.diarization_available() and not used_captions:
            try:
                full_audio = str(work_dir / "diar_full.wav")
                await asyncio.to_thread(renderer.cut_audio, audio_path, 0.0, duration, full_audio)
                analysis_turns = await asyncio.to_thread(diarization.diarize, full_audio)
            except Exception:
                analysis_turns = []
        analysis = await asyncio.to_thread(
            analyzer.find_viral_moments,
            transcript_text, analysis_segments, request.max_clips,
            config.MIN_CLIP_SEC, config.MAX_CLIP_SEC, analysis_turns,
        )
        highlights = analysis.highlights[:request.max_clips]

        # ---- 3. render each clip ----
        total = max(1, len(highlights))
        clips = []
        for i, hl in enumerate(highlights):
            if job._cancel:
                break
            frac = 0.45 + 0.55 * (i / total)
            job.update(status="rendering", stage=f"render_{i+1}", progress=frac,
                       message=f"Rendering clip {i+1}/{total}: {hl.title}")

            # Pad the moment so it's never cut off even if timestamps drift ~1-2s.
            pad = config.PADDING_SEC
            padded_start = max(0.0, hl.start_time - pad)
            padded_end = hl.end_time + pad

            seg_dir = work_dir / f"clip_{i+1}"
            seg_dir.mkdir(exist_ok=True)

            # download only this (padded) video segment
            raw_path = await asyncio.to_thread(
                downloader.download_segment, request.url, padded_start, padded_end, str(seg_dir))

            # words for this clip:
            #   captions path -> download only this (padded) audio segment + Whisper (accurate word timing)
            #   fallback path -> reuse full-transcript words (already have them)
            local_words: list[dict] = []
            aseg: str | None = None
            if used_captions:
                try:
                    aseg = await asyncio.to_thread(
                        downloader.download_audio_segment, request.url, padded_start, padded_end, str(seg_dir))
                    t = await asyncio.to_thread(transcriber.transcribe, aseg)
                    local_words = transcriber.words_from_transcript(t)
                except Exception as e:
                    job.update(message=f"clip {i+1}: audio segment Whisper failed ({e}); subtitle skipped")
            else:
                local_words = [
                    {**w, "start": w["start"] - padded_start, "end": w["end"] - padded_start}
                    for w in full_words
                    if w["end"] >= padded_start and w["start"] <= padded_end
                ]

            # --- v0.2 multi-speaker: decide single vs duo via diarization (optional) ---
            turns: list[dict] = []
            if diarization.diarization_available():
                try:
                    # aseg is the short clip audio (captions path, 0-bound timestamps).
                    # raw_path is the padded video segment — always present. Convert the
                    # segment to 16 kHz mono WAV before diarization. Only operate on the
                    # short per-clip segment so it stays light.
                    if aseg:
                        diar_audio = aseg
                    else:
                        diar_audio = str(seg_dir / "diar_audio.wav")
                        await asyncio.to_thread(renderer.cut_audio, raw_path, 0.0, padded_end - padded_start, diar_audio)
                    turns = await asyncio.to_thread(diarization.diarize, diar_audio)
                except Exception:
                    turns = []
            # ---- B5 dynamic switching: build a clip-relative layout timeline ----
            if config.LAYOUT_MODE in ("single", "duo"):
                clip_layout = config.LAYOUT_MODE
                timeline = [{"start": 0.0, "end": padded_end - padded_start, "layout": clip_layout}]
            elif turns:
                # absolute-turn timeline -> clip-relative -> per-segment layouts
                abs_timeline = layout.layout_timeline(turns, hl.start_time, hl.end_time)
                timeline = compositor.rel_timeline(abs_timeline, padded_start)
                timeline = [s for s in timeline if s["end"] > s["start"]]
            else:
                clip_layout = layout.choose_template([], 0.0, 0.0)
                timeline = [{"start": 0.0, "end": padded_end - padded_start, "layout": clip_layout}]

            # reframe to 9:16 (single crop-follow OR duo split-screen OR dynamic mix)
            vertical = str(seg_dir / "vertical.mp4")
            distinct = {s.get("layout") for s in timeline}
            if len(timeline) > 1 and len(distinct) > 1:
                await asyncio.to_thread(compositor.render_dynamic_clip, raw_path, timeline, vertical)
            elif timeline and timeline[0].get("layout") == "duo":
                await asyncio.to_thread(face_tracker.reframe_duo, raw_path, vertical)
            else:
                samples = await asyncio.to_thread(face_tracker.analyze_faces, raw_path)
                await asyncio.to_thread(face_tracker.reframe_to_vertical, raw_path, vertical, samples)

            # word-by-word subtitles + effects
            ass_path = str(seg_dir / "subs.ass")
            if local_words:
                ass_content = subtitles.words_to_ass(local_words, config.TARGET_WIDTH, config.TARGET_HEIGHT)
                Path(ass_path).write_text(ass_content, encoding="utf-8")

            final = str(seg_dir / "final.mp4")
            if local_words:
                await asyncio.to_thread(renderer.burn_subtitles_and_effects, vertical, ass_path, final)
            else:
                shutil.copy(vertical, final)

            thumb = str(seg_dir / "thumb.jpg")
            await asyncio.to_thread(renderer.make_thumbnail, final, thumb)

            rel = f"/clips/{job.job_id}/clip_{i+1}/final.mp4"
            clips.append(ClipInfo(
                index=i + 1,
                title=hl.title,
                start_time=hl.start_time,
                end_time=hl.end_time,
                duration=round(hl.end_time - hl.start_time, 2),
                viral_score=hl.viral_score,
                reason=hl.reason,
                hook=hl.hook,
                download_url=rel,
                filename=f"{job.job_id}_clip_{i+1}.mp4",
            ))

        job.update(status="done", stage="done", progress=1.0,
                   message=f"Ready: {len(clips)} clips", clips=clips)

    except Exception as e:
        job.update(status="error", stage="error", error=str(e), message=str(e))
        raise
