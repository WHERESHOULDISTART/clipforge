"""Step 1 — fetch the source video with yt-dlp (or accept a local file)."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from .config import settings
from .models import VideoInfo

YOUTUBE_PREFIXES = ("http://", "https://", "youtu.be", "www.", "youtube.com")


def is_url(source: str) -> bool:
    return source.startswith(YOUTUBE_PREFIXES)


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    return float(json.loads(out)["format"]["duration"])


def download(source: str, progress=None) -> VideoInfo:
    """Download a YouTube URL, or wrap a local file. Returns VideoInfo.

    `progress` is an optional callback(float 0..1, str message).
    """
    settings.ensure_dirs()

    if not is_url(source):
        path = Path(source).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(path)
        vid = hashlib.sha1(str(path).encode()).hexdigest()[:11]
        return VideoInfo(id=vid, title=path.stem, url=str(path), duration=probe_duration(path),
                         path=path)

    import yt_dlp  # imported lazily so local-file mode works without network

    def hook(d):
        if progress and d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes", 0)
            if total:
                progress(done / total, f"Downloading {done / total:.0%}")

    opts = {
        "format": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "outtmpl": str(settings.downloads_dir / "%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [hook],
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(source, download=True)
        path = Path(ydl.prepare_filename(info)).with_suffix(".mp4")

    if not path.exists():  # merge may have produced a different container
        candidates = list(settings.downloads_dir.glob(f"{info['id']}.*"))
        if not candidates:
            raise RuntimeError("yt-dlp finished but no file was produced")
        path = candidates[0]

    return VideoInfo(
        id=info["id"],
        title=info.get("title", info["id"]),
        url=info.get("webpage_url", source),
        duration=float(info.get("duration") or probe_duration(path)),
        channel=info.get("uploader", ""),
        path=path,
    )
