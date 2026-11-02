"""Application settings, read from environment variables (or api/.env locally)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "local"
    database_url: str = "postgresql+psycopg://finance:finance@localhost:5432/finance"

    # "dev": every request is one local demo user (no sign-in, local and tests only).
    # "entra": real sign-in with Microsoft Entra External ID; each person has their own data.
    auth_mode: str = "dev"
    demo_user_email: str = "demo@local"
    admin_emails: list[str] = ["demo@local"]

    # Entra External ID (only used when auth_mode is "entra"). None of these are secrets.
    entra_tenant_subdomain: str = ""
    entra_tenant_id: str = ""
    entra_api_client_id: str = ""
    entra_required_scope: str = "access_as_user"

    @property
    def entra_metadata_url(self) -> str:
        return (
            f"https://{self.entra_tenant_subdomain}.ciamlogin.com/"
            f"{self.entra_tenant_id}/v2.0/.well-known/openid-configuration"
        )

    def check(self) -> None:
        """Fail at startup, not on the first request, if sign-in is misconfigured."""
        if self.auth_mode not in {"dev", "entra"}:
            raise RuntimeError(f"AUTH_MODE must be 'dev' or 'entra', not {self.auth_mode!r}")
        if self.auth_mode == "entra":
            missing = [
                name
                for name in ("entra_tenant_subdomain", "entra_tenant_id", "entra_api_client_id")
                if not getattr(self, name)
            ]
            if missing:
                raise RuntimeError(f"AUTH_MODE=entra needs: {', '.join(m.upper() for m in missing)}")

    cors_origins: list[str] = ["http://localhost:5173"]

    fx_provider: str = "frankfurter"
    fx_base_url: str = "https://api.frankfurter.dev/v2"
    fx_timeout_seconds: float = 10.0

    max_upload_bytes: int = 5 * 1024 * 1024


settings = Settings()
