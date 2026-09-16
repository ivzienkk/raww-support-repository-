from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"


@dataclass(frozen=True)
class Settings:
    discord_token: str | None
    database_path: str
    dashboard_token: str | None
    dashboard_host: str
    dashboard_port: int
    dashboard_debug: bool


def load_settings() -> Settings:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return Settings(
        discord_token=os.getenv("DISCORD_TOKEN"),
        database_path=os.getenv("DATABASE_PATH", str(DATA_DIR / "bot.sqlite3")),
        dashboard_token=os.getenv("DASHBOARD_TOKEN"),
        dashboard_host=os.getenv("DASHBOARD_HOST", "0.0.0.0"),
        dashboard_port=int(os.getenv("PORT", os.getenv("DASHBOARD_PORT", "5000"))),
        dashboard_debug=os.getenv("FLASK_DEBUG", "").lower() == "true",
    )
