from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки из переменных окружения или файла .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql+psycopg://faceit:faceit@localhost:15432/faceit"

    # Без значения по умолчанию: приложение не стартует без секрета подписи токенов
    jwt_secret: SecretStr = Field(min_length=32)
    jwt_ttl_minutes: int = Field(default=30, ge=1, le=24 * 60)

    cors_origins: list[str] = ["http://localhost:5173"]

    faceit_api_key: SecretStr | None = None
    faceit_base_url: str = "https://open.faceit.com/data/v4"
    faceit_timeout_seconds: float = 10.0

    login_rate_limit: int = Field(default=5, ge=1)
    login_rate_window_seconds: int = Field(default=60, ge=1)

    docs_enabled: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()  # jwt_secret приходит из окружения
