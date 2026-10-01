import pytest

from config import Settings


def _set_valid_environment(monkeypatch):
    values = {
        "BOT_TOKEN": "123456:placeholder-token",
        "ADMIN_IDS": "123456789,987654321",
        "DATABASE_URL": "postgresql://user:pass@db.example:5432/academy",
        "REDIS_URL": "rediss://default:pass@redis.example:6380/0",
        "WEBHOOK_SECRET": "Valid_webhook-secret_123",
        "WEBHOOK_URL": "https://academy.example/telegram/webhook",
        "CONTENT_STORAGE_BACKEND": "replit",
        "AI_ENABLED": "false",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_production_settings_accept_valid_replit_configuration(monkeypatch):
    _set_valid_environment(monkeypatch)
    Settings().validate_production()


def test_production_settings_reject_invalid_admin_ids(monkeypatch):
    _set_valid_environment(monkeypatch)
    monkeypatch.setenv("ADMIN_IDS", "123456789,not-a-user")
    with pytest.raises(RuntimeError, match="ADMIN_IDS"):
        Settings().validate_production()


def test_production_settings_reject_invalid_webhook_secret(monkeypatch):
    _set_valid_environment(monkeypatch)
    monkeypatch.setenv("WEBHOOK_SECRET", "bad secret!")
    with pytest.raises(RuntimeError, match="WEBHOOK_SECRET"):
        Settings().validate_production()


def test_ai_enabled_requires_openai_credentials(monkeypatch):
    _set_valid_environment(monkeypatch)
    monkeypatch.setenv("AI_ENABLED", "true")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        Settings().validate_production()
