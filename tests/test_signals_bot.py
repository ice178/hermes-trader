from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from hermes_trading.candles import Candle
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


@pytest.mark.parametrize("value", [None, "", "0", "false", "NO", "off"])
def test_metric_filter_config_defaults_to_informational(
    monkeypatch,
    value: str | None,
) -> None:
    if value is None:
        monkeypatch.delenv("SIGNAL_METRIC_FILTER_ENABLED", raising=False)
    else:
        monkeypatch.setenv("SIGNAL_METRIC_FILTER_ENABLED", value)

    assert not metric_filter_enabled_from_env()


def test_metric_filter_config_rejects_unknown_value(monkeypatch) -> None:
    monkeypatch.setenv("SIGNAL_METRIC_FILTER_ENABLED", "sometimes")

    with pytest.raises(ValueError, match="SIGNAL_METRIC_FILTER_ENABLED"):
        metric_filter_enabled_from_env()


def test_optional_metric_filter_controls_delivery() -> None:
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
        volume_increase_pct=(9.0, 40.0),
    )

    assert should_send_signal(signal, metric_filter_enabled=False)
    assert not should_send_signal(signal, metric_filter_enabled=True)


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
