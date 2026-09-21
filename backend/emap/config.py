"""Runtime settings. Read from the environment and the repo-root `.env` (git-ignored).

All paths in the settings are resolved relative to the repository root so the
app behaves the same whether launched from `/` or `/backend`.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env",),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Store
    emap_db_path: Path = Field(default=Path("backend/data/energymap.duckdb"))

    # API
    emap_host: str = "127.0.0.1"
    emap_port: int = 8000
    emap_cors_origins: str = "http://localhost:5173"

    # ENTSO-E token: human-obtained by email (~3 working days). Empty until granted.
    entsoe_token: str = ""

    @field_validator("emap_db_path")
    @classmethod
    def _resolve_relative_to_repo(cls, v: Path) -> Path:
        return v if v.is_absolute() else (REPO_ROOT / v).resolve()

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.emap_cors_origins.split(",") if o.strip()]


def get_settings() -> Settings:
    return Settings()
