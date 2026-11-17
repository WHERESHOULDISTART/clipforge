"""Step 1 — fetch the source video with yt-dlp (or accept a local file)."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

from .config import settings
from .models import VideoInfo

_URL_HINT = re.compile(r"^(https?://|www\.|m\.|music\.)|youtu\.?be|youtube\.com|twitch\.tv|kick\.com", re.I)


class DownloadError(RuntimeError):
    """A download problem with a message meant for humans."""


def is_url(source: str) -> bool:
    s = source.strip()
    if Path(s).expanduser().exists():
        return False
    return bool(_URL_HINT.search(s))


def normalize_url(source: str) -> str:
    s = source.strip().strip('"').strip("'")
    if not re.match(r"^https?://", s, re.I):
        s = "https://" + s
    return s


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    return float(json.loads(out)["format"]["duration"])


def _fmt_dur(seconds: float) -> str:
    seconds = int(seconds or 0)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m {s:02d}s"


def _friendly(exc: Exception) -> str:
    msg = str(exc)
    low = msg.lower()
    if "sign in to confirm" in low or "not a bot" in low:
        return ("YouTube blocked the download from this server (\"confirm you're not a bot\"). "
                "Wait a few minutes and try again, or download the video yourself and upload the file instead.")
    if "private video" in low or "members-only" in low or "join this channel" in low:
        return "This video is private or members-only, so it can't be downloaded."
    if "age" in low and "restrict" in low or "inappropriate for some users" in low:
        return "This video is age-restricted and can't be downloaded without signing in. Upload the file instead."
    if "is not available" in low or "video unavailable" in low:
        return "YouTube says this video is unavailable (removed, region-locked or the link is wrong)."
    if "unsupported url" in low:
        return "That link isn't a video ClipForge can download. Paste a normal YouTube video link."
    if "http error 403" in low:
        return "YouTube refused the download (HTTP 403). Update the downloader (pip install -U yt-dlp) and try again."
    return f"Download failed: {msg.splitlines()[-1] if msg else exc!r}"


def download(source: str, progress=None, max_seconds: float | None = None) -> VideoInfo:
    """Download a YouTube URL, or wrap a local file. Returns VideoInfo.

    `progress` is an optional callback(float 0..1, str message).
    `max_seconds` limits a long video (stream VOD) to its first N seconds.
    """
    settings.ensure_dirs()
    source = source.strip()

    if not is_url(source):
        path = Path(source).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"No such file: {path}")
        vid = hashlib.sha1(str(path).encode()).hexdigest()[:11]
        return VideoInfo(id=vid, title=path.stem, url=str(path), duration=probe_duration(path), path=path)

    import yt_dlp  # imported lazily so local-file mode works without network

    url = normalize_url(source)
    base_opts = {"noplaylist": True, "quiet": True, "no_warnings": True, "noprogress": True}

    # 1) Look before downloading: refuse live streams (they'd record forever)
    try:
        with yt_dlp.YoutubeDL(base_opts) as ydl:
            meta = ydl.extract_info(url, download=False)
    except Exception as exc:  # noqa: BLE001
        raise DownloadError(_friendly(exc)) from exc
    if meta.get("_type") == "playlist":
        entries = [e for e in (meta.get("entries") or []) if e]
        if not entries:
            raise DownloadError("That's a playlist with no videos. Paste a single video link.")
        meta = entries[0]
        url = meta.get("webpage_url") or meta.get("original_url") or url
    if meta.get("is_live") or meta.get("live_status") in ("is_live", "is_upcoming"):
        raise DownloadError("This stream is still live (or hasn't started). Wait until it ends and the "
                            "replay (VOD) is available, then paste the link again.")

    duration = float(meta.get("duration") or 0)
    if progress:
        progress(0.0, f"Found: {meta.get('title', 'video')} ({_fmt_dur(duration)})")

    clip_range = None
    if max_seconds and duration and duration > max_seconds + 30:
        clip_range = (0, float(max_seconds))
        if progress:
            progress(0.0, f"Long video — using the first {_fmt_dur(max_seconds)} of {_fmt_dur(duration)}")

    def hook(d):
        if progress and d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes", 0)
            if total:
                progress(done / total, f"Downloading {done / total:.0%} of {total / 1e6:,.0f} MB")

    suffix = f"_first{int(clip_range[1])}s" if clip_range else ""
    opts = {
        **base_opts,
        "format": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best",
        "merge_output_format": "mp4",
        "outtmpl": str(settings.downloads_dir / f"%(id)s{suffix}.%(ext)s"),
        "progress_hooks": [hook],
    }
    if clip_range:
        from yt_dlp.utils import download_range_func

        opts["download_ranges"] = download_range_func(None, [clip_range])
        opts["force_keyframes_at_cuts"] = True

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            path = Path(ydl.prepare_filename(info)).with_suffix(".mp4")
    except Exception as exc:  # noqa: BLE001
        raise DownloadError(_friendly(exc)) from exc

    if not path.exists():  # merge may have produced a different container
        candidates = sorted(settings.downloads_dir.glob(f"{info['id']}{suffix}.*"))
        candidates = [c for c in candidates if not c.name.endswith((".json", ".part"))]
        if not candidates:
            raise DownloadError("The download finished but no video file was produced. Try again.")
        path = candidates[0]

    return VideoInfo(
        id=info["id"] + suffix,
        title=info.get("title", info["id"]),
        url=info.get("webpage_url", url),
        duration=probe_duration(path),
        channel=info.get("uploader", ""),
        path=path,
    )
