# ✂️ ClipForge

**Paste a YouTube link → get the most intense / funny / insightful moments as vertical clips with trendy animated captions → post them to TikTok, YouTube Shorts, Instagram, Facebook and X from your own browser.**

No API keys required. No platform developer accounts. No audits. Runs on your machine.

```
YouTube URL ──► download ──► transcribe (word timestamps) ──► find highlights (LLM or heuristic)
            ──► cut + reframe 9:16 ──► karaoke captions ──► per-platform captions & hashtags
            ──► "Open in TikTok →"  (browser opens with clip attached, caption filled; you press Post)
```

## Features

- **Highlight detection** — an LLM (Claude / OpenAI / local Ollama) reads the timestamped transcript and picks hook-first, self-contained moments. With no key configured, a built-in heuristic scorer (energy words, questions, numbers, speech pace, audio loudness) still works offline.
- **Word-level animated captions** — five presets, rendered with libass so a 60 s clip burns in seconds on CPU:

  | style | look |
  |---|---|
  | `hormozi` | bold uppercase, yellow pop on the spoken word, thick outline |
  | `mrbeast` | chunky cartoon font, rainbow word colours, big bounce |
  | `neon` | tall condensed font, magenta glow, cyan spoken word |
  | `boxed` | comic font, spoken word in a solid red box |
  | `minimal` | white text in a dark pill, spoken word underlined, blurred background |

  Add your own: drop a JSON file in `clipforge/styles/`.
- **Hook overlay** — the first 3 s show a punchy title card (`"NOBODY TALKS ABOUT THIS"`).
- **9:16 reframing** — centre crop, blurred-background, or letterbox.
- **Per-platform copy** — title, caption and hashtags tuned for TikTok, Shorts, Reels, Facebook and X (LLM-written when available, templated otherwise).
- **Browser publishing** — a persistent Chromium profile logs in to each platform once; ClipForge then opens the upload page, attaches the clip, fills what it can and copies the caption to your clipboard. **You press Post.** No TikTok/YouTube/Meta API audits, no X credits.
- **Web UI + CLI** — `clipforge serve` for the dashboard, `clipforge make <url>` for scripts.

## Install

Requirements: Python 3.10+, [ffmpeg](https://ffmpeg.org/download.html) on your PATH.

```bash
git clone https://github.com/<you>/clipforge && cd clipforge
pip install -e .
playwright install chromium          # for browser publishing
cp .env.example .env                 # optional: add an API key, pick Whisper size
```

GPU users: install the CUDA build of CTranslate2 per the [faster-whisper docs](https://github.com/SYSTRAN/faster-whisper) and set `CLIPFORGE_WHISPER_DEVICE=cuda`. On CPU the default `small` model is a good speed/quality trade-off; use `tiny`/`base` for speed, `medium`/`large-v3` for accuracy.

## Use

### Web UI

```bash
clipforge serve           # opens http://127.0.0.1:8420
```

Paste a link, pick a style, hit **Make clips**. Each finished clip shows a preview, an editable caption per platform, **Download MP4**, and **Open in TikTok →** (or any other platform).

### CLI

```bash
clipforge make "https://www.youtube.com/watch?v=..." --style neon --clips 5
clipforge make ./podcast.mp4 --style minimal --reframe blur     # local files work too
clipforge publish <job-id> 1 tiktok                              # open the uploader for clip 1
clipforge styles
clipforge jobs
```

## How browser publishing works

1. First time per platform, the Chromium window asks you to log in. The session is saved in `browser_profile/` (git-ignored) so you only do this once. Set `CLIPFORGE_BROWSER_CHANNEL=chrome` to use your installed Google Chrome instead of Playwright's Chromium.
2. ClipForge navigates to the upload page, waits for the file picker, attaches the clip and fills the caption/title where the page allows it (TikTok caption, YouTube title + description, X post text). Instagram and Facebook need a couple of **Next** clicks before the caption field appears, so the caption is on your clipboard — just paste.
3. Review, pick a cover, then **press Post yourself**. ClipForge stays one click short of publishing on purpose. (`clipforge publish ... --auto-submit` tries the final click on X and TikTok if you really want that.)

Platform pages change their markup from time to time; every fill step is best-effort and the UI always has the file + caption ready for manual drop-in. PRs updating selectors in `clipforge/publisher/browser.py` are welcome.

## Configuration

Everything is an environment variable or a line in `.env` — see [`.env.example`](.env.example). The important ones:

| variable | default | meaning |
|---|---|---|
| `CLIPFORGE_LLM_PROVIDER` | `auto` | `anthropic`, `openai`, `ollama`, or `none` (heuristic only) |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | — | picked up automatically with `auto` |
| `CLIPFORGE_WHISPER_MODEL` | `small` | faster-whisper model size |
| `CLIPFORGE_MIN_CLIP_SECONDS` / `MAX` | `15` / `60` | clip length range |
| `CLIPFORGE_DEFAULT_STYLE` | `hormozi` | caption preset |

## Project layout

```
clipforge/
  downloader.py    yt-dlp (or local file)
  transcriber.py   faster-whisper, word timestamps, cached JSON
  highlighter.py   LLM prompt + heuristic scorer, snapping & de-dupe
  captioner.py     caption styles → ASS karaoke events
  cutter.py        ffmpeg cut, 9:16 reframe, burn-in, thumbnail
  packager.py      per-platform titles / captions / hashtags
  pipeline.py      job orchestration + JSON job state
  publisher/browser.py   Playwright uploaders for 5 platforms
  web/             FastAPI + vanilla JS dashboard
  styles/*.json    caption presets      fonts/   bundled OFL fonts
  cli.py           typer CLI
tests/             synthetic fixture (no network / model needed) + pytest
```

## Roadmap

- [ ] Face-tracking reframe (MediaPipe) instead of centre crop
- [ ] Emoji / keyword icons in captions
- [ ] B-roll & zoom-punch on emphasis words
- [ ] Scheduling queue + post history
- [ ] Optional API publishers for people who have audited apps
- [ ] Docker image

## Contributing

`python tests/make_fixture.py && pytest` runs the whole pipeline on a synthetic video in ~30 s with no model download. Caption styles and platform selectors are the easiest places to contribute.

## Legal

Only clip videos you have the rights to (your own, or with permission). Respect each platform's terms of service. Fonts are bundled under the SIL Open Font License / Apache 2.0 (see `clipforge/fonts/`).

MIT © ClipForge contributors
