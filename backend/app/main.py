"""Clipper backend — FastAPI application."""
import io
import json
import os
import shutil
import zipfile

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .diarization import diarization_available, unavailable_reason
from .jobs import JobManager, manager
from .models import ClipRequest, JobStatus


app = FastAPI(
    title="Clipper API",
    description="AI podcast clipping: paste a URL, get viral 9:16 clips with word-by-word captions.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS or ["*"],  # explicit allow-list (see config.py)
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve rendered clips
config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/clips", StaticFiles(directory=str(config.OUTPUT_DIR)), name="clips")


@app.get("/health")
def health():
    if config.ANALYSIS_BACKEND == "gemini":
        analysis_ready = bool(config.GEMINI_API_KEY)
        analysis_label = "gemini"
    else:
        analysis_ready = bool(config.OPENAI_API_KEY)
        analysis_label = "openai"
    return {
        "status": "ok",
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "whisper_backend": config.WHISPER_BACKEND,
        "analysis_backend": analysis_label,
        "openai_key": "set" if config.OPENAI_API_KEY else "missing",
        "gemini_key": "set" if config.GEMINI_API_KEY else "missing",
        "analysis_ready": analysis_ready,
        "multi_speaker": diarization_available(),
        "multi_speaker_env": bool(config.MULTI_SPEAKER and config.HUGGINGFACE_TOKEN),
        "multi_speaker_reason": unavailable_reason() or "active",
    }


def _analysis_key_ready() -> bool:
    if config.ANALYSIS_BACKEND == "gemini":
        return bool(config.GEMINI_API_KEY)
    return bool(config.OPENAI_API_KEY)


@app.post("/jobs", response_model=JobStatus)
async def create_job(request: ClipRequest):
    """FIX(bug): must be `async def` so FastAPI runs it on the main event loop.
    A sync endpoint runs in a threadpool thread with NO running asyncio loop,
    so manager.start() -> asyncio.create_task() raised
    `RuntimeError: no running event loop` (always -> 500 on every /jobs call)."""
    if not _analysis_key_ready():
        if config.ANALYSIS_BACKEND == "gemini":
            detail = (
                "GEMINI_API_KEY belum diset. Isi GEMINI_API_KEY=... di file .env "
                "(ambil gratis di https://aistudio.google.com/apikey) lalu restart "
                "backend (cek GET /health).")
        else:
            detail = (
                "OPENAI_API_KEY belum diset. Isi OPENAI_API_KEY=sk-... di file .env "
                "(lihat README: 'Menjalankan Secara Lokal') lalu restart backend "
                "(cek GET /health).")
        raise HTTPException(status_code=500, detail=detail)
    job = manager.create()
    # manager.start is sync but calls asyncio.create_task(); running it from an
    # async endpoint puts it on the event loop thread, where the loop exists.
    manager.start(job, request)
    return job.status


@app.get("/jobs/{job_id}", response_model=JobStatus)
def get_job(job_id: str):
    job = manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.status


@app.get("/styles")
def list_styles():
    """Subtitle style presets available for ClipRequest.subtitle_style."""
    return {"styles": list(config.SUBTITLE_PRESETS.keys())}


@app.get("/jobs/{job_id}/zip")
def zip_job(job_id: str):
    """Download ALL finished clips in one ZIP, plus metadata.json with each
    clip's ready-to-post caption + hashtags (v0.3).

    Answers a concrete Vizard complaint ("can't download all clips at once,
    one by one only") and saves the creator the copy-paste round trip.
    """
    job = manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status.status != "done" or not job.status.clips:
        raise HTTPException(status_code=400, detail="Job has no finished clips yet")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        meta = []
        for c in job.status.clips:
            abs_path = config.OUTPUT_DIR / job_id / f"clip_{c.index}" / f"{c.filename}"
            # filename convention: {job}_clip_{i}.mp4, on disk the rendered
            # file is final.mp4 (or final_aspect.mp4 after aspect conversion).
            for cand in ("final_aspect.mp4", "final.mp4"):
                p = config.OUTPUT_DIR / job_id / f"clip_{c.index}" / cand
                if p.exists():
                    abs_path = p
                    break
            if abs_path.exists():
                zf.write(abs_path, arcname=c.filename)
                meta.append({
                    "file": c.filename,
                    "index": c.index,
                    "title": c.title,
                    "start": c.start_time,
                    "end": c.end_time,
                    "duration_sec": c.duration,
                    "viral_score": c.viral_score,
                    "scores": c.scores.model_dump() if c.scores else {},
                    "reason": c.reason,
                    "hook": c.hook,
                    "caption": c.caption,
                    "hashtags": c.hashtags,
                })
        zf.writestr("metadata.json", json.dumps(meta, indent=2, ensure_ascii=False))
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="clips_{job_id}.zip"'},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), reload=True)
