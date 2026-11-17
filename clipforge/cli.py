"""Command line interface.

    clipforge serve                       # open the web UI
    clipforge make <url> [--style neon]   # run the pipeline headless
    clipforge publish <job> <clip> tiktok # open the browser uploader
    clipforge styles                      # list caption styles
"""

from __future__ import annotations

import webbrowser
from pathlib import Path

import typer

from . import __version__
from .config import settings

app = typer.Typer(add_completion=False, help="ClipForge — YouTube → viral clips → post from your browser.")


@app.callback(invoke_without_command=True)
def _root(ctx: typer.Context,
          version: bool = typer.Option(False, "--version", help="Show version and exit")):
    if version:
        typer.echo(f"clipforge {__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8420, open_browser: bool = True, reload: bool = False):
    """Start the web UI."""
    import uvicorn

    url = f"http://{host}:{port}"
    typer.secho(f"\n  ✂️  ClipForge  →  {url}\n", fg="yellow", bold=True)
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    uvicorn.run("clipforge.web.app:app", host=host, port=port, reload=reload, log_level="info")


@app.command()
def make(
    source: str = typer.Argument(..., help="YouTube URL or local video path"),
    style: str = typer.Option(settings.default_style, help="Caption style (see `clipforge styles`)"),
    clips: int = typer.Option(settings.default_clip_count, help="How many clips to make"),
    reframe: str = typer.Option(None, help="crop | blur | fit (default: style's choice)"),
    language: str = typer.Option(None, help="Force transcription language code, e.g. en"),
):
    """Run the whole pipeline and print the output clips."""
    from .pipeline import new_job, run_job

    job = new_job(source, style, clips, reframe, language)
    last = {"status": None}

    def on_update(j):
        if j.status != last["status"] or j.status == "rendering":
            typer.echo(f"[{j.status:12}] {j.progress * 100:5.1f}%  {j.message}")
            last["status"] = j.status

    run_job(job, on_update)
    if job.status == "error":
        typer.secho(f"\nFailed: {job.error}", fg="red")
        raise typer.Exit(1)

    typer.secho(f"\nJob {job.id}: {len(job.clips)} clips", fg="green", bold=True)
    for c in job.clips:
        h = c.highlight
        typer.echo(f"  {c.index}. [{h.start:6.1f}-{h.end:6.1f}] 🔥{h.score:3.0f}  {h.title}")
        typer.echo(f"     {c.video_path}")
    typer.echo(f"\nPublish one with:  clipforge publish {job.id} 1 tiktok")


@app.command()
def publish(job_id: str, clip: int, platform: str,
            auto_submit: bool = typer.Option(False, help="Try to press Post for you (X/TikTok only)")):
    """Open the platform's upload page with the clip attached and caption filled."""
    from .packager import PLATFORMS
    from .pipeline import Job
    from .publisher import browser

    if platform not in PLATFORMS:
        typer.secho(f"platform must be one of: {', '.join(PLATFORMS)}", fg="red")
        raise typer.Exit(2)
    job = Job.load(job_id)
    c = next((x for x in job.clips if x.index == clip), None)
    if not c:
        typer.secho("clip not found", fg="red")
        raise typer.Exit(2)
    post = c.posts.get(platform)
    state = browser.run_blocking(platform, Path(c.video_path),
                                 caption=post.full_caption if post else "", title=post.title if post else c.highlight.title,
                                 auto_submit=auto_submit)
    typer.echo(f"{state['status']}: {state['message']}")


@app.command()
def styles():
    """List caption styles."""
    from .captioner import CaptionStyle, list_styles

    for n in list_styles():
        s = CaptionStyle.load(n)
        typer.echo(f"  {n:10}  {s.name:9}  {s.description}")


@app.command()
def jobs():
    """List previous jobs."""
    from .pipeline import Job

    for j in Job.list_all():
        title = j.video.title if j.video else j.source
        typer.echo(f"  {j.id}  {j.status:10}  {len(j.clips)} clips  {title}")


if __name__ == "__main__":
    app()
