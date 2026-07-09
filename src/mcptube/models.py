"""Domain models for mcptube."""

from datetime import datetime, timezone

from pydantic import BaseModel, Field, computed_field


class TranscriptSegment(BaseModel):
    """A single caption entry from the video transcript."""

    start: float  # start time in seconds
    duration: float  # duration in seconds
    text: str

    @computed_field
    @property
    def end(self) -> float:
        """End time in seconds."""
        return self.start + self.duration


class Chapter(BaseModel):
    """A chapter marker from the video."""

    title: str
    start: float  # start time in seconds


class Video(BaseModel):
    """Core domain entity representing an indexed YouTube video."""

    video_id: str  # id namespaced: "{platform}_{native_id}"
    platform: str = "youtube"
    source_url: str = ""
    title: str
    description: str = ""
    channel: str = ""
    duration: float = 0.0  # total duration in seconds
    thumbnail_url: str = ""
    chapters: list[Chapter] = Field(default_factory=list)
    transcript: list[TranscriptSegment] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    added_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @computed_field
    @property
    def url(self) -> str:
        """URL canônica da plataforma de origem."""
        if self.source_url:
            return self.source_url
        return f"https://www.youtube.com/watch?v={self.video_id}"
