"""Application configuration. Every tunable comes from environment variables
(or a local .env file) so deployments never require code changes."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- database ---
    database_url: str = "postgresql+psycopg://outreach:outreach@localhost:5432/outreach"

    # --- redis / celery ---
    redis_url: str = "redis://localhost:6379/0"

    # --- auth ---
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 30

    # --- LLM provider (free-tier first; swap via env, no code change) ---
    llm_provider: str = "groq"  # groq | gemini | anthropic
    llm_api_key: str = ""
    llm_model: str = ""  # provider default used when empty

    # --- polite crawling ---
    crawl_delay_seconds: float = 2.0
    crawl_user_agent: str = "AIValyticsOutreachBot/0.1 (+contact: outreach@aivalytics.example)"

    # --- public base URL for unsubscribe/tracking links ---
    public_base_url: str = "http://localhost:8000"
    cors_origins: str = "http://localhost:3000"

    # --- sending & compliance (hard limits enforced in sender service) ---
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    sender_name: str = ""
    sender_email: str = ""
    sender_postal_address: str = ""  # required in every footer
    daily_send_cap: int = 25         # warm-up default; raise gradually
    hourly_send_cap: int = 10
    max_touches: int = 4             # 1 initial + 3 follow-ups, never more
    followup_days: tuple[int, int, int] = (3, 7, 14)

    # --- attachments ---
    attachment_storage_dir: str = "data/attachments"
    max_attachment_size_bytes: int = 25 * 1024 * 1024
    max_attachments_per_draft: int = 10


@lru_cache
def get_settings() -> Settings:
    return Settings()
