"""Shared data models."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class Word(BaseModel):
    text: str
    start: float
    end: float
    prob: float = 1.0


class Segment(BaseModel):
    start: float
    end: float
    text: str
    words: list[Word] = Field(default_factory=list)


class Transcript(BaseModel):
    language: str = "en"
    duration: float = 0.0
    segments: list[Segment] = Field(default_factory=list)

    @property
    def words(self) -> list[Word]:
        return [w for s in self.segments for w in s.words]

    def text_between(self, start: float, end: float) -> str:
        return " ".join(w.text for w in self.words if w.start >= start and w.end <= end).strip()


class Highlight(BaseModel):
    start: float
    end: float
    title: str
    hook: str = ""
    reason: str = ""
    score: float = 0.0  # 0..100 "virality" estimate
    mood: str = "general"  # funny | intense | insightful | emotional | general

    @property
    def duration(self) -> float:
        return self.end - self.start


class PlatformPost(BaseModel):
    platform: str
    title: str
    caption: str
    hashtags: list[str] = Field(default_factory=list)

    @property
    def full_caption(self) -> str:
        tags = " ".join(f"#{t.lstrip('#')}" for t in self.hashtags)
        return f"{self.caption}\n\n{tags}".strip()


class Clip(BaseModel):
    index: int
    highlight: Highlight
    video_path: Path
    thumbnail_path: Path | None = None
    srt_path: Path | None = None
    posts: dict[str, PlatformPost] = Field(default_factory=dict)


class VideoInfo(BaseModel):
    id: str
    title: str
    url: str
    duration: float
    channel: str = ""
    path: Path
