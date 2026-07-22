from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="MOTO_", extra="ignore")

    database_url: str = "postgresql+psycopg://moto:moto@localhost:5433/motocompare"

    # Research pipeline. Without MOTO_ANTHROPIC_API_KEY the Claude SDK falls back
    # to its own credential resolution (ANTHROPIC_API_KEY etc.).
    anthropic_api_key: str | None = None
    research_model: str = "claude-opus-4-8"
    research_max_attempts: int = 3
    research_max_web_searches: int = 8
    research_workers: int = 2
    # Same-tier numeric sources whose spread exceeds this fraction of their mean
    # are an unresolved conflict.
    research_conflict_tolerance: float = 0.15
    # Chat's inline research budget; past it, research continues in the background.
    research_inline_budget_seconds: float = 20.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
