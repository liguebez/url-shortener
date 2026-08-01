from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parent.parent / ".env", extra="ignore"
    )

    base_url: str
    log_level: str = "INFO"
    database_url: str
    redis_url: str
    cache_ttl_seconds: int = 3600
    negative_cache_ttl_seconds: int = 60
    short_id_length: int = 7
    max_key_retries: int = 5
    max_url_length: int = 2048


@lru_cache
def get_settings() -> Settings:
    return Settings()


SettingsDep = Annotated[Settings, Depends(get_settings)]
