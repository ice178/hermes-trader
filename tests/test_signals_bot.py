from datetime import datetime, timezone

import pytest

from hermes_trading.candles import Candle
from hermes_trading.signal_filters import FilteredSignal
from hermes_trading.signals import SignalMatch
from signals_bot import (
    format_signal_message,
    metric_filter_enabled_from_env,
    should_send_signal,
)


@pytest.mark.parametrize(
    (
        "volatility",
        "volume",
        "expected_volatility_status",
        "expected_volume_status",
    ),
    [
        ((10.0, 12.0), (10.0, 40.0), "YES", "YES"),
        ((10.0, 12.0), (9.0, 40.0), "YES", "NO"),
        ((9.0, 12.0), (10.0, 40.0), "NO", "YES"),
        ((9.0, 12.0), (9.0, 40.0), "NO", "NO"),
    ],
)
def test_signal_message_reports_session_and_metric_statuses(
    volatility: tuple[float, float],
    volume: tuple[float, float],
    expected_volatility_status: str,
    expected_volume_status: str,
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

    message = format_signal_message(signal, index=1, total=1)

    assert "<b>Market session:</b> <code>London + New York</code>" in message
    assert (
        "<b>Metric filter:</b> "
        "<code>DISABLED — metrics are informational only</code>"
    ) in message
    assert (
        "<b>Elevated volatility (≥10% vs both):</b> "
        f"<code>{expected_volatility_status}</code>"
    ) in message
    assert (
        "<b>Elevated volume (≥10% vs both):</b> "
        f"<code>{expected_volume_status}</code>"
    ) in message


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

    message = format_signal_message(
        signal,
        index=1,
        total=1,
        metric_filter_enabled=True,
    )

    assert "<b>Candle close:</b> 2026-08-03T11:00:00+02:00" in message
    assert "<b>Time:</b>" not in message
    assert "<b>Open price:</b> <code>1.0683</code>" in message
    assert "<code>ENABLED — signal passed</code>" in message
