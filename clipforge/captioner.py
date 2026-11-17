"""Step 5 — trendy animated captions, rendered as ASS and burned in by ffmpeg/libass.

Why ASS instead of frame-by-frame rendering: libass handles per-word colour,
scale, pop/bounce animation and outlines natively, so a 60s clip renders in
seconds on a CPU. Each *line* (a group of 3-5 words) gets one Dialogue event
per spoken word, with that word highlighted — the "karaoke / Hormozi" effect.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .models import Word

STYLES_DIR = Path(__file__).parent / "styles"
FONTS_DIR = Path(__file__).parent / "fonts"


@dataclass
class CaptionStyle:
    name: str
    font: str
    font_file: str
    font_size: int = 90
    uppercase: bool = True
    words_per_line: int = 3
    max_line_seconds: float = 2.2
    primary_color: str = "#FFFFFF"
    highlight_color: str = "#FFD400"
    outline_color: str = "#000000"
    back_color: str = "#000000"
    outline: int = 6
    shadow: int = 2
    blur: int = 0
    border_style: int = 1
    highlight_mode: str = "color"  # color | box | underline
    highlight_box_color: str = "#FF3B30"
    highlight_scale: int = 115
    line_pop: bool = True
    position_y: float = 0.7
    letter_spacing: int = 0
    word_colors: list[str] = field(default_factory=list)
    reframe: str = "crop"  # crop | blur | fit
    description: str = ""

    @classmethod
    def load(cls, name_or_path: str) -> "CaptionStyle":
        p = Path(name_or_path)
        if not p.exists():
            p = STYLES_DIR / f"{name_or_path}.json"
        if not p.exists():
            raise FileNotFoundError(f"Unknown caption style '{name_or_path}'. Available: {', '.join(list_styles())}")
        data = json.loads(p.read_text())
        known = {k for k in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})


def list_styles() -> list[str]:
    return sorted(p.stem for p in STYLES_DIR.glob("*.json"))


# ----------------------------------------------------------------------------
# ASS helpers
# ----------------------------------------------------------------------------

def ass_color(hex_color: str, alpha: int = 0) -> str:
    """#RRGGBB -> &HAABBGGRR (ASS is little-endian BGR)."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"&H{alpha:02X}{b:02X}{g:02X}{r:02X}"


def ass_time(t: float) -> str:
    t = max(0.0, t)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h}:{m:02}:{s:05.2f}"


def _escape(text: str) -> str:
    return text.replace("{", "(").replace("}", ")").replace("\\", "/")


def group_words(words: list[Word], per_line: int, max_seconds: float) -> list[list[Word]]:
    """Group words into caption lines: at most `per_line` words, `max_seconds`
    long, and never spanning a long pause or a sentence end."""
    lines: list[list[Word]] = []
    cur: list[Word] = []
    for w in words:
        if cur:
            too_many = len(cur) >= per_line
            too_long = (w.end - cur[0].start) > max_seconds
            pause = (w.start - cur[-1].end) > 0.6
            sentence_end = cur[-1].text[-1:] in ".!?"
            if too_many or too_long or pause or sentence_end:
                lines.append(cur)
                cur = []
        cur.append(w)
    if cur:
        lines.append(cur)
    return lines


def build_ass(words: list[Word], style: CaptionStyle, clip_start: float, clip_end: float,
              width: int = 1080, height: int = 1920, hook: str | None = None) -> str:
    """Build the full ASS document for a clip. Word times are absolute; the clip
    is assumed to start at `clip_start` so we subtract it."""
    primary = ass_color(style.primary_color)
    outline_c = ass_color(style.outline_color)
    back_c = ass_color(style.back_color, 0 if style.border_style in (3, 4) else 128)
    margin_v = int(height * (1 - style.position_y))

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{style.font},{style.font_size},{primary},{primary},{outline_c},{back_c},-1,0,0,0,100,100,{style.letter_spacing},0,{style.border_style},{style.outline},{style.shadow},2,60,60,{margin_v},1
Style: Hook,{style.font},{int(style.font_size * 0.72)},{primary},{primary},{outline_c},{back_c},-1,0,0,0,100,100,{style.letter_spacing},0,1,{max(style.outline - 1, 2)},{style.shadow},8,80,80,{int(height * 0.12)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events: list[str] = []
    clip_words = [w for w in words if w.end > clip_start and w.start < clip_end]
    lines = group_words(clip_words, style.words_per_line, style.max_line_seconds)

    blur_tag = f"\\blur{style.blur}" if style.blur else ""

    for line in lines:
        line_start = max(line[0].start, clip_start)
        line_end = min(line[-1].end + 0.08, clip_end)
        for i, w in enumerate(line):
            w_start = max(w.start, clip_start)
            w_end = line[i + 1].start if i + 1 < len(line) else line_end
            w_end = min(w_end, clip_end)
            if w_end - w_start < 0.02:
                continue

            parts = []
            for j, other in enumerate(line):
                txt = _escape(other.text.upper() if style.uppercase else other.text)
                if style.word_colors:
                    base_c = ass_color(style.word_colors[j % len(style.word_colors)])
                else:
                    base_c = primary
                if j == i:
                    parts.append(_highlight(txt, style, base_c))
                else:
                    parts.append(f"{{\\c{base_c}\\fscx100\\fscy100}}{txt}")
            text = " ".join(parts)

            pop = ""
            if style.line_pop and i == 0:
                pop = "\\fscx82\\fscy82\\t(0,110,\\fscx100\\fscy100)"
            text = f"{{\\an2{blur_tag}{pop}}}" + text
            events.append(
                f"Dialogue: 0,{ass_time(w_start - clip_start)},{ass_time(w_end - clip_start)},Cap,,0,0,0,,{text}"
            )

    if hook:
        hook_txt = _escape(hook.upper() if style.uppercase else hook)
        events.insert(0, (
            f"Dialogue: 1,{ass_time(0)},{ass_time(min(3.0, clip_end - clip_start))},Hook,,0,0,0,,"
            f"{{\\an8\\fad(80,250)\\fscx70\\fscy70\\t(0,150,\\fscx100\\fscy100)}}{hook_txt}"
        ))

    return header + "\n".join(events) + "\n"


def _highlight(txt: str, style: CaptionStyle, base_c: str) -> str:
    hl = ass_color(style.highlight_color)
    s = style.highlight_scale
    anim = f"\\fscx{s + 10}\\fscy{s + 10}\\t(0,90,\\fscx{s}\\fscy{s})"
    if style.highlight_mode == "box":
        box = ass_color(style.highlight_box_color)
        return f"{{\\c{hl}\\3c{box}\\bord{style.outline + 10}{anim}}}{txt}{{\\3c{ass_color(style.outline_color)}\\bord{style.outline}}}"
    if style.highlight_mode == "underline":
        return f"{{\\c{hl}\\u1{anim}}}{txt}{{\\u0}}"
    return f"{{\\c{hl}{anim}}}{txt}"
