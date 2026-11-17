# ✂️ ClipForge

**Paste a YouTube link → get the most intense / funny / insightful moments as vertical clips with trendy animated captions → post them to TikTok, YouTube Shorts, Instagram, Facebook and X from your own browser.**

No API keys required. No platform developer accounts. No audits. Runs on your machine — or free in your browser.

## 🚀 Try it free right now (no install)

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/WHERESHOULDISTART/clipforge/blob/main/notebooks/ClipForge_Colab.ipynb)

**→ [Open ClipForge in Google Colab](https://colab.research.google.com/github/WHERESHOULDISTART/clipforge/blob/main/notebooks/ClipForge_Colab.ipynb)** — paste a YouTube link, pick a caption style, press run. Google's free GPU does the transcription and rendering; you download the finished clips as a zip. Works on any computer, phone browser included.

Want the full dashboard with one-click **Open in TikTok →** publishing? [Install it on your computer](#install) (free too — it's all open source, MIT).

```
YouTube URL ──► download ──► transcribe (word timestamps) ──► find highlights (LLM or heuristic)
            ──► cut + reframe 9:16 ──► karaoke captions ──► per-platform captions & hashtags
            ──► "Open in TikTok →"  (browser opens with clip attached, caption filled; you press Post)
```

**Contents:** [How to use it](#how-to-use) · [How I built it](#how-i-built-it) · [Features](#features) · [Configuration](#configuration) · [Troubleshooting](#troubleshooting)

---

<a id="how-to-use"></a>
## 📖 How to use it — step by step

There are two ways. **Option A** needs nothing installed and is the quickest way to see what ClipForge does. **Option B** runs on your own computer and adds the dashboard plus one-click posting to TikTok, YouTube, Instagram, Facebook and X.

### Option A — Free in your browser (Google Colab)

1. **Open the notebook.** Click the **Open in Colab** badge above. Sign in with any Google account.
2. **Turn on the free GPU** (makes it ~10× faster). Menu **Runtime → Change runtime type → T4 GPU → Save**. Usually it's already selected.
3. **Paste your link.** In step **2️⃣ Settings**, paste a YouTube link into `youtube_url`. Pick a video where **people are talking** — a podcast, interview, vlog, stream or lecture. Pure music videos can't be captioned.
4. **Choose your look** (optional). Pick a `caption_style` (hormozi, mrbeast, neon, boxed, minimal), how many clips you want, and the framing.
5. **Run it.** Menu **Runtime → Run all**. Colab shows a warning that the notebook wasn't written by Google — that's normal for any notebook from GitHub; click **Run anyway**.
6. **Wait ~2–5 minutes.** Step 1️⃣ installs ClipForge, step 3️⃣ prints progress: downloading → transcribing → finding the best moments → rendering.
7. **Watch your clips** in step 4️⃣. Each one shows the video and a ready-made caption with hashtags.
8. **Download.** Step 5️⃣ downloads a zip with every MP4, subtitle files, and `captions.md` with a caption for each platform.
9. **Post.** Open TikTok / YouTube / Instagram / Facebook / X, upload the MP4 and paste the matching caption from `captions.md`.

> Optional: paste an Anthropic or OpenAI API key in step 2️⃣ and an AI picks the moments and writes the captions instead of the built-in scorer.

<a id="install"></a>
### Option B — Install on your computer (full version)

**1. Install the three tools ClipForge needs** (Python, ffmpeg, git). One time only.

| Your computer | Open this app | Run this |
|---|---|---|
| **Mac** | Terminal | Install [Homebrew](https://brew.sh) first, then: `brew install python ffmpeg git` |
| **Windows** | PowerShell | `winget install Python.Python.3.12 Gyan.FFmpeg Git.Git` — then close and reopen PowerShell |
| **Linux** (Ubuntu/Debian) | Terminal | `sudo apt install python3 python3-venv ffmpeg git` |

**2. Download ClipForge and set it up.** One time only.

Mac / Linux:
```bash
git clone https://github.com/WHERESHOULDISTART/clipforge
cd clipforge
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
playwright install chromium
```

Windows (PowerShell):
```powershell
git clone https://github.com/WHERESHOULDISTART/clipforge
cd clipforge
py -m venv .venv
.venv\Scripts\activate
pip install -e .
playwright install chromium
```

**3. (Optional) Add an AI key** for smarter moment-picking and captions. Copy `.env.example` to `.env` and put your `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` in it. Without a key ClipForge still works using its built-in scorer.

**4. Start ClipForge.**
```bash
clipforge serve
```
Your browser opens **http://127.0.0.1:8420**. Keep the Terminal window open while you use it.

**5. Make clips.** Paste a YouTube link (or the path of a video file on your computer), choose a caption style, the number of clips and the framing, then click **Make clips ⚡**. A progress bar shows each stage. The first run downloads the speech-recognition model (a few hundred MB), so it takes longer.

**6. Review each clip.** Every clip card shows a preview, a 🔥 score, and a caption box with tabs for **TikTok · YouTube Shorts · Instagram Reels · Facebook Reels · X**. Edit the caption if you like. **Download MP4** saves the file.

**7. Post it.** Pick a platform tab and click **Open in TikTok →** (the button follows the tab):
   1. A separate browser window opens on that platform's upload page.
   2. **The first time only**, log in to your account there. ClipForge remembers it, so next time you go straight to the upload page.
   3. ClipForge attaches the clip and fills in the caption (on Instagram and Facebook, click **Next** and paste — the caption is already on your clipboard).
   4. Check everything, pick a cover if you want, and **press Post yourself**. ClipForge never posts without you.

**8. Next time** you only need:
```bash
cd clipforge
source .venv/bin/activate      # Windows: .venv\Scripts\activate
clipforge serve
```
To get the newest version: `git pull` then `pip install -e .`

### Prefer the command line?

```bash
clipforge make "https://www.youtube.com/watch?v=..." --style neon --clips 5
clipforge make ./podcast.mp4 --style minimal --reframe blur     # local files work too
clipforge publish <job-id> 1 tiktok                              # open the uploader for clip 1
clipforge styles                                                 # list caption styles
clipforge jobs                                                   # list past jobs
```

---

<a id="how-i-built-it"></a>
## 🛠️ How I built it — step by step

I'm [@WHERESHOULDISTART](https://github.com/WHERESHOULDISTART). I built ClipForge in two days (16–17 November 2026) together with **Claude**, Anthropic's AI assistant: I described what I wanted and made the decisions, Claude wrote and tested the code. Here's exactly how it went.

**Step 1 — The idea.** I wanted a free, open-source version of the paid "AI clipping" tools: paste a YouTube link, get the best moments as vertical clips with trendy captions. I asked Claude to help me build it and publish it on GitHub.

**Step 2 — Planning the pipeline.** We broke it into stages: download (yt-dlp) → transcribe with word-level timestamps (faster-whisper) → find the highlights (an AI model, or a built-in scorer when there's no key) → cut and reframe to 9:16 (ffmpeg) → burn in word-by-word animated captions. I chose Python because all of those tools are Python-friendly.

**Step 3 — Adding social media posting.** I wanted to post straight to TikTok, YouTube, Instagram, Facebook and X. We looked into the official APIs and hit walls: TikTok and YouTube keep posts **private** until your app passes an audit, Instagram's API only works for Business/Creator accounts after Meta's app review, and X's API is pay-per-use. So I decided ClipForge would **post through the browser instead** — it opens each site's normal upload page with the clip attached and the caption filled in, and I press Post. No keys, no audits, works on day one.

**Step 4 — Making it a browser app.** I asked for it to run in the browser, so Claude built a small web dashboard: paste a link, watch the progress, preview clips, edit captions and click **Open in TikTok →**. There's also a command-line version.

**Step 5 — Building version 0.1.** Claude wrote the whole thing: the downloader, transcriber, highlight finder, five caption styles (Hormozi, MrBeast, Neon, Boxed, Minimal) with free fonts, the clip renderer, per-platform captions and hashtags, the dashboard, and the browser publisher. Everything was tested on a generated test video, and the automated tests passed.

**Step 6 — Publishing on GitHub.** I created this public repository, `clipforge`, under my account. Then I **connected Claude to my GitHub account**: in GitHub **Settings → Applications → Claude → Configure**, I confirmed my password and added `clipforge` to the repositories Claude is allowed to access. After that Claude could push the code straight here, and every fix since then has landed as a normal commit.

**Step 7 — Making it free for everyone.** Not everyone wants to install Python, so I added a **Google Colab notebook** and the **Open in Colab** badge at the top of this page. Anyone can run ClipForge on Google's free GPU from any browser — even a phone.

**Step 8 — Testing it on a real YouTube video.** I ran the Colab notebook on a real talk. The first runs failed, and each failure turned into a fix:
1. Transcription crashed because of an audio-library mismatch on Colab → audio is now decoded with ffmpeg.
2. The GPU libraries weren't found → they're now loaded automatically, with a CPU fallback.
3. A music video gave "no speech detected" → it now retries, and the notebook asks for a video with people talking.
4. The highlight finder measured loudness at the wrong moments and was slow → fixed; it's now correct and takes seconds.
5. The captions were half the size this style should be → all five styles are bigger, and long titles wrap onto two lines.
6. Rendering used only the CPU → it now uses the GPU when there is one.

After those fixes a full run on a real video — download, transcription on the GPU, three captioned clips and captions for every platform — took about **one minute**.

**Step 9 — Writing this guide**, so anyone can use it, step by step.

**What I learned:** test on real videos early (my generated test video hid most of these bugs), check what platform APIs actually allow before building on them, and a free Colab notebook is the easiest way to let anyone try a project without installing anything.

---

## Features

- **Highlight detection** — an LLM (Claude / OpenAI / local Ollama) reads the timestamped transcript and picks hook-first, self-contained moments. With no key configured, a built-in heuristic scorer (energy words, questions, numbers, speech pace, audio loudness) still works offline.
- **Word-level animated captions** — five presets, rendered with libass so a 60 s clip burns in seconds:

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
- **GPU when available** — Whisper on CUDA and NVENC video encoding, with automatic CPU fallback.
- **Web UI + CLI + Colab** — `clipforge serve` for the dashboard, `clipforge make <url>` for scripts, the notebook for zero-install use.

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
| `CLIPFORGE_WHISPER_MODEL` | `small` | faster-whisper model size: `tiny`/`base` faster, `medium`/`large-v3` more accurate |
| `CLIPFORGE_WHISPER_DEVICE` | `auto` | `auto`, `cpu` or `cuda` |
| `CLIPFORGE_MIN_CLIP_SECONDS` / `MAX` | `15` / `60` | clip length range |
| `CLIPFORGE_DEFAULT_STYLE` | `hormozi` | caption preset |
| `CLIPFORGE_BROWSER_CHANNEL` | `chromium` | `chrome` / `msedge` to post from your installed browser |

## Troubleshooting

| Problem | Fix |
|---|---|
| **"No speech detected"** | The video needs people talking. Music-only or silent videos can't be captioned. |
| **"Chromium for Playwright is not installed"** | Run `playwright install chromium` (with the `.venv` active). |
| **`clipforge: command not found`** | Activate the environment first: `source .venv/bin/activate` (Windows: `.venv\Scripts\activate`). |
| **YouTube download fails** | YouTube changes often — update the downloader: `pip install -U yt-dlp`. |
| **Very slow on my laptop** | Set `CLIPFORGE_WHISPER_MODEL=base` in `.env`, or use the free Colab GPU (Option A). |
| **Caption not filled on a platform** | The site changed its page. Paste the caption — it's already on your clipboard — and please open an issue. |

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
notebooks/         free Google Colab version
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
