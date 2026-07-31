from datetime import datetime, timezone

from hermes_trading.candles import Candle
from hermes_trading.market_context import build_signal_market_context
from hermes_trading.time_utils import MADRID_TIMEZONE, madrid_datetime_from_timestamp_ms, timeframe_to_milliseconds

BASE_TIMESTAMP = int(
    datetime(2026, 1, 1, 0, 0, tzinfo=MADRID_TIMEZONE)
    .astimezone(timezone.utc)
    .timestamp()
    * 1000
)


def _candle(
    index: int,
    open_: float,
    high: float,
    low: float,
    close: float,
    *,
    timeframe: str = "15m",
) -> Candle:
    timestamp = BASE_TIMESTAMP + (index * timeframe_to_milliseconds(timeframe))
    return Candle(
        timestamp=timestamp,
        datetime=madrid_datetime_from_timestamp_ms(timestamp),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=100.0,
        symbol="BTC/USDT",
        timeframe=timeframe,
    )


def test_build_signal_market_context_computes_bias_range_and_volatility() -> None:
    candles = [
        _candle(0, 100, 102, 99, 101),
        _candle(1, 101, 103, 100, 102),
        _candle(2, 102, 104, 101, 103),
        _candle(3, 103, 105, 102, 104),
        _candle(4, 104, 106, 103, 105),
        _candle(5, 105, 107, 104, 106),
        _candle(6, 106, 108, 105, 107),
        _candle(7, 107, 109, 106, 108),
        _candle(8, 108, 110, 107, 109),
        _candle(9, 109, 111, 108, 110),
        _candle(10, 110, 112, 109, 111),
        _candle(11, 111, 113, 110, 112),
        _candle(12, 112, 114, 111, 113),
        _candle(13, 113, 115, 112, 114),
        _candle(14, 114, 116, 113, 115),
        _candle(15, 115, 123, 114, 122),
    ]

    context = build_signal_market_context(
        candles,
        15,
        range_lookback=4,
        recent_lookback=4,
        atr_period=4,
        bias_fast_period=2,
        bias_slow_period=3,
    )

    assert context.higher_timeframe == "1h"
    assert context.higher_timeframe_bias == "bullish"
    assert context.higher_timeframe_close == 122
    assert context.higher_timeframe_fast_sma == 117.0
    assert context.higher_timeframe_slow_sma == 114.0
    assert context.range_lookback == 4
    assert context.range_high == 123
    assert context.range_low == 111
    assert context.range_position_pct == ((122 - 111) / (123 - 111)) * 100
    assert context.recent_lookback == 4
    assert context.recent_high == 116
    assert context.recent_low == 110
    assert context.distance_to_recent_high_abs == 6
    assert context.distance_to_recent_high_pct == (6 / 122) * 100
    assert context.distance_to_recent_low_abs == 12
    assert context.distance_to_recent_low_pct == (12 / 122) * 100
    assert context.atr_period == 4
    assert context.atr_abs == 4.5
    assert context.atr_pct == (4.5 / 122) * 100
    assert context.signal_range_to_atr_ratio == 2.0
    assert context.volatility_regime == "expanded"
