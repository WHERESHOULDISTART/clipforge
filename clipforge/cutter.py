"""Step 4 + 6 — cut a highlight out of the source, reframe to 9:16, burn captions,
and grab a thumbnail. One ffmpeg pass per clip."""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from .captioner import FONTS_DIR, CaptionStyle, build_ass
from .config import settings
from .models import Clip, Highlight, Transcript
from .transcriber import transcript_to_srt


def _reframe_filter(mode: str, w: int, h: int) -> str:
    if mode == "blur":
        # Blurred, zoomed copy of the source as background; sharp source fitted on top.
        return (
            f"split[bg][fg];"
            f"[bg]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},boxblur=30:8,eq=brightness=-0.08[bgb];"
            f"[fg]scale={w}:{h}:force_original_aspect_ratio=decrease[fgs];"
            f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2"
        )
    if mode == "fit":
        return f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black"
    # default: centre crop to 9:16
    return f"crop='min(iw,ih*{w}/{h})':'min(ih,iw*{h}/{w})',scale={w}:{h}"


def _ass_path_for_filter(p: Path) -> str:
    # ffmpeg filter args need ':' and '\' escaped, and the whole thing quoted.
    s = str(p.resolve()).replace("\\", "/").replace(":", "\\:")
    return s


def render_clip(source: Path, highlight: Highlight, transcript: Transcript, style: CaptionStyle,
                out_dir: Path, index: int, reframe: str | None = None, with_hook: bool = True,
                progress=None) -> Clip:
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"clip_{index:02d}"
    video_out = out_dir / f"{stem}.mp4"
    ass_out = out_dir / f"{stem}.ass"
    srt_out = out_dir / f"{stem}.srt"
    thumb_out = out_dir / f"{stem}.jpg"

    w, h = settings.output_width, settings.output_height
    ass_out.write_text(build_ass(transcript.words, style, highlight.start, highlight.end, w, h,
                                 hook=highlight.hook if with_hook else None), encoding="utf-8")
    srt_out.write_text(transcript_to_srt(transcript, highlight.start, highlight.end), encoding="utf-8")

    vf = (
        f"{_reframe_filter(reframe or style.reframe, w, h)},"
        f"ass='{_ass_path_for_filter(ass_out)}':fontsdir='{_ass_path_for_filter(FONTS_DIR)}',"
        f"format=yuv420p"
    )
    duration = highlight.end - highlight.start
    cmd = [
        "ffmpeg", "-y", "-v", "error", "-stats",
        "-ss", f"{highlight.start:.3f}", "-i", str(source), "-t", f"{duration:.3f}",
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", "30",
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
        "-movflags", "+faststart",
        str(video_out),
    ]
    if progress:
        progress(0.0, f"Rendering clip {index}")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed for clip {index}:\n{' '.join(shlex.quote(c) for c in cmd)}\n{proc.stderr[-2000:]}")

    # Thumbnail ~1s in (after the hook pop), from the finished clip so captions are on it.
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-ss", f"{min(1.0, duration / 2):.2f}", "-i", str(video_out),
         "-frames:v", "1", "-q:v", "3", str(thumb_out)],
        capture_output=True, text=True,
    )

    return Clip(index=index, highlight=highlight, video_path=video_out,
                thumbnail_path=thumb_out if thumb_out.exists() else None, srt_path=srt_out)
