from pathlib import Path
from typing import Literal

from pydantic import Field
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
