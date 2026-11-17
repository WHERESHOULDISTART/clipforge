"""Create a synthetic test video + fake word-level transcript so the pipeline can
be exercised without network access or a Whisper model.

    python tests/make_fixture.py  ->  tests/fixtures/sample.mp4 + sample.transcript.json
"""

from __future__ import annotations

import json
import random
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from clipforge.models import Segment, Transcript, Word  # noqa: E402

FIX = Path(__file__).parent / "fixtures"
MONOLOGUE = """
Okay so nobody talks about this but it is literally the biggest mistake new creators make.
They spend ten hours editing one video and then post it once and wonder why nothing happens.
Here's the truth. The algorithm does not care how long you worked. It cares about the first three seconds.
If you don't hook them, you lose. That's it. Game over.
So what do you actually do? You take your best moment, you put it first, and you cut everything else.
I tested this on forty videos last month. Forty! The ones that opened with the punchline got five times the views.
Five times. Not five percent. Five hundred percent more views from one simple change.
And honestly the craziest part is that it costs you nothing. Zero dollars. Zero new tools.
You already have the footage. You already have the moment. You just put it in the wrong place.
Now here's where people push back. They say but my story needs context. No it doesn't.
Nobody is waiting for context. They're scrolling. You have to earn the context.
Let me give you a real example. My friend Sam had a cooking channel. Great food, terrible numbers.
We moved the final reveal to the start of every video. Boom. Two hundred thousand subscribers in six months.
Same recipes. Same kitchen. Same camera. Different order. That's insane when you think about it.
So stop asking how to make better content and start asking what is the most intense moment I already have.
Find it. Clip it. Lead with it. That is the whole secret. That's the video.
"""


def main() -> None:
    FIX.mkdir(parents=True, exist_ok=True)
    video = FIX / "sample.mp4"
    duration = 100
    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i", f"testsrc2=size=1280x720:rate=30:duration={duration}",
        "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration={duration}",
        "-vf", "drawtext=text='%{pts\\:hms}':fontsize=64:fontcolor=white:x=(w-tw)/2:y=h/2-32:box=1:boxcolor=black@0.5",
        "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac", "-shortest", str(video),
    ], check=True)

    random.seed(7)
    t = 1.0
    segments = []
    for sentence in [s.strip() for s in MONOLOGUE.strip().splitlines() if s.strip()]:
        words = []
        for raw in sentence.split():
            dur = 0.14 + 0.03 * len(raw) + random.uniform(-0.03, 0.06)
            words.append(Word(text=raw, start=round(t, 2), end=round(t + dur, 2), prob=0.95))
            t += dur + random.uniform(0.02, 0.09)
        segments.append(Segment(start=words[0].start, end=words[-1].end, text=sentence, words=words))
        t += random.uniform(0.25, 0.7)
    transcript = Transcript(language="en", duration=float(duration), segments=segments)
    (FIX / "sample.transcript.json").write_text(transcript.model_dump_json(indent=1))
    print(f"wrote {video} and transcript ending at {t:.1f}s with {len(transcript.words)} words")


if __name__ == "__main__":
    main()
