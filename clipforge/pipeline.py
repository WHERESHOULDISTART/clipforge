"""Orchestrates: download → transcribe → highlights → render clips → package.

A `Job` records progress to JSON so the web UI (or a resumed CLI) can read it.
"""

from __future__ import annotations

import json
import threading
import time
import traceback
import uuid
from pathlib import Path
from typing import Callable

from pydantic import BaseModel, Field

from . import downloader, highlighter, packager, transcriber
from .captioner import CaptionStyle
from .config import settings
from .cutter import render_clip
from .models import Clip, VideoInfo

STAGES = ["queued", "downloading", "transcribing", "highlighting", "rendering", "packaging", "done", "error"]


class Job(BaseModel):
    id: str
    source: str
    style: str
    clip_count: int
    reframe: str | None = None
    language: str | None = None
    status: str = "queued"
    progress: float = 0.0
    message: str = ""
    video: VideoInfo | None = None
    clips: list[Clip] = Field(default_factory=list)
    error: str | None = None
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    @property
    def dir(self) -> Path:
        return settings.jobs_dir / self.id

    def save(self) -> None:
        self.updated_at = time.time()
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "job.json").write_text(self.model_dump_json(indent=1))

    @classmethod
    def load(cls, job_id: str) -> "Job":
        return cls.model_validate_json((settings.jobs_dir / job_id / "job.json").read_text())

    @classmethod
    def list_all(cls) -> list["Job"]:
        settings.ensure_dirs()
        jobs = []
        for p in settings.jobs_dir.glob("*/job.json"):
            try:
                jobs.append(cls.model_validate_json(p.read_text()))
            except Exception:
                continue
        return sorted(jobs, key=lambda j: -j.created_at)


def new_job(source: str, style: str | None = None, clip_count: int | None = None,
            reframe: str | None = None, language: str | None = None) -> Job:
    settings.ensure_dirs()
    job = Job(id=uuid.uuid4().hex[:10], source=source.strip(), style=style or settings.default_style,
              clip_count=clip_count or settings.default_clip_count, reframe=reframe, language=language)
    job.save()
    return job


def run_job(job: Job, on_update: Callable[[Job], None] | None = None) -> Job:
    """Run the full pipeline synchronously, updating `job` as it goes."""

    def update(status: str | None = None, progress: float | None = None, message: str | None = None):
        if status:
            job.status = status
        if progress is not None:
            job.progress = round(float(progress), 3)
        if message is not None:
            job.message = message
        job.save()
        if on_update:
            on_update(job)

    # Stage weights for the overall progress bar
    weights = {"downloading": (0.0, 0.15), "transcribing": (0.15, 0.45), "highlighting": (0.45, 0.55),
               "rendering": (0.55, 0.95), "packaging": (0.95, 1.0)}

    def stage_cb(stage):
        lo, hi = weights[stage]
        return lambda frac, msg: update(progress=lo + (hi - lo) * max(0.0, min(frac, 1.0)), message=msg)

    try:
        update("downloading", 0.0, "Fetching video")
        video = downloader.download(job.source, progress=stage_cb("downloading"))
        job.video = video
        update(message=f"Got: {video.title}")

        update("transcribing", weights["transcribing"][0], "Loading Whisper model")
        transcript = transcriber.transcribe(video.path, progress=stage_cb("transcribing"), language=job.language)
        if not transcript.words:
            raise RuntimeError("No speech detected in this video — nothing to clip.")

        update("highlighting", weights["highlighting"][0], "Finding the best moments")
        highlights = highlighter.find_highlights(transcript, video.path, n=job.clip_count,
                                                 progress=stage_cb("highlighting"))
        if not highlights:
            raise RuntimeError("Could not find any clip-worthy moments.")

        style = CaptionStyle.load(job.style)
        out_dir = settings.clips_dir / job.id
        clips: list[Clip] = []
        lo, hi = weights["rendering"]
        for i, h in enumerate(highlights, start=1):
            update(status="rendering", progress=lo + (hi - lo) * (i - 1) / len(highlights),
                   message=f"Rendering clip {i}/{len(highlights)}: {h.title}")
            clip = render_clip(video.path, h, transcript, style, out_dir, i, reframe=job.reframe)
            clips.append(clip)
            job.clips = clips
            update()

        update("packaging", weights["packaging"][0], "Writing captions & hashtags")
        job.clips = packager.package(clips, video)
        update("done", 1.0, f"{len(job.clips)} clips ready")
    except Exception as exc:  # noqa: BLE001
        job.error = f"{exc}"
        update("error", message=str(exc))
        traceback.print_exc()
    return job


# ---- simple in-process job runner for the web UI --------------------------

_threads: dict[str, threading.Thread] = {}
_lock = threading.Lock()


def start_job_async(job: Job) -> None:
    def target():
        with _lock:  # one render at a time keeps CPU/GPU sane
            run_job(job)

    t = threading.Thread(target=target, daemon=True, name=f"job-{job.id}")
    _threads[job.id] = t
    t.start()
