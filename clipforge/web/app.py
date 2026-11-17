"""FastAPI web UI. Run with `clipforge serve` or `uvicorn clipforge.web.app:app`."""

from __future__ import annotations

import json
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from .. import __version__
from ..captioner import CaptionStyle, list_styles
from ..config import settings
from ..packager import PLATFORMS
from ..pipeline import Job, new_job, start_job_async
from ..publisher import browser as browser_publisher

HERE = Path(__file__).parent
app = FastAPI(title="ClipForge", version=__version__)
templates = Jinja2Templates(directory=str(HERE / "templates"))
settings.ensure_dirs()
app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")
app.mount("/clips", StaticFiles(directory=str(settings.clips_dir)), name="clips")


class JobRequest(BaseModel):
    source: str
    style: str = settings.default_style
    clip_count: int = settings.default_clip_count
    reframe: str | None = None
    language: str | None = None


class PublishRequest(BaseModel):
    platform: str
    caption: str | None = None
    title: str | None = None


def _job_payload(job: Job) -> dict:
    data = json.loads(job.model_dump_json())
    for c in data.get("clips", []):
        c["video_url"] = f"/clips/{job.id}/{Path(c['video_path']).name}"
        c["thumb_url"] = f"/clips/{job.id}/{Path(c['thumbnail_path']).name}" if c.get("thumbnail_path") else None
        for p in c.get("posts", {}).values():
            p["full_caption"] = (p["caption"] + "\n\n" + " ".join("#" + t for t in p["hashtags"])).strip()
    return data


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    styles = []
    for name in list_styles():
        s = CaptionStyle.load(name)
        styles.append({"id": name, "name": s.name, "description": s.description})
    return templates.TemplateResponse(request, "index.html", {
        "styles": styles,
        "platforms": PLATFORMS,
        "defaults": {"style": settings.default_style, "clip_count": settings.default_clip_count},
        "version": __version__,
    })


@app.get("/api/styles")
def api_styles():
    return [{"id": n, **CaptionStyle.load(n).__dict__} for n in list_styles()]


@app.get("/api/jobs")
def api_jobs():
    return [_job_payload(j) for j in Job.list_all()[:30]]


@app.post("/api/jobs")
def api_create_job(req: JobRequest):
    if not req.source.strip():
        raise HTTPException(400, "source is required")
    job = new_job(req.source, req.style, max(1, min(req.clip_count, 20)), req.reframe, req.language)
    start_job_async(job)
    return _job_payload(job)


@app.get("/api/jobs/{job_id}")
def api_job(job_id: str):
    try:
        return _job_payload(Job.load(job_id))
    except FileNotFoundError:
        raise HTTPException(404, "job not found")


@app.post("/api/jobs/{job_id}/clips/{index}/publish")
def api_publish(job_id: str, index: int, req: PublishRequest):
    job = Job.load(job_id)
    clip = next((c for c in job.clips if c.index == index), None)
    if not clip:
        raise HTTPException(404, "clip not found")
    if req.platform not in PLATFORMS:
        raise HTTPException(400, f"unknown platform {req.platform}")
    post = clip.posts.get(req.platform)
    caption = req.caption if req.caption is not None else (post.full_caption if post else "")
    title = req.title if req.title is not None else (post.title if post else clip.highlight.title)

    state = browser_publisher.start(req.platform, clip.video_path, caption=caption, title=title)
    return {"ok": True, "session": state}


@app.get("/api/publish/{session_id}")
def api_publish_status(session_id: str):
    st = browser_publisher.status(session_id)
    if not st:
        raise HTTPException(404, "no such publish session")
    return st


@app.get("/api/jobs/{job_id}/clips/{index}/download")
def api_download(job_id: str, index: int):
    job = Job.load(job_id)
    clip = next((c for c in job.clips if c.index == index), None)
    if not clip:
        raise HTTPException(404, "clip not found")
    safe = "".join(ch if ch.isalnum() or ch in "-_ " else "" for ch in clip.highlight.title).strip() or f"clip_{index}"
    return FileResponse(clip.video_path, media_type="video/mp4", filename=f"{safe}.mp4")
