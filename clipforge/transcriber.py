"""Step 2 — word-level transcription with faster-whisper.

Word timestamps are what make karaoke-style captions possible, so we always
request them. The transcript is cached next to the download as JSON.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np

from .config import settings
from .models import Segment, Transcript, Word

_model_cache: dict[tuple, object] = {}


def _preload_cuda_libs() -> None:
    """Make pip-installed NVIDIA libraries (nvidia-cublas-cu12, nvidia-cudnn-cu12)
    visible to CTranslate2 even when LD_LIBRARY_PATH was not set before Python
    started (Colab, Jupyter). Best effort, silent on failure."""
    import ctypes
    import glob
    import os

    try:
        import nvidia  # noqa: F401
    except ImportError:
        return
    roots = [os.path.dirname(p) for p in getattr(nvidia, "__path__", [])] or []
    libs = []
    for root in roots:
        for name in ("cublas", "cudnn"):
            libs += sorted(glob.glob(os.path.join(root, "nvidia", name, "lib", "*.so*")))
    # Load primary libs first (cublasLt before cublas; cudnn before its sub-libs).
    libs.sort(key=lambda x: (("cublasLt" not in x), ("cublas" not in x), len(os.path.basename(x))))
    for lib in libs:
        try:
            ctypes.CDLL(lib, mode=ctypes.RTLD_GLOBAL)
        except OSError:
            pass


def _resolve_device() -> tuple[str, str]:
    device = settings.whisper_device
    compute = settings.whisper_compute_type
    if device == "auto":
        try:
            import ctranslate2

            device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        except Exception:
            device = "cpu"
    if compute == "default":
        compute = "float16" if device == "cuda" else "int8"
    return device, compute


def _load_model(device: str, compute: str):
    key = (settings.whisper_model, device, compute)
    if key not in _model_cache:
        from faster_whisper import WhisperModel

        if device == "cuda":
            _preload_cuda_libs()
        _model_cache[key] = WhisperModel(settings.whisper_model, device=device, compute_type=compute)
    return _model_cache[key]


_CUDA_ERRORS = ("libcublas", "libcudnn", "cuda", "cudnn", "cublas", "CUDA")


def _run_whisper(audio: np.ndarray, device: str, compute: str, language: str | None, progress):
    model = _load_model(device, compute)
    segments_iter, info = model.transcribe(
        audio, word_timestamps=True, vad_filter=True, language=language, beam_size=5,
    )
    segments: list[Segment] = []
    total = float(info.duration or 0) or 1.0
    for seg in segments_iter:
        words = [
            Word(text=w.word.strip(), start=float(w.start), end=float(w.end), prob=float(w.probability))
            for w in (seg.words or [])
            if w.word.strip()
        ]
        segments.append(Segment(start=float(seg.start), end=float(seg.end), text=seg.text.strip(), words=words))
        if progress:
            progress(min(seg.end / total, 1.0), f"Transcribing {seg.end / total:.0%} ({device})")
    return segments, info


def load_audio(path: Path, sample_rate: int = 16000) -> np.ndarray:
    """Decode any media file to mono float32 PCM with ffmpeg.

    We deliberately do not let faster-whisper decode via PyAV: PyAV wheels differ
    between environments (Colab, conda, Apple Silicon) and break its decoder.
    ffmpeg is already a hard requirement, so we use it for everything.
    """
    cmd = ["ffmpeg", "-v", "error", "-nostdin", "-i", str(path), "-vn",
           "-f", "f32le", "-acodec", "pcm_f32le", "-ac", "1", "-ar", str(sample_rate), "-"]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg could not decode audio from {path.name}: {proc.stderr.decode(errors='ignore')[-500:]}")
    return np.frombuffer(proc.stdout, dtype=np.float32).copy()


def transcribe(video_path: Path, cache_path: Path | None = None, progress=None,
               language: str | None = None) -> Transcript:
    cache_path = cache_path or video_path.with_suffix(".transcript.json")
    if cache_path.exists():
        return Transcript.model_validate_json(cache_path.read_text())

    if progress:
        progress(0.0, "Decoding audio")
    audio = load_audio(video_path)
    if audio.size == 0:
        raise RuntimeError("This video has no audio track — nothing to transcribe.")

    device, compute = _resolve_device()
    try:
        segments, info = _run_whisper(audio, device, compute, language, progress)
    except (RuntimeError, OSError) as exc:
        if device == "cuda" and any(k in str(exc) for k in _CUDA_ERRORS):
            print(f"[transcriber] CUDA unavailable ({str(exc)[:120]}); falling back to CPU")
            if progress:
                progress(0.0, "GPU libraries missing — transcribing on CPU instead")
            segments, info = _run_whisper(audio, "cpu", "int8", language, progress)
        else:
            raise

    transcript = Transcript(language=info.language, duration=float(info.duration or 0), segments=segments)
    cache_path.write_text(transcript.model_dump_json(indent=1))
    return transcript


def transcript_to_srt(transcript: Transcript, start: float = 0.0, end: float | None = None) -> str:
    """Plain SRT for a time window (offset so the window starts at 0)."""

    def ts(t: float) -> str:
        t = max(t, 0)
        h, rem = divmod(t, 3600)
        m, s = divmod(rem, 60)
        return f"{int(h):02}:{int(m):02}:{int(s):02},{int((s % 1) * 1000):03}"

    lines = []
    n = 1
    for seg in transcript.segments:
        if seg.end < start or (end is not None and seg.start > end):
            continue
        lines.append(f"{n}\n{ts(seg.start - start)} --> {ts(seg.end - start)}\n{seg.text}\n")
        n += 1
    return "\n".join(lines)
