"""Pydantic models shared across the API and pipeline."""
from pydantic import BaseModel, Field


class ClipRequest(BaseModel):
    url: str = Field(..., description="Video URL (YouTube, TikTok, Instagram, direct file, ...)")
    max_clips: int = Field(default=8, ge=1, le=15, description="Maximum number of clips to produce")
    mode: str = Field(default="podcast", description="Mode: 'podcast' (v1). 'keyword' is reserved for v2.")


class ViralMoment(BaseModel):
    start_time: float = Field(..., description="Start time in seconds")
    end_time: float = Field(..., description="End time in seconds")
    title: str = Field(..., description="Short, punchy title for the clip")
    reason: str = Field(..., description="Why this moment is engaging / viral-worthy")
    viral_score: int = Field(..., ge=1, le=10, description="Viral potential score 1-10")
    hook: str = Field(..., description="One-line hook for the caption")


class HighlightAnalysis(BaseModel):
    highlights: list[ViralMoment] = Field(..., min_length=1, max_length=15)


class SpeakerTurn(BaseModel):
    speaker: str = Field(..., description="Speaker label (e.g. SPEAKER_00)")
    start: float = Field(..., description="Start time in seconds")
    end: float = Field(..., description="End time in seconds")


class Word(BaseModel):
    word: str
    start: float
    end: float


class ClipInfo(BaseModel):
    index: int
    title: str
    start_time: float
    end_time: float
    duration: float
    viral_score: int
    reason: str
    hook: str
    download_url: str
    filename: str


class JobStatus(BaseModel):
    job_id: str
    status: str  # queued | downloading | transcribing | analyzing | rendering | done | error
    progress: float = 0.0
    stage: str = "queued"
    message: str = ""
    clips: list[ClipInfo] = []
    error: str = ""
