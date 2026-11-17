"""Runtime configuration, read from `UPCYCLING_*` environment variables (and `.env` locally)."""

from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
DEV_SECRET_KEY = "dev-only-insecure-secret-key-change-me-0000"  # noqa: S105 - rejected in production
DEV_DATABASE_URL = "postgresql+psycopg://upcycling:upcycling@localhost:55432/upcycling"
DEV_STORAGE_SECRET = "upcycling-dev-storage-secret"  # noqa: S105 - rejected in production

# Production must receive these explicitly from the environment; defaults are for development.
REQUIRED_IN_PRODUCTION = (
    "database_url",
    "public_origin",
    "secret_key",
    "smtp_host",
    "smtp_from",
    "storage_endpoint_url",
    "storage_bucket",
    "storage_access_key_id",
    "storage_secret_access_key",
)

MIB = 1024 * 1024


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="UPCYCLING_",
        env_file=REPO_ROOT / ".env",
        extra="ignore",
    )

    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"

    database_url: str = DEV_DATABASE_URL

    # Origin the expert uses in the browser. Magic links point here, and it is
    # the default allowed `Origin` for state-changing requests (ADR-0003, ADR-0005).
    public_origin: str = "http://localhost:5173"
    extra_allowed_origins: list[str] = []

    # Used for HMAC of one-time codes and of rate-limit identifiers.
    secret_key: SecretStr = SecretStr(DEV_SECRET_KEY)

    # With Secure cookies the browser-visible name gets the `__Host-` prefix (see
    # `session_cookie_key`): host-only, Path=/, Secure, so no subdomain can set or shadow it.
    session_cookie_name: str = "upcycling_session"
    session_cookie_secure: bool = True
    session_ttl_seconds: int = 30 * 24 * 3600

    login_ttl_seconds: int = 15 * 60
    login_code_max_attempts: int = 5
    login_rate_limit_window_seconds: int = 15 * 60
    login_rate_limit_per_email: int = 5
    login_rate_limit_per_ip: int = 20

    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_starttls: bool = False
    smtp_use_tls: bool = False
    smtp_timeout_seconds: float = 10.0
    smtp_from: str = "Upcycling <no-reply@upcycling.local>"

    # S3-compatible object storage (ADR-0006). The backend talks to `storage_endpoint_url`;
    # presigned upload URLs are built for `storage_public_endpoint_url`, which must be
    # reachable from the expert's browser (defaults to the same endpoint).
    storage_endpoint_url: str = "http://localhost:8333"
    storage_public_endpoint_url: str | None = None
    storage_region: str = "us-east-1"
    storage_bucket: str = "upcycling"
    storage_access_key_id: str = "upcycling-dev"
    storage_secret_access_key: SecretStr = SecretStr(DEV_STORAGE_SECRET)
    storage_addressing_style: Literal["path", "virtual"] = "path"

    upload_url_ttl_seconds: int = 15 * 60
    upload_max_bytes: int = 30 * MIB
    image_max_pixels: int = 100_000_000
    garment_max_photos: int = 40
    pending_uploads_per_user: int = 20
    # Voice notes (ADR-0007). The client stops recording at the duration limit; the server
    # accepts a small tolerance for encoder padding.
    voice_note_max_bytes: int = 20 * MIB
    voice_note_max_seconds: int = 300
    garment_max_voice_notes: int = 20
    # Unfinished uploads and rejected photos older than this are removed by `storage-sweep`.
    stale_upload_seconds: int = 24 * 3600

    @property
    def allowed_origins(self) -> frozenset[str]:
        return frozenset([self.public_origin, *self.extra_allowed_origins])

    @property
    def storage_presign_endpoint_url(self) -> str:
        return self.storage_public_endpoint_url or self.storage_endpoint_url

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def session_cookie_key(self) -> str:
        if self.session_cookie_secure:
            return f"__Host-{self.session_cookie_name}"
        return self.session_cookie_name

    @model_validator(mode="after")
    def _enforce_production_safety(self) -> Self:
        if not self.is_production:
            return self
        secret = self.secret_key.get_secret_value()
        problems = [
            f"UPCYCLING_{name.upper()} must be set explicitly"
            for name in REQUIRED_IN_PRODUCTION
            if name not in self.model_fields_set
        ]
        if secret == DEV_SECRET_KEY or len(secret) < 32:
            problems.append("UPCYCLING_SECRET_KEY must be a random value of at least 32 chars")
        if not self.session_cookie_secure:
            problems.append("UPCYCLING_SESSION_COOKIE_SECURE must be true")
        if not all(o.startswith("https://") for o in self.allowed_origins):
            problems.append("UPCYCLING_PUBLIC_ORIGIN and extra allowed origins must use https")
        if self.database_url == DEV_DATABASE_URL:
            problems.append("UPCYCLING_DATABASE_URL must not be the development database")
        if not (self.smtp_starttls or self.smtp_use_tls):
            problems.append("SMTP must use TLS (UPCYCLING_SMTP_STARTTLS or UPCYCLING_SMTP_USE_TLS)")
        if self.storage_secret_access_key.get_secret_value() == DEV_STORAGE_SECRET:
            problems.append("UPCYCLING_STORAGE_SECRET_ACCESS_KEY must not be the development value")
        if not all(
            url.startswith("https://")
            for url in (self.storage_endpoint_url, self.storage_presign_endpoint_url)
        ):
            problems.append("Storage endpoints must use https")
        if problems:
            raise ValueError("Unsafe production configuration: " + "; ".join(problems))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
