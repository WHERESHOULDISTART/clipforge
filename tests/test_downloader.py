"""Downloader safeguards, tested offline with a fake yt-dlp."""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from clipforge import downloader  # noqa: E402


@pytest.mark.parametrize("src,expected", [
    ("https://www.youtube.com/watch?v=abc", True),
    ("youtu.be/abc", True),
    ("m.youtube.com/watch?v=abc", True),
    ("www.youtube.com/live/abc", True),
    ("https://www.twitch.tv/videos/123", True),
    ("/definitely/not/here.mp4", False),
])
def test_is_url(src, expected):
    assert downloader.is_url(src) is expected


def test_local_file_is_not_url():
    fixture = ROOT / "tests" / "fixtures" / "sample.mp4"
    if fixture.exists():
        assert downloader.is_url(str(fixture)) is False


def test_normalize_url():
    assert downloader.normalize_url("  youtu.be/abc ") == "https://youtu.be/abc"
    assert downloader.normalize_url("https://youtu.be/abc") == "https://youtu.be/abc"


def _fake_ytdlp(meta):
    mod = types.ModuleType("yt_dlp")

    class YoutubeDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, url, download=False):
            if isinstance(meta, Exception):
                raise meta
            if download:
                raise AssertionError("must not download")
            return meta

    mod.YoutubeDL = YoutubeDL
    return mod


def test_refuses_live_stream(monkeypatch):
    monkeypatch.setitem(sys.modules, "yt_dlp", _fake_ytdlp({"id": "x", "is_live": True, "title": "GTA 6 LIVE"}))
    with pytest.raises(downloader.DownloadError, match="still live"):
        downloader.download("https://youtube.com/watch?v=x")


def test_friendly_bot_check_message(monkeypatch):
    err = Exception("ERROR: [youtube] x: Sign in to confirm you're not a bot.")
    monkeypatch.setitem(sys.modules, "yt_dlp", _fake_ytdlp(err))
    with pytest.raises(downloader.DownloadError, match="blocked the download"):
        downloader.download("https://youtube.com/watch?v=x")


def test_friendly_unavailable_message(monkeypatch):
    err = Exception("ERROR: [youtube] x: Video unavailable")
    monkeypatch.setitem(sys.modules, "yt_dlp", _fake_ytdlp(err))
    with pytest.raises(downloader.DownloadError, match="unavailable"):
        downloader.download("https://youtube.com/watch?v=x")
