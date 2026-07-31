from hermes_trading.time_utils import (
    is_candle_closed,
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
