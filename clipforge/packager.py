"""Step 7 — per-platform titles, captions and hashtags for each clip.

Uses the LLM when one is configured; otherwise builds sensible defaults from the
highlight title/hook and mood so the tool works with zero keys.
"""

from __future__ import annotations

import json
import re

from .highlighter import _complete, _detect_provider, _extract_json
from .config import settings
from .models import Clip, PlatformPost, VideoInfo

PLATFORMS = {
    "tiktok": {"name": "TikTok", "caption_max": 2200, "tags": 5},
    "youtube": {"name": "YouTube Shorts", "caption_max": 5000, "tags": 4},
    "instagram": {"name": "Instagram Reels", "caption_max": 2200, "tags": 8},
    "facebook": {"name": "Facebook Reels", "caption_max": 2200, "tags": 3},
    "x": {"name": "X", "caption_max": 280, "tags": 2},
}

MOOD_TAGS = {
    "funny": ["funny", "comedy", "lol", "humor"],
    "intense": ["intense", "mindblown", "wow", "crazy"],
    "insightful": ["mindset", "learn", "facts", "knowledge"],
    "emotional": ["emotional", "storytime", "real", "deep"],
    "general": ["viral", "fyp", "trending", "clips"],
}
BASE_TAGS = {
    "tiktok": ["fyp", "foryou", "viral"],
    "youtube": ["shorts", "viral"],
    "instagram": ["reels", "explore", "viral", "trending"],
    "facebook": ["reels"],
    "x": [],
}

PACKAGE_PROMPT = """You write captions for short-form video. Source video: "{title}" by {channel}.
For each clip below, write platform-specific copy. Return ONLY JSON:
[{{"index": <clip index>, "posts": {{
   "tiktok":    {{"title": "...", "caption": "<1-2 punchy lines + question/CTA>", "hashtags": ["..", ".."]}},
   "youtube":   {{"title": "<Shorts title, <=70 chars>", "caption": "...", "hashtags": [..]}},
   "instagram": {{"title": "...", "caption": "<hooky first line, then 1-2 lines>", "hashtags": [.. up to 8]}},
   "facebook":  {{"title": "...", "caption": "...", "hashtags": [..]}},
   "x":         {{"title": "...", "caption": "<=200 chars, no hashtag spam>", "hashtags": [.. max 2]}}
}}}}]
No emojis in titles; 1-2 emojis in captions are fine. Hashtags without '#'.

CLIPS:
{clips}
"""


def package(clips: list[Clip], video: VideoInfo, provider: str | None = None) -> list[Clip]:
    provider = (provider or settings.llm_provider).lower()
    if provider == "auto":
        provider = _detect_provider()

    llm_posts: dict[int, dict] = {}
    if provider != "none" and clips:
        try:
            desc = "\n".join(
                f"- index {c.index}: title='{c.highlight.title}', hook='{c.highlight.hook}', "
                f"mood={c.highlight.mood}, transcript='{_short(c)}'" for c in clips
            )
            raw = _complete(PACKAGE_PROMPT.format(title=video.title, channel=video.channel or "unknown",
                                                  clips=desc), provider)
            for item in _extract_json(raw):
                llm_posts[int(item["index"])] = item.get("posts", {})
        except Exception as exc:
            print(f"[packager] LLM failed ({exc}); using template captions")

    for clip in clips:
        for key, meta in PLATFORMS.items():
            data = llm_posts.get(clip.index, {}).get(key)
            if data:
                post = PlatformPost(platform=key, title=str(data.get("title", clip.highlight.title))[:100],
                                    caption=str(data.get("caption", ""))[: meta["caption_max"]],
                                    hashtags=[_clean_tag(t) for t in data.get("hashtags", [])][: meta["tags"] + 4])
            else:
                post = _template_post(clip, video, key, meta)
            clip.posts[key] = post
    return clips


def _short(clip: Clip) -> str:
    return (clip.highlight.reason or clip.highlight.title)[:160].replace("'", "")


def _clean_tag(t: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "", str(t))


def _template_post(clip: Clip, video: VideoInfo, key: str, meta: dict) -> PlatformPost:
    h = clip.highlight
    title = h.title or video.title
    hook = h.hook.capitalize() if h.hook else title
    credit = f"Clip from \"{video.title}\"" + (f" by {video.channel}" if video.channel else "")
    if key == "x":
        caption = f"{hook}\n\n{credit}"[:260]
    elif key == "youtube":
        caption = f"{hook}\n\n{credit}\nFull video: {video.url}" if video.url.startswith("http") else f"{hook}\n\n{credit}"
    else:
        caption = f"{hook} 👀\n\n{credit}\nFollow for more clips like this."
    tags = BASE_TAGS[key] + MOOD_TAGS.get(h.mood, MOOD_TAGS["general"])
    topic = [_clean_tag(w).lower() for w in re.findall(r"[A-Za-z]{5,}", video.title)][:2]
    tags = list(dict.fromkeys(tags + topic))[: meta["tags"] + 2]
    return PlatformPost(platform=key, title=title[:100], caption=caption, hashtags=tags)
