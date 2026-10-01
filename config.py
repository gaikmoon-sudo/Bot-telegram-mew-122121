"""Central runtime configuration.

All secrets and deployment settings are read from environment variables or
platform secrets. No secret or connection value is stored in source control.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _bool(name: str, default: bool = False) -> bool:
    raw = _env(name, "true" if default else "false").lower()
    return raw in {"1", "true", "yes", "on"}


def _int(name: str, default: int, *, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        value = int(_env(name, str(default)))
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _float(name: str, default: float, *, minimum: float = 0.0, maximum: float = 1.0) -> float:
    try:
        value = float(_env(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _admin_ids() -> tuple[int, ...]:
    return tuple(int(item.strip()) for item in _env("ADMIN_IDS").split(",") if item.strip().isdigit())


def get_bot_token() -> str:
    token = _env("BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "BOT_TOKEN is not set. Add BOT_TOKEN to your Replit Secrets "
            "or environment variables."
        )
    return token


@dataclass(frozen=True)
class Settings:
    bot_token: str = field(default_factory=lambda: _env("BOT_TOKEN"))
    admin_ids: tuple[int, ...] = field(default_factory=_admin_ids)
    sentry_dsn: str = field(default_factory=lambda: _env("SENTRY_DSN"))
    sentry_traces_sample_rate: float = field(default_factory=lambda: _float("SENTRY_TRACES_SAMPLE_RATE", 0.10))
    sentry_profiles_sample_rate: float = field(default_factory=lambda: _float("SENTRY_PROFILES_SAMPLE_RATE", 0.0))
    environment: str = field(default_factory=lambda: _env("SENTRY_ENVIRONMENT", "production_replit") or "production_replit")
    redis_url: str = field(default_factory=lambda: _env("REDIS_URL"))
    database_url: str = field(default_factory=lambda: _env("DATABASE_URL"))
    timezone: str = field(default_factory=lambda: _env("APP_TIMEZONE", "UTC") or "UTC")
    content_storage_backend: str = field(default_factory=lambda: _env("CONTENT_STORAGE_BACKEND", "replit").lower())
    app_storage_bucket_id: str = field(default_factory=lambda: _env("APP_STORAGE_BUCKET_ID"))

    ai_enabled: bool = field(default_factory=lambda: _bool("AI_ENABLED", False))
    ai_provider: str = field(default_factory=lambda: _env("AI_PROVIDER", "openai") or "openai")
    ai_model: str = field(default_factory=lambda: _env("AI_MODEL", "gpt-5.6-luna") or "gpt-5.6-luna")
    openai_api_key: str = field(default_factory=lambda: _env("OPENAI_API_KEY"))
    ai_tutor_daily_limit: int = field(default_factory=lambda: _int("AI_TUTOR_DAILY_LIMIT", 10, minimum=0))
    ai_review_daily_limit: int = field(default_factory=lambda: _int("AI_REVIEW_DAILY_LIMIT", 3, minimum=0))
    ai_quiz_daily_limit: int = field(default_factory=lambda: _int("AI_QUIZ_DAILY_LIMIT", 1, minimum=0))
    ai_cache_ttl: int = field(default_factory=lambda: _int("AI_CACHE_TTL", 86400, minimum=0))

    webhook_url: str = field(default_factory=lambda: (
        _env("WEBHOOK_URL")
        or (f"https://{_env('REPLIT_APP_DOMAIN')}" if _env("REPLIT_APP_DOMAIN") else "")
    ).rstrip("/"))
    webhook_path: str = field(default_factory=lambda: _env("WEBHOOK_PATH", "/telegram/webhook") or "/telegram/webhook")
    webhook_secret: str = field(default_factory=lambda: _env("WEBHOOK_SECRET"))
    web_server_host: str = field(default_factory=lambda: _env("WEB_SERVER_HOST", "0.0.0.0") or "0.0.0.0")
    web_server_port: int = field(default_factory=lambda: _int("WEB_SERVER_PORT", 8080, minimum=1, maximum=65535))
    web_app_url: str = field(default_factory=lambda: _env("WEB_APP_URL").rstrip("/"))
    replit_app_domain: str = field(default_factory=lambda: _env("REPLIT_APP_DOMAIN"))
    replit_dev_domain: str = field(default_factory=lambda: _env("REPLIT_DEV_DOMAIN"))

    piston_api_url: str = field(default_factory=lambda: _env("PISTON_API_URL", "https://emkc.org/api/v2/piston").rstrip("/"))
    piston_api_key: str = field(default_factory=lambda: _env("PISTON_API_KEY"))
    piston_timeout_seconds: int = field(default_factory=lambda: _int("PISTON_TIMEOUT_SECONDS", 15, minimum=3, maximum=60))
    piston_compile_timeout_ms: int = field(default_factory=lambda: _int("PISTON_COMPILE_TIMEOUT_MS", 5000, minimum=1000, maximum=10000))
    piston_run_timeout_ms: int = field(default_factory=lambda: _int("PISTON_RUN_TIMEOUT_MS", 3000, minimum=500, maximum=10000))
    piston_max_concurrency: int = field(default_factory=lambda: _int("PISTON_MAX_CONCURRENCY", 4, minimum=1, maximum=32))
    piston_max_code_chars: int = field(default_factory=lambda: _int("PISTON_MAX_CODE_CHARS", 20000, minimum=1000, maximum=100000))
    piston_max_stdin_chars: int = field(default_factory=lambda: _int("PISTON_MAX_STDIN_CHARS", 5000, minimum=0, maximum=20000))
    piston_max_output_chars: int = field(default_factory=lambda: _int("PISTON_MAX_OUTPUT_CHARS", 12000, minimum=1000, maximum=100000))

    representative_username: str = field(default_factory=lambda: _env("REPRESENTATIVE_USERNAME", "alialgadiri"))
    developer_username: str = field(default_factory=lambda: _env("DEVELOPER_USERNAME", "Dark6j1"))
    admin_username: str = field(default_factory=lambda: _env("ADMIN_USERNAME", "Dark6j1"))

    def validate_production(self) -> None:
        """Validate required deployment configuration without making connections."""
        if self.content_storage_backend not in {"local", "replit"}:
            raise RuntimeError("CONTENT_STORAGE_BACKEND must be either 'local' or 'replit'.")
        # Replit production must use App Storage, while the permanent Docker
        # profile intentionally uses the persistent /app/data volume.
        if self.environment.lower() == "production_replit" and self.content_storage_backend == "local":
            raise RuntimeError("CONTENT_STORAGE_BACKEND=local is not allowed in production_replit; use Replit App Storage.")
        raw_admin_ids = _env("ADMIN_IDS")
        admin_parts = [part.strip() for part in raw_admin_ids.split(",") if part.strip()]
        if not admin_parts or any(not part.isdigit() or int(part) <= 0 for part in admin_parts):
            raise RuntimeError("ADMIN_IDS must contain comma-separated positive Telegram user IDs.")
        missing = [
            name for name, value in (
                ("BOT_TOKEN", self.bot_token),
                ("DATABASE_URL", self.database_url),
                ("REDIS_URL", self.redis_url),
                ("WEBHOOK_URL", self.webhook_url),
                ("WEBHOOK_SECRET", self.webhook_secret),
                ("ADMIN_IDS", ",".join(str(x) for x in self.admin_ids)),
            ) if not value
        ]
        if missing:
            raise RuntimeError("Missing required production settings: " + ", ".join(missing))
        parsed = urlparse(self.webhook_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise RuntimeError("WEBHOOK_URL must be a complete HTTPS URL.")
        if self.web_app_url:
            web_app = urlparse(self.web_app_url)
            if web_app.scheme != "https" or not web_app.netloc:
                raise RuntimeError("WEB_APP_URL must be a complete HTTPS URL.")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", self.webhook_secret):
            raise RuntimeError("WEBHOOK_SECRET must contain 1-256 letters, digits, underscores, or hyphens.")
        database = urlparse(self.database_url)
        if database.scheme not in {"postgres", "postgresql"} or not database.hostname:
            raise RuntimeError("DATABASE_URL must be a PostgreSQL URL with a hostname.")
        redis = urlparse(self.redis_url)
        if redis.scheme not in {"redis", "rediss"} or not redis.hostname:
            raise RuntimeError("REDIS_URL must be a redis:// or rediss:// URL with a hostname.")
        if self.ai_enabled and (self.ai_provider != "openai" or not self.openai_api_key):
            raise RuntimeError("When AI_ENABLED is true, configure AI_PROVIDER=openai and OPENAI_API_KEY.")


settings = Settings()
