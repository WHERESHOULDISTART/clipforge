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


def _load_model():
    key = (settings.whisper_model, settings.whisper_device, settings.whisper_compute_type)
    if key not in _model_cache:
        from faster_whisper import WhisperModel

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
        _model_cache[key] = WhisperModel(settings.whisper_model, device=device, compute_type=compute)
    return _model_cache[key]


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

    model = _load_model()
    segments_iter, info = model.transcribe(
        audio,
        word_timestamps=True,
        vad_filter=True,
        language=language,
        beam_size=5,
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
            progress(min(seg.end / total, 1.0), f"Transcribing {seg.end / total:.0%}")

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
