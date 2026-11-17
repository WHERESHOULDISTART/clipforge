"""Browser publisher — posts through the platforms' own web uploaders using
Playwright, so no developer accounts, API audits or keys are needed.

How it works
------------
* A persistent Chromium profile lives in `settings.browser_profile_dir`, so you
  log in to each platform once and stay logged in.
* For a clip we open the platform's upload page, attach the video file, fill the
  caption/title where the page allows it, and copy the caption to the clipboard.
* **You press Post.** We deliberately stop one click short of publishing so you
  can review, pick a cover, tag people, etc. (Set `auto_submit=True` to try the
  final click on platforms where that is reliable.)

Selectors on these sites change often; every fill step is best-effort and the
file + caption are always available in the UI to drop in manually.
"""

from __future__ import annotations

import threading
import time
import traceback
import uuid
from pathlib import Path

from ..config import settings

UPLOAD_URLS = {
    "tiktok": "https://www.tiktok.com/tiktokstudio/upload",
    "youtube": "https://www.youtube.com/upload",
    "instagram": "https://www.instagram.com/",
    "facebook": "https://www.facebook.com/reels/create",
    "x": "https://x.com/compose/post",
}

LOGIN_TIMEOUT_S = 15 * 60  # time we give you to log in the first time

_sessions: dict[str, dict] = {}
_lock = threading.Lock()


def start(platform: str, video_path: Path, caption: str = "", title: str = "",
          auto_submit: bool = False) -> dict:
    """Launch the browser flow in a background thread. Returns the session dict."""
    sid = uuid.uuid4().hex[:8]
    state = {"id": sid, "platform": platform, "video": str(video_path), "status": "starting",
             "message": "Launching browser…", "started_at": time.time(), "error": None}
    with _lock:
        _sessions[sid] = state
    t = threading.Thread(target=_run, args=(state, platform, Path(video_path), caption, title, auto_submit),
                         daemon=True, name=f"publish-{sid}")
    t.start()
    return state


def status(sid: str) -> dict | None:
    return _sessions.get(sid)


def run_blocking(platform: str, video_path: Path, caption: str = "", title: str = "",
                 auto_submit: bool = False) -> dict:
    state = {"id": "cli", "platform": platform, "video": str(video_path), "status": "starting",
             "message": "", "started_at": time.time(), "error": None}
    _run(state, platform, Path(video_path), caption, title, auto_submit)
    return state


# ----------------------------------------------------------------------------

def _set(state: dict, status: str | None = None, message: str | None = None):
    if status:
        state["status"] = status
    if message is not None:
        state["message"] = message
        print(f"[publish:{state['platform']}] {message}")


def _run(state: dict, platform: str, video_path: Path, caption: str, title: str, auto_submit: bool):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        _set(state, "error", "Playwright not installed. Run: pip install playwright && playwright install chromium")
        state["error"] = state["message"]
        return

    url = UPLOAD_URLS.get(platform)
    if not url:
        _set(state, "error", f"Unknown platform {platform}")
        return
    if not video_path.exists():
        _set(state, "error", f"Video not found: {video_path}")
        return

    try:
        with sync_playwright() as p:
            profile = settings.browser_profile_dir.resolve()
            profile.mkdir(parents=True, exist_ok=True)
            launch_kwargs = dict(
                user_data_dir=str(profile),
                headless=False,
                viewport={"width": 1280, "height": 900},
                args=["--disable-blink-features=AutomationControlled"],
                permissions=["clipboard-read", "clipboard-write"],
            )
            if settings.browser_channel in ("chrome", "msedge"):
                launch_kwargs["channel"] = settings.browser_channel
            ctx = p.chromium.launch_persistent_context(**launch_kwargs)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()

            _set(state, "opening", f"Opening {platform} upload page")
            page.goto(url, wait_until="domcontentloaded")

            handler = HANDLERS[platform]
            _set(state, "waiting_login", "Waiting for the upload page (log in if asked)…")
            handler(page, video_path, caption, title, state, auto_submit)

            # Put the caption on the clipboard as a fallback for manual paste.
            try:
                page.evaluate("t => navigator.clipboard.writeText(t)", caption)
            except Exception:
                pass

            if state["status"] not in ("error",):
                _set(state, "ready", "Clip attached. Review in the browser window and press Post. "
                                      "Caption is on your clipboard.")
            # Keep the window open until the user closes the tab/browser.
            try:
                page.wait_for_event("close", timeout=0)
            except Exception:
                pass
            try:
                ctx.close()
            except Exception:
                pass
            if state["status"] == "ready":
                _set(state, "closed", "Browser closed.")
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        msg = str(exc)
        if "Executable doesn't exist" in msg or "playwright install" in msg:
            msg = ("Chromium for Playwright is not installed. Run:  playwright install chromium  "
                   "(or set CLIPFORGE_BROWSER_CHANNEL=chrome to use your installed Google Chrome).")
        elif "Missing X server" in msg or "cannot open display" in msg.lower():
            msg = "No display available — browser publishing needs a desktop session (not SSH/headless/Colab)."
        state["error"] = msg
        _set(state, "error", msg)


# ----------------------------------------------------------------------------
# Per-platform handlers (best effort; they never raise for a missing selector)
# ----------------------------------------------------------------------------

def _wait_file_input(page, state, timeout_s=LOGIN_TIMEOUT_S, selector="input[type=file]"):
    """Wait for a file input to appear; the user may need to log in first."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        loc = page.locator(selector)
        if loc.count() > 0:
            return loc.first
        time.sleep(1.0)
    raise TimeoutError("Upload page never showed a file picker (not logged in?)")


def _attach(page, state, video_path: Path, selector="input[type=file]"):
    inp = _wait_file_input(page, state, selector=selector)
    _set(state, "uploading", "Attaching video…")
    inp.set_input_files(str(video_path))


def _type_into(page, selector: str, text: str, timeout_ms=20000) -> bool:
    try:
        loc = page.locator(selector).first
        loc.wait_for(state="visible", timeout=timeout_ms)
        loc.click()
        page.keyboard.press("Control+A")
        page.keyboard.press("Backspace")
        page.keyboard.insert_text(text)
        return True
    except Exception:
        return False


def _tiktok(page, video_path, caption, title, state, auto_submit):
    _attach(page, state, video_path)
    _set(state, "filling", "Filling caption")
    # TikTok Studio uses a Draft.js editor for the caption.
    ok = _type_into(page, "div[contenteditable='true']", caption, timeout_ms=60000)
    if not ok:
        _set(state, message="Could not auto-fill caption; paste it from your clipboard.")
    if auto_submit:
        try:
            page.get_by_role("button", name="Post").click(timeout=120000)
            _set(state, "submitted", "Post clicked")
        except Exception:
            pass


def _youtube(page, video_path, caption, title, state, auto_submit):
    # youtube.com/upload redirects into Studio and opens the picker dialog.
    _attach(page, state, video_path)
    _set(state, "filling", "Filling title & description")
    desc = caption
    if not _type_into(page, "#title-textarea #textbox", title, timeout_ms=60000):
        _set(state, message="Could not auto-fill title; paste from clipboard.")
    _type_into(page, "#description-textarea #textbox", desc, timeout_ms=15000)
    # Leave the "Made for kids" radio + visibility steps to the user.


def _instagram(page, video_path, caption, title, state, auto_submit):
    # Click "Create" (the + icon in the left nav), which opens a dialog with a file input.
    deadline = time.time() + LOGIN_TIMEOUT_S
    while time.time() < deadline:
        try:
            btn = page.get_by_role("link", name="New post").or_(page.get_by_role("button", name="New post"))
            if btn.count() == 0:
                btn = page.locator("svg[aria-label='New post']").locator("xpath=ancestor::a | ancestor::div[@role='button']")
            if btn.count() > 0:
                btn.first.click()
                # Some layouts show a sub-menu with "Post"
                try:
                    page.get_by_role("link", name="Post").or_(page.get_by_text("Post", exact=True)).first.click(timeout=3000)
                except Exception:
                    pass
                break
        except Exception:
            pass
        time.sleep(1.0)
    _attach(page, state, video_path, selector="input[type=file][accept*='video'], input[type=file]")
    _set(state, message="Video attached. Click Next → Next, then paste the caption (it's on your clipboard).")


def _facebook(page, video_path, caption, title, state, auto_submit):
    _attach(page, state, video_path)
    _set(state, message="Video attached. Click Next, then paste the caption from your clipboard.")


def _x(page, video_path, caption, title, state, auto_submit):
    _set(state, "filling", "Typing post")
    _type_into(page, "div[data-testid='tweetTextarea_0']", caption, timeout_ms=LOGIN_TIMEOUT_S * 1000)
    _attach(page, state, video_path, selector="input[data-testid='fileInput']")
    if auto_submit:
        try:
            # Wait for media processing to finish before posting.
            page.locator("div[data-testid='tweetButton']").wait_for(state="visible", timeout=120000)
            time.sleep(5)
            page.locator("div[data-testid='tweetButton']").click()
            _set(state, "submitted", "Post clicked")
        except Exception:
            pass


HANDLERS = {
    "tiktok": _tiktok,
    "youtube": _youtube,
    "instagram": _instagram,
    "facebook": _facebook,
    "x": _x,
}
