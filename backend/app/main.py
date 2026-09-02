"""Clipper backend — FastAPI application."""
import os
import shutil

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import config
from .jobs import JobManager, manager
from .models import ClipRequest, JobStatus


app = FastAPI(
    title="Clipper API",
    description="AI podcast clipping: paste a URL, get viral 9:16 clips with word-by-word captions.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve rendered clips
config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/clips", StaticFiles(directory=str(config.OUTPUT_DIR)), name="clips")


@app.get("/health")
def health():
    key_set = bool(config.OPENAI_API_KEY)
    return {
        "status": "ok",
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "openai_key": "set" if key_set else "missing",
        "multi_speaker": bool(config.MULTI_SPEAKER and config.HUGGINGFACE_TOKEN),
    }


@app.post("/jobs", response_model=JobStatus)
def create_job(request: ClipRequest):
    if not config.OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY belum diset. Jalankan setup.bat lalu restart backend (cek GET /health).")
    job = manager.create()
    manager.start(job, request)
    return job.status


@app.get("/jobs/{job_id}", response_model=JobStatus)
def get_job(job_id: str):
    job = manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.status


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), reload=True)
