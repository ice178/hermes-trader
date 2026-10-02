from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
import signals_bot

from hermes_trading.candles import Candle
from hermes_trading.level_store import LevelStore
from hermes_trading.telegram_commands import CommandHandler, text_units
from hermes_trading.signal_filters import FilteredSignal
from hermes_trading.signals import SignalMatch
from signals_bot import (
    format_signal_message,
    metric_filter_enabled_from_env,
    send_signal_notifications,
    should_send_signal,
)


@pytest.mark.parametrize(
    (
        "volatility",
        "volume",
        "expected_volatility_line",
        "expected_volume_line",
    ),
    [
        ((10.0, 12.0), (10.0, 40.0), True, True),
        ((10.0, 12.0), (9.0, 40.0), True, False),
        ((9.0, 12.0), (10.0, 40.0), False, True),
        ((9.0, 12.0), (9.0, 40.0), False, False),
    ],
)
def test_signal_message_includes_only_passing_metrics(
    volatility: tuple[float, float],
    volume: tuple[float, float],
    expected_volatility_line: bool,
    expected_volume_line: bool,
) -> None:
    candle_open_ms = int(
        datetime(2026, 1, 15, 13, 45, tzinfo=timezone.utc).timestamp() * 1000
    )
    candle = Candle(
        timestamp=candle_open_ms,
        datetime="2026-01-15T14:45:00+01:00",
        open=100,
        high=105,
        low=99,
        close=104,
        volume=100,
        symbol="BTC/USDT",
        timeframe="15m",
    )
    signal = FilteredSignal(
        match=SignalMatch(
            pattern="pin_bar",
            direction="long",
            candle=candle,
            level=None,
        ),
        volatility_increase_pct=volatility,
        volume_increase_pct=volume,
    )

    message = format_signal_message(signal)

    assert message.startswith("<b>Symbol:</b> BTC/USDT\n")
    assert "<b>Market session:</b> <code>London + New York</code>" in message
    assert ("<b>Volatility vs previous 2 candles:</b>" in message) is (
        expected_volatility_line
    )
    assert ("<b>Volume vs previous 2 candles:</b>" in message) is (
        expected_volume_line
    )
    assert "Signal " not in message
    assert "Signals found" not in message
    assert "Metric filter" not in message
    assert "Elevated volatility" not in message
    assert "Elevated volume" not in message
    assert "\n\n" not in message
    if not expected_volatility_line and not expected_volume_line:
        assert message.endswith(
            "<b>Market session:</b> <code>London + New York</code>"
        )


@pytest.mark.parametrize("value", ["1", "true", "YES", "on"])
def test_metric_filter_config_accepts_enabled_values(monkeypatch, value: str) -> None:
    monkeypatch.setenv("SIGNAL_METRIC_FILTER_ENABLED", value)

    assert metric_filter_enabled_from_env()


@pytest.mark.parametrize("value", [None, "", "  "])
def test_metric_filter_config_defaults_to_enabled(
    monkeypatch,
    value: str | None,
) -> None:
    if value is None:
        monkeypatch.delenv("SIGNAL_METRIC_FILTER_ENABLED", raising=False)
    else:
        monkeypatch.setenv("SIGNAL_METRIC_FILTER_ENABLED", value)

    assert metric_filter_enabled_from_env()


@pytest.mark.parametrize("value", ["0", "false", "NO", "off"])
def test_metric_filter_config_accepts_disabled_values(monkeypatch, value: str) -> None:
    monkeypatch.setenv("SIGNAL_METRIC_FILTER_ENABLED", value)

    assert not metric_filter_enabled_from_env()


def test_metric_filter_config_rejects_unknown_value(monkeypatch) -> None:
    monkeypatch.setenv("SIGNAL_METRIC_FILTER_ENABLED", "sometimes")

    with pytest.raises(ValueError, match="SIGNAL_METRIC_FILTER_ENABLED"):
        metric_filter_enabled_from_env()


@pytest.mark.parametrize("volatility,volume,expected", [
    ((10.0, 10.0), (10.0, 10.0), True),
    ((9.9, 30.0), (20.0, 40.0), False),
    ((20.0, 9.9), (20.0, 40.0), False),
    ((20.0, 30.0), (9.9, 40.0), False),
    ((20.0, 30.0), (20.0, 9.9), False),
    ((0.0, 0.0), (0.0, 0.0), False),
])
def test_optional_metric_filter_controls_delivery(volatility, volume, expected) -> None:
    candle = Candle(
        timestamp=0,
        datetime="1970-01-01T01:00:00+01:00",
        open=100,
        high=105,
        low=99,
        close=104,
        volume=100,
        symbol="BTC/USDT",
        timeframe="15m",
    )
    signal = FilteredSignal(
        match=SignalMatch(
            pattern="pin_bar",
            direction="long",
            candle=candle,
            level=None,
        ),
        volatility_increase_pct=volatility,
        volume_increase_pct=volume,
    )

    assert should_send_signal(signal, metric_filter_enabled=False)
    assert should_send_signal(signal, metric_filter_enabled=True) is expected


@pytest.mark.parametrize("setting,expected_messages", [(None, 1), ("0", 2), ("1", 1)])
def test_live_scan_filters_telegram_delivery(monkeypatch, setting, expected_messages):
    if setting is None:
        monkeypatch.delenv("SIGNAL_METRIC_FILTER_ENABLED", raising=False)
    else:
        monkeypatch.setenv("SIGNAL_METRIC_FILTER_ENABLED", setting)
    monkeypatch.delenv("LEVELS_DB_PATH", raising=False)
    client, connector = Mock(), Mock()
    connector.client.fetch_ohlcv.return_value = []
    monkeypatch.setattr(signals_bot.TelegramConfig, "from_env", Mock(return_value=object()))
    monkeypatch.setattr(signals_bot, "TelegramClient", Mock(return_value=client))
    monkeypatch.setattr(signals_bot, "CONNECTOR_TYPES", {"bingx": lambda: connector})
    monkeypatch.setattr(signals_bot, "SCAN_MARKETS", {"bingx": ("BTC/USDT",)})
    monkeypatch.setattr(signals_bot, "SCAN_TIMEFRAMES", ("15m",))
    monkeypatch.setattr(signals_bot, "latest_fresh_batch", Mock(return_value=object()))
    rejected = _area_signal()
    accepted = FilteredSignal(
        SignalMatch("pin_bar", "long", rejected.match.candle, None),
        (10.0, 20.0), (30.0, 10.0),
    )
    monkeypatch.setattr(signals_bot, "latest_matches",
                        Mock(return_value=[rejected.match, accepted.match]))
    monkeypatch.setattr(signals_bot, "build_signal_metrics",
                        Mock(side_effect=[rejected, accepted]))

    signals_bot.main()

    assert client.send_text.call_count == expected_messages
    assert "Pin Bar" in client.send_text.call_args.args[0]
    if expected_messages == 1:
        assert "Inside Bar" not in client.send_text.call_args.args[0]


def test_signal_message_displays_candle_close_time() -> None:
    candle_open_ms = int(
        datetime(2026, 8, 3, 8, 0, tzinfo=timezone.utc).timestamp() * 1000
    )
    candle = Candle(
        timestamp=candle_open_ms,
        datetime="2026-08-03T10:00:00+02:00",
        open=1.0683,
        high=1.08,
        low=1.06,
        close=1.075,
        volume=100,
        symbol="XRP/USDT",
        timeframe="1h",
    )
    signal = FilteredSignal(
        match=SignalMatch(
            pattern="pin_bar",
            direction="long",
            candle=candle,
            level=None,
        ),
        volatility_increase_pct=(20.4, 73.5),
        volume_increase_pct=(64.1, 36.9),
    )

    message = format_signal_message(signal)

    assert "<b>Candle close:</b> 2026-08-03T11:00:00+02:00" in message
    assert "<b>Time:</b>" not in message
    assert "<b>Open price:</b> <code>1.0683</code>" in message
    assert "<b>Volatility vs previous 2 candles:</b>" in message
    assert "<b>Volume vs previous 2 candles:</b>" in message


def test_send_signal_notifications_sends_one_message_per_signal() -> None:
    candle = Candle(
        timestamp=0,
        datetime="1970-01-01T01:00:00+01:00",
        open=100,
        high=105,
        low=99,
        close=104,
        volume=100,
        symbol="BTC/USDT",
        timeframe="15m",
    )
    signal = FilteredSignal(
        match=SignalMatch(
            pattern="pin_bar",
            direction="long",
            candle=candle,
            level=None,
        ),
        volatility_increase_pct=(20.0, 30.0),
        volume_increase_pct=(20.0, 30.0),
    )
    client = Mock()

    send_signal_notifications(client, [signal, signal])

    assert client.send_text.call_count == 2
    for call in client.send_text.call_args_list:
        message = call.args[0]
        assert message.startswith("<b>Symbol:</b>")
        assert "Signals found" not in message
        assert call.kwargs == {"parse_mode": "HTML"}


def _area_signal():
    mother = Candle(timestamp=0, datetime="1970-01-01T00:00:00Z", open=110,
                    high=120, low=90, close=100, volume=100,
                    symbol="BTC/USDT", timeframe="15m")
    current = Candle(timestamp=900000, datetime="1970-01-01T00:15:00Z", open=100.5,
                     high=111, low=99, close=109.5, volume=100,
                     symbol="BTC/USDT", timeframe="15m")
    match = SignalMatch("inside_bar", "long", current, None, (mother, current))
    return FilteredSignal(match, (20.0, 30.0), (5.0, 6.0))


def _add_area(store, text, update_id=1):
    handler = CommandHandler(frozenset({42}), "test_bot")
    store.process_update({"update_id": update_id, "message": {
        "from": {"id": 42}, "chat": {"id": 42}, "text": text,
    }}, handler.handle)


def test_signal_enrichment_uses_mother_wick_and_escapes_comments(tmp_path):
    store = LevelStore(tmp_path / "levels.sqlite3")
    store.initialize()
    _add_area(store, "/levels_add BTC/USDT bingx buy 1d level 90 | <b>& note")
    _add_area(store, "/zone_add BTC/USDT bingx buy 4h imbalance 119 121", 2)
    _add_area(store, "/levels_add BTC/USDT bingx sell 1h level 100", 3)
    client, signal = Mock(), _area_signal()
    send_signal_notifications(client, [signal], level_store=store, exchange="bingx")
    message = client.send_text.call_args.args[0]
    assert message.startswith(format_signal_message(signal))
    assert "90, buy" in message and "119–121, buy" in message
    assert "source: 1d" in message and "source: 4h" in message
    assert "&lt;b&gt;&amp; note" in message
    assert "sell" not in message
    assert len(store.active_areas("bingx", "BTC/USDT")) == 3


def test_signal_without_matching_areas_is_unchanged(tmp_path):
    store = LevelStore(tmp_path / "levels.sqlite3")
    store.initialize()
    signal, client = _area_signal(), Mock()
    send_signal_notifications(client, [signal], level_store=store)
    client.send_text.assert_called_once_with(format_signal_message(signal), parse_mode="HTML")


def test_missing_database_does_not_suppress_signal(tmp_path, caplog):
    store = LevelStore(tmp_path / "missing.sqlite3")
    signal, client = _area_signal(), Mock()
    send_signal_notifications(client, [signal], level_store=store)
    message = client.send_text.call_args.args[0]
    assert message.startswith(format_signal_message(signal))
    assert "Manual levels: unavailable" in message and "unavailable" in caplog.text
    assert not store.path.exists()


def test_many_signal_areas_split_without_losing_records(tmp_path):
    import html

    store = LevelStore(tmp_path / "levels.sqlite3")
    store.initialize()
    for i in range(15):
        _add_area(store, f"/levels_add BTC/USDT bingx buy 4h level {100+i} | " + "😀" * 500, i)
    client = Mock()
    send_signal_notifications(client, [_area_signal()], level_store=store)
    messages = [call.args[0] for call in client.send_text.call_args_list]
    assert len(messages) > 1
    assert all(text_units(html.unescape(message)) <= 3500 for message in messages)
    assert sum(message.count("😀" * 500) for message in messages) == 15
