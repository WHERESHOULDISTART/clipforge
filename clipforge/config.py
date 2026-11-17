"""Configuration. Everything can be set via environment variables or a .env file.

Example .env:

    CLIPFORGE_LLM_PROVIDER=anthropic      # anthropic | openai | ollama | none
    ANTHROPIC_API_KEY=sk-ant-...
    CLIPFORGE_WHISPER_MODEL=small         # tiny | base | small | medium | large-v3
    CLIPFORGE_WHISPER_DEVICE=auto         # auto | cpu | cuda
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CLIPFORGE_", env_file=".env", extra="ignore")

    # Storage
    work_dir: Path = Path("workspace")

    # Transcription
    whisper_model: str = "small"
    whisper_device: str = "auto"  # auto | cpu | cuda
    whisper_compute_type: str = "default"  # int8 | float16 | default

    # Highlight detection
    llm_provider: str = "auto"  # auto | anthropic | openai | ollama | none
    llm_model: str | None = None
    ollama_host: str = "http://localhost:11434"

    # Clips
    default_clip_count: int = 5
    min_clip_seconds: float = 15.0
    max_clip_seconds: float = 60.0
    default_style: str = "hormozi"
    output_width: int = 1080
    output_height: int = 1920

    # Browser publishing
    browser_profile_dir: Path = Path("browser_profile")
    browser_channel: str = "chromium"  # chromium | chrome | msedge

    @property
    def downloads_dir(self) -> Path:
        return self.work_dir / "downloads"

    @property
    def clips_dir(self) -> Path:
        return self.work_dir / "clips"

    @property
    def jobs_dir(self) -> Path:
        return self.work_dir / "jobs"

    def ensure_dirs(self) -> None:
        for d in (self.downloads_dir, self.clips_dir, self.jobs_dir):
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
