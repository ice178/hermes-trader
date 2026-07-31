import pytest

from hermes_trading.time_utils import (
    is_candle_closed,
    is_candle_freshly_closed,
    madrid_datetime_from_timestamp_ms,
    timeframe_to_milliseconds,
)


def test_madrid_datetime_from_timestamp_ms_uses_madrid_offset() -> None:
    assert (
        madrid_datetime_from_timestamp_ms(1577836800000)
        == "2020-01-01T01:00:00+01:00"
    )


def test_timeframe_to_milliseconds_converts_supported_values() -> None:
    assert timeframe_to_milliseconds("15m") == 900_000
    assert timeframe_to_milliseconds("1h") == 3_600_000


def test_is_candle_closed_returns_true_when_interval_elapsed() -> None:
    candle_timestamp = 1_577_836_800_000
    close_time = candle_timestamp + timeframe_to_milliseconds("15m")

    assert is_candle_closed(candle_timestamp, "15m", now_ms=close_time)


def test_is_candle_closed_returns_false_for_open_interval() -> None:
    candle_timestamp = 1_577_836_800_000
    before_close = candle_timestamp + timeframe_to_milliseconds("15m") - 1

    assert not is_candle_closed(candle_timestamp, "15m", now_ms=before_close)


def test_is_candle_freshly_closed_observes_window_boundaries() -> None:
    candle_timestamp = 1_577_836_800_000
    close_time = candle_timestamp + timeframe_to_milliseconds("30m")
    freshness_ms = timeframe_to_milliseconds("15m")

    assert not is_candle_freshly_closed(
        candle_timestamp,
        "30m",
        freshness_ms=freshness_ms,
        now_ms=close_time - 1,
    )
    assert is_candle_freshly_closed(
        candle_timestamp,
        "30m",
        freshness_ms=freshness_ms,
        now_ms=close_time,
    )
    assert is_candle_freshly_closed(
        candle_timestamp,
        "30m",
        freshness_ms=freshness_ms,
        now_ms=close_time + freshness_ms - 1,
    )
    assert not is_candle_freshly_closed(
        candle_timestamp,
        "30m",
        freshness_ms=freshness_ms,
        now_ms=close_time + freshness_ms,
    )


def test_is_candle_freshly_closed_rejects_non_positive_window() -> None:
    with pytest.raises(ValueError, match="freshness_ms must be positive"):
        is_candle_freshly_closed(0, "15m", freshness_ms=0, now_ms=0)


@pytest.mark.parametrize(
    ("timestamp_ms", "timeframe", "now_ms", "expected"),
    [
        (45 * 60_000, "15m", 61 * 60_000, True),
        (30 * 60_000, "30m", 61 * 60_000, True),
        (0, "1h", 61 * 60_000, True),
        (0, "4h", 61 * 60_000, False),
        (0, "4h", 241 * 60_000, True),
        (60 * 60_000, "15m", 76 * 60_000, True),
        (30 * 60_000, "30m", 76 * 60_000, False),
        (0, "1h", 76 * 60_000, False),
    ],
)
def test_is_candle_freshly_closed_selects_expected_scheduled_timeframes(
    timestamp_ms: int,
    timeframe: str,
    now_ms: int,
    expected: bool,
) -> None:
    assert (
        is_candle_freshly_closed(
            timestamp_ms,
            timeframe,
            freshness_ms=15 * 60_000,
            now_ms=now_ms,
        )
        is expected
    )
