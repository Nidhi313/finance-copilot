"""Application settings, read from environment variables (or api/.env locally)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "local"
    database_url: str = "postgresql+psycopg://finance:finance@localhost:5432/finance"

    # "dev" signs every request in as one local demo user. Real sign-in (Entra
    # External ID) replaces this before the app is deployed anywhere public.
    auth_mode: str = "dev"
    demo_user_email: str = "demo@local"
    admin_emails: list[str] = ["demo@local"]

    cors_origins: list[str] = ["http://localhost:5173"]

    fx_provider: str = "frankfurter"
    fx_base_url: str = "https://api.frankfurter.dev/v2"
    fx_timeout_seconds: float = 10.0

    max_upload_bytes: int = 5 * 1024 * 1024


settings = Settings()
