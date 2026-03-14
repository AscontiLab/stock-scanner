"""Dashboard-Konfiguration via pydantic-settings."""

from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    SCANNER_DIR: Path = Path(__file__).parent.parent
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""
    DASHBOARD_PORT: int = 8091
    CACHE_TTL_SECONDS: int = 300  # 5min Cache fuer Portfolio-Check

    model_config = {"env_file": str(Path(__file__).parent.parent / ".env"), "extra": "ignore"}


settings = Settings()
