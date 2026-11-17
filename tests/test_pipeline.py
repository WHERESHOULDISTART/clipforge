"""Tests that run without network or a Whisper model, using the synthetic fixture."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(ROOT))
os.environ.setdefault("CLIPFORGE_LLM_PROVIDER", "none")
os.environ.setdefault("CLIPFORGE_WORK_DIR", str(ROOT / "workspace" / "test"))

from clipforge.captioner import CaptionStyle, build_ass, group_words, list_styles  # noqa: E402
from clipforge.highlighter import find_highlights  # noqa: E402
from clipforge.models import Transcript  # noqa: E402
from clipforge.packager import PLATFORMS, package  # noqa: E402
from clipforge.pipeline import new_job, run_job  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def fixture_files():
    if not (FIX / "sample.mp4").exists():
        subprocess.run([sys.executable, str(ROOT / "tests" / "make_fixture.py")], check=True)
    yield


@pytest.fixture(scope="session")
def transcript() -> Transcript:
    return Transcript.model_validate_json((FIX / "sample.transcript.json").read_text())


def test_styles_load():
    names = list_styles()
    assert {"hormozi", "mrbeast", "minimal", "neon", "boxed"} <= set(names)
    for n in names:
        s = CaptionStyle.load(n)
        assert (ROOT / "clipforge" / "fonts" / s.font_file).exists(), f"font missing for {n}"


def test_group_words_respects_limits(transcript):
    lines = group_words(transcript.words, per_line=3, max_seconds=2.0)
    assert lines
    for line in lines:
        assert 1 <= len(line) <= 3
        assert line[-1].end - line[0].start <= 2.0 + 0.5  # a single long word may exceed slightly


def test_build_ass_has_karaoke_events(transcript):
    style = CaptionStyle.load("hormozi")
    ass = build_ass(transcript.words, style, 0.0, 10.0, hook="TEST HOOK")
    assert "[Events]" in ass and "Dialogue:" in ass
    # One Dialogue per spoken word in the window + the hook
    n_words = sum(1 for w in transcript.words if w.end > 0 and w.start < 10.0)
    assert ass.count("Dialogue: 0,") >= n_words - 2
    assert "TEST HOOK" in ass
    assert "&H00" in ass  # colours converted to ASS format


def test_heuristic_highlights(transcript):
    hs = find_highlights(transcript, FIX / "sample.mp4", n=3, provider="none")
    assert 1 <= len(hs) <= 3
    for h in hs:
        assert 15 * 0.6 <= h.duration <= 60 + 1
        assert 0 <= h.start < h.end <= transcript.duration + 1
    # no heavy overlap
    for a in hs:
        for b in hs:
            if a is b:
                continue
            inter = max(0.0, min(a.end, b.end) - max(a.start, b.start))
            assert inter / min(a.duration, b.duration) <= 0.3


def test_full_pipeline_local_file():
    job = new_job(str(FIX / "sample.mp4"), style="boxed", clip_count=2)
    run_job(job)
    assert job.status == "done", job.error
    assert len(job.clips) == 2
    for c in job.clips:
        assert c.video_path.exists() and c.video_path.stat().st_size > 10_000
        assert c.srt_path and c.srt_path.exists()
        assert set(c.posts) == set(PLATFORMS)
        assert c.posts["x"].full_caption
        # output is vertical 1080x1920
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                              "stream=width,height", "-of", "json", str(c.video_path)],
                             capture_output=True, text=True, check=True).stdout
        s = json.loads(out)["streams"][0]
        assert (s["width"], s["height"]) == (1080, 1920)


def test_package_template_captions(transcript):
    from clipforge.models import Clip, Highlight, VideoInfo

    video = VideoInfo(id="x", title="How To Grow On YouTube Fast", url="https://youtu.be/x", duration=100,
                      channel="Tester", path=FIX / "sample.mp4")
    clip = Clip(index=1, highlight=Highlight(start=0, end=30, title="Biggest mistake", hook="THE BIGGEST MISTAKE",
                                             mood="insightful", score=80), video_path=FIX / "sample.mp4")
    package([clip], video, provider="none")
    assert len(clip.posts["x"].full_caption) <= 280
    assert "#shorts" in clip.posts["youtube"].full_caption
    assert "mindset" in clip.posts["tiktok"].hashtags
