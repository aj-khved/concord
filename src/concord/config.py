from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://concord:concord_dev_password@localhost:5432/concord"

    anthropic_api_key: str | None = None
    # Deliberately NOT named anthropic_base_url: pydantic-settings maps field
    # names to env vars case-insensitively, and a dev machine (or this coding
    # session) may have ANTHROPIC_BASE_URL set for unrelated tooling — the app
    # must never silently inherit that.
    llm_base_url: str = "https://api.anthropic.com"
    llm_model: str = "claude-haiku-4-5-20251001"
    llm_max_calls_per_run: int = 200


settings = Settings()
