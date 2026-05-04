"""Application configuration loaded from environment variables."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Runtime configuration loaded from .env and environment."""

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    discord_bot_token: str = Field(default="", alias="DISCORD_BOT_TOKEN")
    coach_guild_id: int | None = Field(default=None, alias="COACH_GUILD_ID")

    twelve_data_api_key: str = Field(default="", alias="TWELVE_DATA_API_KEY")
    cryptopanic_api_key: str = Field(default="", alias="CRYPTOPANIC_API_KEY")
    etherscan_api_key: str = Field(default="", alias="ETHERSCAN_API_KEY")

    coach_daily_hour_utc: int = Field(default=6, alias="COACH_DAILY_HOUR_UTC")
    coach_timezone: str = Field(default="UTC", alias="COACH_TIMEZONE")
    coach_default_risk_pct: float = Field(default=1.0, alias="COACH_DEFAULT_RISK_PCT")
    coach_db_url: str = Field(default="sqlite+aiosqlite:///data/coach.db", alias="COACH_DB_URL")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    charts_dir: Path = ROOT_DIR / "charts"
    data_dir: Path = ROOT_DIR / "data"

    def ensure_dirs(self) -> None:
        self.charts_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()
