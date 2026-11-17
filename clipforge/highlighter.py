"""Step 3 — find the moments worth clipping.

Two engines:

* **LLM** (Anthropic / OpenAI / Ollama): reads the timestamped transcript and
  returns the most hook-worthy, funny, intense or insightful windows.
* **Heuristic** (no key needed): scores sentences by energy words, questions,
  numbers, exclamation, speech density and audio loudness, then picks peaks.

Both return a list of `Highlight`, snapped to sentence boundaries and clamped
to the configured clip length range.
"""

from __future__ import annotations

import json
import math
import re
import subprocess
from pathlib import Path

from .config import settings
from .models import Highlight, Transcript, Word

PROMPT = """You are a world-class short-form video editor (TikTok, Reels, Shorts).
Below is a transcript of a video with timestamps in seconds.

Pick the {n} best self-contained moments to turn into vertical clips of
{min_s:.0f}-{max_s:.0f} seconds each. Prioritise:
- a strong hook in the first 3 seconds (bold claim, question, conflict, surprise)
- funny, intense, emotional or highly insightful moments
- complete thoughts: start at the beginning of a sentence, end at the end of one
- no overlap between clips

Return ONLY a JSON array, no prose. Each item:
{{"start": <sec>, "end": <sec>, "title": "<punchy 5-8 word title>",
  "hook": "<first line text overlay, max 8 words>",
  "reason": "<why this will perform>", "score": <0-100>,
  "mood": "funny|intense|insightful|emotional|general"}}

TRANSCRIPT:
{transcript}
"""

ENERGY_WORDS = {
    "insane", "crazy", "unbelievable", "never", "secret", "truth", "biggest", "worst", "best",
    "mistake", "shocking", "literally", "actually", "nobody", "everyone", "million", "billion",
    "hate", "love", "die", "kill", "win", "lose", "money", "rich", "broke", "fail", "failed",
    "why", "how", "what", "stop", "wait", "listen", "honestly", "wrong", "right", "proof",
    "game", "changer", "hack", "trick", "warning", "danger", "finally", "first", "last",
}


# ----------------------------------------------------------------------------
# Public entry point
# ----------------------------------------------------------------------------

def find_highlights(transcript: Transcript, video_path: Path | None = None, n: int | None = None,
                    provider: str | None = None, progress=None) -> list[Highlight]:
    n = n or settings.default_clip_count
    provider = (provider or settings.llm_provider).lower()
    if provider == "auto":
        provider = _detect_provider()

    highlights: list[Highlight] = []
    if provider != "none":
        try:
            if progress:
                progress(0.1, f"Asking {provider} for the best moments")
            highlights = _llm_highlights(transcript, n, provider)
        except Exception as exc:  # fall back rather than fail the whole job
            print(f"[highlighter] LLM provider '{provider}' failed ({exc}); using heuristic")

    if not highlights:
        if progress:
            progress(0.3, "Scoring transcript heuristically")
        highlights = _heuristic_highlights(transcript, video_path, n)

    highlights = [_snap(h, transcript) for h in highlights]
    highlights = _dedupe(highlights)
    highlights.sort(key=lambda h: -h.score)
    return highlights[:n]


# ----------------------------------------------------------------------------
# LLM engine
# ----------------------------------------------------------------------------

def _detect_provider() -> str:
    import os

    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    try:
        import httpx

        httpx.get(f"{settings.ollama_host}/api/tags", timeout=1.5).raise_for_status()
        return "ollama"
    except Exception:
        return "none"


def _format_transcript(transcript: Transcript, max_chars: int = 60_000) -> str:
    lines = [f"[{s.start:.1f}-{s.end:.1f}] {s.text}" for s in transcript.segments]
    text = "\n".join(lines)
    if len(text) > max_chars:  # keep it inside any model's context; sample evenly
        step = math.ceil(len(lines) / (max_chars // 80))
        text = "\n".join(lines[::step])
    return text


def _llm_highlights(transcript: Transcript, n: int, provider: str) -> list[Highlight]:
    prompt = PROMPT.format(n=n, min_s=settings.min_clip_seconds, max_s=settings.max_clip_seconds,
                           transcript=_format_transcript(transcript))
    raw = _complete(prompt, provider)
    data = _extract_json(raw)
    out = []
    for item in data:
        try:
            out.append(Highlight(
                start=float(item["start"]), end=float(item["end"]),
                title=str(item.get("title", "Clip")).strip(),
                hook=str(item.get("hook", "")).strip(),
                reason=str(item.get("reason", "")).strip(),
                score=float(item.get("score", 50)),
                mood=str(item.get("mood", "general")).lower(),
            ))
        except (KeyError, ValueError, TypeError):
            continue
    return out


def _complete(prompt: str, provider: str) -> str:
    if provider == "anthropic":
        import anthropic

        client = anthropic.Anthropic()
        msg = client.messages.create(
            model=settings.llm_model or "claude-sonnet-4-5",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(getattr(b, "text", "") for b in msg.content)

    if provider == "openai":
        from openai import OpenAI

        client = OpenAI()
        resp = client.chat.completions.create(
            model=settings.llm_model or "gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
        )
        return resp.choices[0].message.content or ""

    if provider == "ollama":
        import httpx

        resp = httpx.post(
            f"{settings.ollama_host}/api/generate",
            json={"model": settings.llm_model or "llama3.1", "prompt": prompt, "stream": False,
                  "format": "json"},
            timeout=300,
        )
        resp.raise_for_status()
        return resp.json().get("response", "")

    raise ValueError(f"unknown provider {provider}")


def _extract_json(text: str) -> list[dict]:
    text = text.strip()
    m = re.search(r"\[.*\]", text, re.S)
    if m:
        text = m.group(0)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):  # some models wrap it: {"clips": [...]}
        for v in data.values():
            if isinstance(v, list):
                return v
        return []
    return data if isinstance(data, list) else []


# ----------------------------------------------------------------------------
# Heuristic engine
# ----------------------------------------------------------------------------

def _sentences(transcript: Transcript) -> list[tuple[float, float, str, list[Word]]]:
    """Split the word stream into sentences on terminal punctuation / long pauses."""
    sents, cur = [], []
    for w in transcript.words:
        if cur and (w.start - cur[-1].end > 1.2):
            sents.append(cur)
            cur = []
        cur.append(w)
        if re.search(r"[.!?]$", w.text):
            sents.append(cur)
            cur = []
    if cur:
        sents.append(cur)
    return [(s[0].start, s[-1].end, " ".join(x.text for x in s), s) for s in sents if s]


def _loudness_profile(video_path: Path, duration: float, step: float = 1.0) -> list[float]:
    """Per-second RMS loudness (0..1) using ffmpeg's astats; empty list on failure."""
    try:
        cmd = ["ffmpeg", "-v", "error", "-i", str(video_path), "-vn", "-af",
               f"astats=metadata=1:reset={int(step * 50)},ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-",
               "-f", "null", "-"]
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=600).stdout
        vals = [float(m) for m in re.findall(r"RMS_level=(-?[\d.]+)", out)]
        if not vals:
            return []
        lo, hi = min(vals), max(vals)
        return [(v - lo) / (hi - lo + 1e-9) for v in vals]
    except Exception:
        return []


def _heuristic_highlights(transcript: Transcript, video_path: Path | None, n: int) -> list[Highlight]:
    sents = _sentences(transcript)
    if not sents:
        return []
    loud = _loudness_profile(video_path, transcript.duration) if video_path else []

    scored = []
    for start, end, text, words in sents:
        toks = re.findall(r"[a-zA-Z']+", text.lower())
        if not toks:
            continue
        dur = max(end - start, 0.1)
        energy = sum(t in ENERGY_WORDS for t in toks) / math.sqrt(len(toks))
        punct = text.count("!") * 1.5 + text.count("?") * 1.0
        numbers = len(re.findall(r"\d", text)) * 0.3
        density = min(len(toks) / dur / 3.0, 1.5)  # fast talking = excitement
        loudness = 0.0
        if loud:
            i0, i1 = int(start), max(int(end), int(start) + 1)
            window = loud[i0:i1] or [0.0]
            loudness = sum(window) / len(window) * 2.0
        scored.append((energy * 2 + punct + numbers + density + loudness, start, end, text))

    # Slide a window over sentences to build candidate clips around each peak
    target = (settings.min_clip_seconds + settings.max_clip_seconds) / 2
    cands: list[Highlight] = []
    for i, (score, s_start, s_end, s_text) in enumerate(scored):
        a, b = i, i
        total = score
        while (scored[b][2] - scored[a][1]) < target:
            grow_left = a > 0 and (b == len(scored) - 1 or scored[a - 1][0] >= scored[b + 1][0])
            if grow_left:
                a -= 1
                total += scored[a][0]
            elif b < len(scored) - 1:
                b += 1
                total += scored[b][0]
            else:
                break
        start, end = scored[a][1], scored[b][2]
        if end - start < settings.min_clip_seconds * 0.6:
            continue
        hook_text = s_text
        mood = "intense" if ("!" in hook_text or loudness_rank(score, scored)) else "general"
        cands.append(Highlight(
            start=start, end=end,
            title=_title_from(hook_text),
            hook=_hook_from(hook_text),
            reason="High-energy passage (heuristic scorer)",
            score=min(100.0, 40 + total * 6),
            mood=mood,
        ))
    cands = _dedupe(sorted(cands, key=lambda h: -h.score))[: n * 2]
    # Rank-normalise raw scores into a 55-95 "virality" range for display.
    for rank, h in enumerate(cands):
        h.score = round(95 - (40 * rank / max(len(cands) - 1, 1)), 1)
    return cands


def loudness_rank(score: float, scored: list) -> bool:
    if not scored:
        return False
    top = sorted(s[0] for s in scored)[int(len(scored) * 0.85)]
    return score >= top


def _title_from(text: str) -> str:
    words = re.findall(r"[\w']+", text)[:7]
    return " ".join(words).capitalize() or "Clip"


def _hook_from(text: str) -> str:
    words = re.findall(r"[\w']+", text)[:8]
    return " ".join(words).upper()


# ----------------------------------------------------------------------------
# Shared post-processing
# ----------------------------------------------------------------------------

def _snap(h: Highlight, transcript: Transcript) -> Highlight:
    """Snap to the nearest word boundaries and clamp duration."""
    words = transcript.words
    if not words:
        return h
    start = min((w.start for w in words), key=lambda t: abs(t - h.start))
    end = min((w.end for w in words), key=lambda t: abs(t - h.end))
    if end - start > settings.max_clip_seconds:
        end = max((w.end for w in words if w.end <= start + settings.max_clip_seconds), default=end)
    if end - start < settings.min_clip_seconds:
        end = min((w.end for w in words if w.end >= start + settings.min_clip_seconds), default=end)
    end = min(end, transcript.duration or end)
    return h.model_copy(update={"start": max(0.0, start - 0.15), "end": end + 0.25})


def _dedupe(hs: list[Highlight], max_overlap: float = 0.3) -> list[Highlight]:
    kept: list[Highlight] = []
    for h in sorted(hs, key=lambda x: -x.score):
        ok = True
        for k in kept:
            inter = max(0.0, min(h.end, k.end) - max(h.start, k.start))
            if inter / max(min(h.duration, k.duration), 0.1) > max_overlap:
                ok = False
                break
        if ok:
            kept.append(h)
    return kept
