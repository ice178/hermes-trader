import io
import json
from threading import Event
from unittest.mock import Mock
import urllib.error
import urllib.parse

import pytest

from hermes_trading.level_store import LevelStore
from hermes_trading.levels_listener import (
    LevelsListener, ListenerConfig, listener_lock,
)
from hermes_trading import levels_listener
from hermes_trading.telegram import TelegramClient, TelegramConfig, TelegramError
from hermes_trading.telegram_commands import CommandHandler


@pytest.fixture
def store(tmp_path):
    store = LevelStore(tmp_path / "levels.sqlite3")
    store.initialize()
    return store


def item(update_id=1):
    return {"update_id": update_id, "message": {
        "message_id": update_id, "from": {"id": 42}, "chat": {"id": -100},
        "text": "/levels_add BTC/USDT bingx buy 4h level 100",
    }}


def test_listener_processes_and_replies_to_command_chat_once(store):
    client, stop = Mock(), Event()
    handler = CommandHandler(frozenset({42}), "test_bot")
    calls = []

    def poll(offset, **kwargs):
        calls.append(offset)
        if len(calls) == 3:
            stop.set()
            return []
        return [item()]

    client.get_updates.side_effect = poll
    LevelsListener(client, store, handler, stop).run()
    assert calls == [None, 2, 2]
    assert client.send_text.call_count == 1
    assert client.send_text.call_args.kwargs == {"chat_id": -100}
    assert len(store.active_areas("bingx", "BTC/USDT")) == 1


def test_restart_drains_pending_reply_but_not_attempted_reply(store):
    handler = CommandHandler(frozenset({42}), "test_bot")
    store.process_update(item(), handler.handle)
    client = Mock()
    listener = LevelsListener(client, LevelStore(store.path), handler, Event())
    listener.drain_replies()
    listener.drain_replies()
    assert client.send_text.call_count == 1
    store.process_update(item(2), handler.handle)
    store.claim_reply()  # crash before or after send: delivery cannot be known
    listener.drain_replies()
    assert client.send_text.call_count == 1
    assert store.uncertain_reply_count() == 1


def test_ambiguous_send_failure_is_logged_and_not_retried(store, caplog):
    handler = CommandHandler(frozenset({42}), "test_bot")
    store.process_update(item(), handler.handle)
    client = Mock()
    client.send_text.side_effect = TelegramError()
    listener = LevelsListener(client, store, handler, Event())
    listener.drain_replies()
    listener.drain_replies()
    assert client.send_text.call_count == 1
    assert "delivery failed" in caplog.text
    assert len(store.active_areas("bingx", "BTC/USDT")) == 1


def test_rate_limit_requeues_definitely_rejected_reply(store):
    handler = CommandHandler(frozenset({42}), "test_bot")
    store.process_update(item(), handler.handle)
    client, stop = Mock(), Mock()
    stop.is_set.return_value = False
    client.send_text.side_effect = [TelegramError(429, 7), {}]
    listener = LevelsListener(client, store, handler, stop)
    listener.drain_replies()
    stop.wait.assert_called_once_with(7)
    listener.drain_replies()
    assert client.send_text.call_count == 2


def test_poll_backoff_is_bounded_and_interruptible(store):
    client, stop = Mock(), Mock()
    stop.is_set.return_value = False
    client.get_updates.side_effect = TelegramError(503)
    delays = []

    def wait(delay):
        delays.append(delay)
        if len(delays) == 8:
            stop.is_set.return_value = True

    stop.wait.side_effect = wait
    LevelsListener(client, store, Mock(), stop).run()
    assert delays == [1, 2, 4, 8, 16, 32, 60, 60]


@pytest.mark.parametrize("code", [401, 404, 409])
def test_poll_conflicts_and_bad_tokens_stop_instead_of_retrying(store, code):
    client, stop = Mock(), Mock()
    stop.is_set.return_value = False
    client.get_updates.side_effect = TelegramError(code)
    with pytest.raises(TelegramError):
        LevelsListener(client, store, Mock(), stop).run()
    stop.wait.assert_not_called()


def test_database_failure_does_not_advance_offset(store):
    import sqlite3

    stop, client, handler = Mock(), Mock(), Mock()
    stop.is_set.return_value = False
    client.get_updates.return_value = [item()]
    handler.handle.side_effect = sqlite3.OperationalError("busy")
    stop.wait.side_effect = lambda _: setattr(stop.is_set, "return_value", True)
    LevelsListener(client, store, handler, stop).run()
    assert store.offset() is None
    assert not store.active_areas("bingx", "BTC/USDT")


def test_shutdown_after_poll_does_not_acknowledge_unprocessed_updates(store):
    client, stop = Mock(), Event()

    def poll(*args, **kwargs):
        stop.set()
        return [item()]

    client.get_updates.side_effect = poll
    LevelsListener(client, store, Mock(), stop).run()
    assert store.offset() is None


def test_second_listener_is_rejected_and_lock_released(store):
    with listener_lock(store.path):
        with pytest.raises(ValueError, match="Another listener"):
            with listener_lock(store.path):
                pytest.fail("acquired the same lock")
    with listener_lock(store.path):
        pass


@pytest.mark.parametrize("value", ["", "-100", "42,", "42,bad", "0", "1.5"])
def test_invalid_allowlist_fails_closed(monkeypatch, value):
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", value)
    monkeypatch.setenv("LEVELS_DB_PATH", "/tmp/unused.sqlite3")
    with pytest.raises(ValueError, match="TELEGRAM_ALLOWED_USER_IDS"):
        ListenerConfig.from_env()


def test_config_requires_db_and_accepts_multiple_ids(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "42, 43")
    monkeypatch.delenv("LEVELS_DB_PATH", raising=False)
    with pytest.raises(ValueError, match="LEVELS_DB_PATH"):
        ListenerConfig.from_env()
    monkeypatch.setenv("LEVELS_DB_PATH", str(tmp_path / "levels.sqlite3"))
    assert ListenerConfig.from_env().allowed_user_ids == frozenset({42, 43})


def test_transport_encodes_poll_timeout_and_reply_destination(monkeypatch):
    calls = []

    def urlopen(url, **kwargs):
        calls.append((url, kwargs))
        return io.BytesIO(b'{"ok":true,"result":[]}')

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    client = TelegramClient(TelegramConfig("fake-token", "default-chat"))
    assert client.get_updates(123, timeout=30) == []
    payload = urllib.parse.parse_qs(calls[-1][1]["data"].decode())
    assert payload["offset"] == ["123"] and payload["timeout"] == ["30"]
    assert json.loads(payload["allowed_updates"][0]) == ["message"]
    assert calls[-1][1]["timeout"] == 40
    client.send_text("hello", chat_id=-100)
    payload = urllib.parse.parse_qs(calls[-1][1]["data"].decode())
    assert payload["chat_id"] == ["-100"]
    client.send_text("signal", parse_mode="HTML")
    payload = urllib.parse.parse_qs(calls[-1][1]["data"].decode())
    assert payload["chat_id"] == ["default-chat"]


@pytest.mark.parametrize("failure", ["http", "network", "json", "api", "incomplete", "shape"])
def test_transport_errors_never_expose_token_or_body(monkeypatch, failure):
    secret = "private-fake-token"

    def urlopen(url, **kwargs):
        if failure == "http":
            raise urllib.error.HTTPError(url, 429, secret, {}, io.BytesIO(
                json.dumps({"description": secret, "parameters": {"retry_after": 9}}).encode()))
        if failure == "network":
            raise urllib.error.URLError(secret)
        if failure == "json":
            return io.BytesIO(secret.encode())
        if failure == "incomplete":
            from http.client import IncompleteRead
            raise IncompleteRead(secret.encode())
        if failure == "shape":
            return io.BytesIO(b'{"ok": true, "result": {}}')
        return io.BytesIO(json.dumps({"ok": False, "error_code": 409, "description": secret}).encode())

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    client = TelegramClient(TelegramConfig(secret, "unused"))
    with pytest.raises(TelegramError) as exc:
        client.get_updates(None)
    assert secret not in str(exc.value)
    if failure == "http":
        assert exc.value.retry_after == 9


def test_main_handles_sigterm_and_releases_lock(monkeypatch, tmp_path):
    import signal

    db_path = tmp_path / "levels.sqlite3"
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "42")
    monkeypatch.setenv("LEVELS_DB_PATH", str(db_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "fake-chat")
    client = Mock()
    client.get_me.return_value = {"id": 1, "username": "test_bot"}

    def poll(*args, **kwargs):
        signal.raise_signal(signal.SIGTERM)
        return []

    client.get_updates.side_effect = poll
    monkeypatch.setattr(levels_listener, "TelegramClient", lambda _: client)
    monkeypatch.setattr(levels_listener.os, "umask", lambda _: None)
    old_handler = signal.getsignal(signal.SIGTERM)
    assert levels_listener.main() == 0
    assert signal.getsignal(signal.SIGTERM) == old_handler
    with listener_lock(db_path):
        pass
