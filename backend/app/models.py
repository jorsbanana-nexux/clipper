"""Pydantic models shared across the API and pipeline."""
from pydantic import BaseModel, Field


class ClipScores(BaseModel):
    """Multi-dimension virality breakdown (1-10 each, editor-style rubric).

    Answers the #1 complaint about ALL clipper platforms ("the AI picked the
    safe, boring parts"): the user SEES why a moment was chosen and can judge
    it, instead of trusting a single opaque 1-10 number.
    """
    hook: int = Field(default=5, ge=1, le=10, description="How strongly the first seconds grab attention")
    payoff: int = Field(default=5, ge=1, le=10, description="How satisfying the ending / punchline / takeaway is")
    emotion: int = Field(default=5, ge=1, le=10, description="Emotional charge (surprise, tension, laughter, inspiration)")
    quotability: int = Field(default=5, ge=1, le=10, description="How quotable / shareable the key line is")
    energy: int = Field(default=5, ge=1, le=10, description="Speaking energy & pacing (no dead air, fast back-and-forth)")


class ClipRequest(BaseModel):
    url: str = Field(..., description="Video URL (YouTube, TikTok, Instagram, direct file, ...)")
    max_clips: int = Field(default=8, ge=1, le=15, description="Maximum number of clips to produce")
    mode: str = Field(default="podcast", description="Mode: 'podcast' (v1). 'keyword' is reserved for v2.")
    keywords: str = Field(default="", description="OPTIONAL human steer: topics/keywords the user wants clips about. The #1 clipper complaint is 'AI picked the boring parts' — this gives the human a vote BEFORE rendering.")
    instruction: str = Field(default="", description="OPTIONAL free-text editing instruction (e.g. 'only clips where they argue', 'prefer funny moments').")
    subtitle_style: str = Field(default="mrbeast", description="Subtitle style preset: mrbeast | hormozi | minimal | karaoke | none")
    aspect: str = Field(default="9:16", description="Export aspect ratio: 9:16 | 1:1 | 4:5")


class ViralMoment(BaseModel):
    start_time: float = Field(..., description="Start time in seconds")
    end_time: float = Field(..., description="End time in seconds")
    title: str = Field(..., description="Short, punchy title for the clip")
    reason: str = Field(..., description="Why this moment is engaging / viral-worthy")
    viral_score: int = Field(..., ge=1, le=10, description="Viral potential score 1-10")
    hook: str = Field(..., description="One-line hook for the caption")
    speaker: str = Field("", description="Primary speaker label (empty if no diarization)")
    speakers: list[str] = Field(default_factory=list, description="All speaker labels active in this moment")
    scores: ClipScores = Field(default_factory=ClipScores, description="Per-dimension breakdown of the score")
    caption: str = Field(default="", description="Ready-to-post social caption in the CONTENT's language (first-person, no hashtags inside)")
    hashtags: list[str] = Field(default_factory=list, description="3-8 lowercase hashtags WITHOUT the # symbol, relevant to the clip")


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
    scores: ClipScores = Field(default_factory=ClipScores)
    caption: str = ""
    hashtags: list[str] = Field(default_factory=list)
    srt_url: str = ""  # v0.4: portable captions (CapCut/Premiere importable)


class JobStatus(BaseModel):
    job_id: str
    status: str  # queued | downloading | transcribing | analyzing | rendering | done | error
    progress: float = 0.0
    stage: str = "queued"
    message: str = ""
    clips: list[ClipInfo] = []
    error: str = ""
