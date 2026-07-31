import pytest

from hermes_trading import get_telegram_chat_id
from hermes_trading.telegram import TelegramConfig


def test_telegram_config_reads_required_environment(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "test-chat")

    config = TelegramConfig.from_env()

    assert config.bot_token == "test-token"
    assert config.chat_id == "test-chat"
    assert config.verify_ssl is True


def test_telegram_config_reports_missing_environment(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID"):
        TelegramConfig.from_env()


def test_get_chat_id_uses_environment_token(monkeypatch, capsys):
    captured = {}
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")

    def fake_request_updates(token, **kwargs):
        captured["token"] = token
        return {"ok": True, "result": []}

    monkeypatch.setattr(get_telegram_chat_id, "_request_updates", fake_request_updates)

    assert get_telegram_chat_id.main([]) == 0
    assert captured["token"] == "test-token"
    assert "No updates found" in capsys.readouterr().out
