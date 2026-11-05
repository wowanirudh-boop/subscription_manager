"""Settings from environment variables. Production values come from Secret Manager (see deploy/)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass
class Settings:
    database_url: str = field(default_factory=lambda: _env("DATABASE_URL", "sqlite:///./srt-dev.db"))
    jwt_secret: str = field(default_factory=lambda: _env("JWT_SECRET", "dev-only-jwt-secret-not-for-production-use"))
    jwt_ttl_days: int = 30
    # Google OAuth "web" client used to exchange the app's server auth code (D8: our own OAuth app).
    google_client_id: str = field(default_factory=lambda: _env("GOOGLE_OAUTH_CLIENT_ID"))
    google_client_secret: str = field(default_factory=lambda: _env("GOOGLE_OAUTH_CLIENT_SECRET"))
    # Token encryption (R10): Cloud KMS key in production, local Fernet key in development.
    kms_key_name: str = field(default_factory=lambda: _env("KMS_KEY_NAME"))
    local_token_key: str = field(default_factory=lambda: _env("LOCAL_TOKEN_KEY"))
    # Gmail push (R3): Pub/Sub topic Gmail publishes to; push subscription audience for JWT checks.
    pubsub_topic: str = field(default_factory=lambda: _env("PUBSUB_TOPIC"))
    pubsub_audience: str = field(default_factory=lambda: _env("PUBSUB_AUDIENCE"))
    pubsub_service_account: str = field(default_factory=lambda: _env("PUBSUB_SERVICE_ACCOUNT"))
    # Internal endpoints (Cloud Scheduler tick) authenticate with this shared secret.
    internal_token: str = field(default_factory=lambda: _env("INTERNAL_TOKEN", "dev-internal"))
    # Extraction provider: "openrouter" in production (Q2), "fake" in development.
    provider: str = field(default_factory=lambda: _env("EXTRACTION_PROVIDER", "fake"))
    # Delivery
    expo_push_url: str = "https://exp.host/--/api/v2/push/send"
    smtp_host: str = field(default_factory=lambda: _env("SMTP_HOST"))
    smtp_port: int = field(default_factory=lambda: int(_env("SMTP_PORT", "587")))
    smtp_user: str = field(default_factory=lambda: _env("SMTP_USER"))
    smtp_password: str = field(default_factory=lambda: _env("SMTP_PASSWORD"))
    mail_from: str = field(default_factory=lambda: _env("MAIL_FROM", "alerts@example.invalid"))
    disclosure_version: str = "gmail-disclosure-v1"
    region: str = field(default_factory=lambda: _env("REGION", "asia-south1"))  # R9: India


_settings: Settings | None = None


def settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
        if os.environ.get("ENV") == "production":
            missing = [n for n, v in [("JWT_SECRET", os.environ.get("JWT_SECRET")), ("KMS_KEY_NAME", _settings.kms_key_name),
                                      ("GOOGLE_OAUTH_CLIENT_ID", _settings.google_client_id),
                                      ("INTERNAL_TOKEN", os.environ.get("INTERNAL_TOKEN")),
                                      ("PUBSUB_AUDIENCE", _settings.pubsub_audience)] if not v]
            if missing:
                raise RuntimeError(f"production configuration missing: {', '.join(missing)}")
    return _settings


def reset_settings() -> None:
    global _settings
    _settings = None
