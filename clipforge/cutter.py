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


_NVENC: bool | None = None


def _nvenc_available() -> bool:
    """True if this ffmpeg has h264_nvenc AND it can actually open a GPU encoder."""
    global _NVENC
    if _NVENC is None:
        try:
            enc = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
            if "h264_nvenc" not in enc:
                _NVENC = False
            else:
                probe = subprocess.run(
                    ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=black:s=256x256:d=0.2",
                     "-c:v", "h264_nvenc", "-f", "null", "-"], capture_output=True, text=True, timeout=30)
                _NVENC = probe.returncode == 0
        except Exception:
            _NVENC = False
    return _NVENC


def _video_codec_args(gpu: bool) -> list[str]:
    if gpu:
        return ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "21", "-b:v", "0"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]


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
    def build_cmd(gpu: bool) -> list[str]:
        return [
            "ffmpeg", "-y", "-v", "error", "-nostats", "-progress", "pipe:1",
            "-ss", f"{highlight.start:.3f}", "-i", str(source), "-t", f"{duration:.3f}",
            "-vf", vf,
            *_video_codec_args(gpu), "-r", "30",
            "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
            "-movflags", "+faststart",
            str(video_out),
        ]

    def run(cmd: list[str]) -> tuple[int, str]:
        """Run ffmpeg, reporting % done for this clip from its -progress output."""
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        import threading

        err: list[str] = []
        t = threading.Thread(target=lambda: err.append(proc.stderr.read()), daemon=True)
        t.start()
        for line in proc.stdout:
            if progress and line.startswith("out_time_us="):
                try:
                    done = int(line.split("=", 1)[1]) / 1e6
                except ValueError:
                    continue
                if duration > 0:
                    progress(min(done / duration, 1.0), f"Rendering clip {index}: {min(done / duration, 1.0):.0%}")
        proc.wait()
        t.join(timeout=5)
        return proc.returncode, "".join(err)

    if progress:
        progress(0.0, f"Rendering clip {index}")
    use_gpu = _nvenc_available()
    cmd = build_cmd(use_gpu)
    code, stderr = run(cmd)
    if code != 0 and use_gpu:  # GPU encoder hiccup -> CPU
        cmd = build_cmd(False)
        code, stderr = run(cmd)
    if code != 0:
        raise RuntimeError(f"ffmpeg failed for clip {index}:\n{' '.join(shlex.quote(c) for c in cmd)}\n{stderr[-2000:]}")

    # Thumbnail ~1s in (after the hook pop), from the finished clip so captions are on it.
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-ss", f"{min(1.0, duration / 2):.2f}", "-i", str(video_out),
         "-frames:v", "1", "-q:v", "3", str(thumb_out)],
        capture_output=True, text=True,
    )

    return Clip(index=index, highlight=highlight, video_path=video_out,
                thumbnail_path=thumb_out if thumb_out.exists() else None, srt_path=srt_out)
