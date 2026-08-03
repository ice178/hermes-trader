from datetime import datetime, timezone

import pytest

from hermes_trading.candles import Candle
from hermes_trading.market_sessions import (
    active_market_sessions,
    market_session_label,
    signal_candle_market_session_label,
)


def _timestamp_ms(
    year: int,
    month: int,
    day: int,
    hour: int,
    minute: int = 0,
) -> int:
    return int(
        datetime(year, month, day, hour, minute, tzinfo=timezone.utc).timestamp()
        * 1000
    )


@pytest.mark.parametrize(
    ("timestamp_ms", "expected"),
    [
        (_timestamp_ms(2026, 1, 15, 0), ("Tokyo",)),
        (_timestamp_ms(2026, 1, 15, 9), ("London",)),
        (_timestamp_ms(2026, 1, 15, 13), ("London", "New York")),
        (_timestamp_ms(2026, 1, 15, 17), ("New York",)),
        (_timestamp_ms(2026, 1, 15, 22), ()),
    ],
)
def test_session_starts_are_inclusive_and_ends_are_exclusive(
    timestamp_ms: int,
    expected: tuple[str, ...],
) -> None:
    assert active_market_sessions(timestamp_ms) == expected


def test_tokyo_and_london_overlap_in_winter() -> None:
    timestamp_ms = _timestamp_ms(2026, 1, 15, 8, 30)

    assert market_session_label(timestamp_ms) == "Tokyo + London"


@pytest.mark.parametrize(
    ("timestamp_ms", "expected"),
    [
        (_timestamp_ms(2026, 1, 15, 14), "London + New York"),
        (_timestamp_ms(2026, 7, 15, 13), "London + New York"),
    ],
)
def test_london_and_new_york_overlap_across_dst(
    timestamp_ms: int,
    expected: str,
) -> None:
    assert market_session_label(timestamp_ms) == expected


def test_no_major_session_label() -> None:
    assert market_session_label(_timestamp_ms(2026, 1, 15, 23)) == (
        "No major session"
    )


def test_signal_uses_candle_close_time_for_session() -> None:
    candle = Candle(
        timestamp=_timestamp_ms(2026, 1, 15, 13, 45),
        datetime="2026-01-15T14:45:00+01:00",
        open=100,
        high=102,
        low=99,
        close=101,
        volume=100,
        symbol="TEST/USDT",
        timeframe="15m",
    )

    assert signal_candle_market_session_label(candle) == "London + New York"


def test_signal_session_requires_timeframe() -> None:
    candle = Candle(
        timestamp=_timestamp_ms(2026, 1, 15, 13, 45),
        datetime="2026-01-15T14:45:00+01:00",
        open=100,
        high=102,
        low=99,
        close=101,
        volume=100,
    )

    with pytest.raises(ValueError, match="timeframe"):
        signal_candle_market_session_label(candle)
