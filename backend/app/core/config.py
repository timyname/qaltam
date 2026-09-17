from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_STORAGE_PATH = (PROJECT_ROOT / "storage").resolve()
DEFAULT_DB_PATH = (DEFAULT_STORAGE_PATH / "db" / "qaltam_v2.db").resolve()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(default="QALTAM", alias="APP_NAME")
    app_env: str = Field(default="local", alias="APP_ENV")
    app_debug: bool = Field(default=True, alias="APP_DEBUG")
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT")
    database_url: str = Field(
        default=f"sqlite+aiosqlite:///{DEFAULT_DB_PATH.as_posix()}",
        alias="DATABASE_URL",
    )
    local_storage_path: Path = Field(default=DEFAULT_STORAGE_PATH, alias="LOCAL_STORAGE_PATH")
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_webapp_url: str = Field(default="http://localhost:5173", alias="TELEGRAM_WEBAPP_URL")
    quick_add_api_key: str = Field(default="secret_local_key", alias="QUICK_ADD_API_KEY")
    default_currency: str = Field(default="KZT", alias="DEFAULT_CURRENCY")
    safe_withdrawal_buffer: int = Field(default=50_000, alias="SAFE_WITHDRAWAL_BUFFER")
    deepseek_api_key: str = Field(default="", alias="DEEPSEEK_API_KEY")
    deepseek_base_url: str = Field(default="https://api.deepseek.com/v1", alias="DEEPSEEK_BASE_URL")
    deepseek_model: str = Field(default="deepseek-chat", alias="DEEPSEEK_MODEL")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.local_storage_path.mkdir(parents=True, exist_ok=True)
    (settings.local_storage_path / "db").mkdir(parents=True, exist_ok=True)
    (settings.local_storage_path / "imports").mkdir(parents=True, exist_ok=True)
    return settings
