from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SECOND_BRAIN_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    vault_path: Path = Field(default_factory=lambda: Path.home() / "second-brain-vault")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    local_only: bool = False

    litellm_base_url: AnyHttpUrl = Field(  # type: ignore[assignment]
        default="http://localhost:4000"
    )
    litellm_master_key: SecretStr | None = Field(default=None)

    # Capture layer
    capture_watch_dirs: list[Path] = Field(default_factory=list)
    capture_extensions: list[str] = Field(
        default_factory=lambda: [".md", ".pdf", ".txt", ".png", ".jpg", ".jpeg", ".webp"]
    )
    clipper_port: int = 7331
    clipper_host: str = "127.0.0.1"
    whisper_model_size: str = "base"
