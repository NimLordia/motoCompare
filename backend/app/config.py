from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="MOTO_", extra="ignore")

    database_url: str = "postgresql+psycopg://moto:moto@localhost:5433/motocompare"


@lru_cache
def get_settings() -> Settings:
    return Settings()
