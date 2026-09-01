"""In-process job manager: async pipeline execution with progress tracking.

v1 keeps jobs in memory (single-process). Swapping the dict for Redis is a
documented future step for horizontal scaling.
"""
import asyncio
import shutil
import uuid
from pathlib import Path

from . import config, downloader, transcriber, analyzer, subtitles, face_tracker, renderer
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
        # 1. audio-only download + metadata
        job.update(status="downloading", stage="download_audio", progress=0.05,
                   message="Downloading audio track...")
        audio_path, info = await asyncio.to_thread(downloader.download_audio_only, request.url, str(work_dir))
        title = (info or {}).get("title", "Untitled")
        duration = float((info or {}).get("duration") or 0.0)

        # 2. transcribe
        job.update(status="transcribing", stage="transcribe", progress=0.2,
                   message="Transcribing speech (word-level)...")
        transcript = await asyncio.to_thread(transcriber.transcribe, audio_path)
        words = transcriber.words_from_transcript(transcript)
        segments = transcriber.segments_from_transcript(transcript)

        # 3. analyze
        job.update(status="analyzing", stage="analyze", progress=0.35,
                   message="Finding viral moments...")
        analysis = await asyncio.to_thread(
            analyzer.find_viral_moments,
            transcript.get("text", ""), segments, request.max_clips,
            config.MIN_CLIP_SEC, config.MAX_CLIP_SEC,
        )
        highlights = analysis.highlights[:request.max_clips]

        # 4. render each clip
        total = max(1, len(highlights))
        clips = []
        for i, hl in enumerate(highlights):
            if job._cancel:
                break
            frac = 0.45 + 0.55 * (i / total)
            job.update(status="rendering", stage=f"render_{i+1}", progress=frac,
                       message=f"Rendering clip {i+1}/{total}: {hl.title}")

            seg_dir = work_dir / f"clip_{i+1}"
            seg_dir.mkdir(exist_ok=True)

            # download only this segment (light) then cut
            raw_path = await asyncio.to_thread(downloader.download_segment, request.url, hl.start_time, hl.end_time, str(seg_dir))

            # face-track reframe to 9:16
            samples = await asyncio.to_thread(face_tracker.analyze_faces, raw_path)
            vertical = str(seg_dir / "vertical.mp4")
            await asyncio.to_thread(face_tracker.reframe_to_vertical, raw_path, vertical, samples)

            # word-by-word subtitles (clip-local timing)
            local_words = [w for w in words if w["end"] >= hl.start_time and w["start"] <= hl.end_time]
            local_words = [{**w, "start": w["start"] - hl.start_time, "end": w["end"] - hl.start_time} for w in local_words]
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

            # serve from output dir (static mount in main.py)
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
