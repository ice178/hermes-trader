"""Market context features for signal-level backtests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .candles import Candle
from .time_utils import timeframe_to_milliseconds

DEFAULT_CONTEXT_RANGE_LOOKBACK = 20
DEFAULT_CONTEXT_RECENT_LOOKBACK = 20
DEFAULT_CONTEXT_ATR_PERIOD = 14
DEFAULT_CONTEXT_BIAS_FAST_PERIOD = 5
DEFAULT_CONTEXT_BIAS_SLOW_PERIOD = 20

HIGHER_TIMEFRAME_MAP = {
    "5m": "15m",
    "15m": "1h",
    "30m": "4h",
    "1h": "4h",
    "4h": "1d",
}


@dataclass(frozen=True)
class SignalMarketContext:
    higher_timeframe: str | None
    higher_timeframe_bias: str | None
    higher_timeframe_close: float | None
    higher_timeframe_fast_sma: float | None
    higher_timeframe_slow_sma: float | None
    range_lookback: int
    range_high: float | None
    range_low: float | None
    range_position_pct: float | None
    recent_lookback: int
    recent_high: float | None
    recent_low: float | None
    distance_to_recent_high_abs: float | None
    distance_to_recent_high_pct: float | None
    distance_to_recent_low_abs: float | None
    distance_to_recent_low_pct: float | None
    atr_period: int
    atr_abs: float | None
    atr_pct: float | None
    signal_range_to_atr_ratio: float | None
    volatility_regime: str | None


def _pct_of_price(value: float | None, price: float | None) -> float | None:
    if value is None or price is None or price == 0:
        return None
    return (value / price) * 100


def _sma(values: Sequence[float], period: int) -> float | None:
    if period <= 0 or len(values) < period:
        return None
    window = values[-period:]
    return sum(window) / len(window)


def _aggregate_candles(
    candles: Sequence[Candle],
    *,
    target_timeframe: str,
    closed_before_or_at: int,
) -> list[Candle]:
    if not candles:
        return []

    target_ms = timeframe_to_milliseconds(target_timeframe)
    buckets: dict[int, Candle] = {}

    for candle in candles:
        bucket_timestamp = (candle.timestamp // target_ms) * target_ms
        bucket = buckets.get(bucket_timestamp)
        if bucket is None:
            buckets[bucket_timestamp] = Candle(
                timestamp=bucket_timestamp,
                datetime=candle.datetime,
                open=float(candle.open),
                high=float(candle.high),
                low=float(candle.low),
                close=float(candle.close),
                volume=float(candle.volume),
                symbol=candle.symbol,
                timeframe=target_timeframe,
            )
            continue

        bucket.high = max(float(bucket.high), float(candle.high))
        bucket.low = min(float(bucket.low), float(candle.low))
        bucket.close = float(candle.close)
        bucket.volume = float(bucket.volume) + float(candle.volume)

    return [
        buckets[timestamp]
        for timestamp in sorted(buckets)
        if timestamp + target_ms <= closed_before_or_at
    ]


def _higher_timeframe_bias(
    candles: Sequence[Candle],
    *,
    source_timeframe: str,
    signal_available_at_timestamp: int,
    fast_period: int,
    slow_period: int,
) -> tuple[str | None, str | None, float | None, float | None, float | None]:
    higher_timeframe = HIGHER_TIMEFRAME_MAP.get(source_timeframe)
    if higher_timeframe is None:
        return None, None, None, None, None

    aggregated = _aggregate_candles(
        candles,
        target_timeframe=higher_timeframe,
        closed_before_or_at=signal_available_at_timestamp,
    )
    if not aggregated:
        return higher_timeframe, None, None, None, None

    closes = [float(candle.close) for candle in aggregated]
    last_close = closes[-1]
    fast_sma = _sma(closes, fast_period)
    slow_sma = _sma(closes, slow_period)
    if fast_sma is None or slow_sma is None:
        return higher_timeframe, None, last_close, fast_sma, slow_sma

    if last_close > fast_sma > slow_sma:
        bias = "bullish"
    elif last_close < fast_sma < slow_sma:
        bias = "bearish"
    else:
        bias = "neutral"
    return higher_timeframe, bias, last_close, fast_sma, slow_sma


def _range_context(
    candles: Sequence[Candle],
    *,
    signal_index: int,
    lookback: int,
) -> tuple[float | None, float | None, float | None]:
    if lookback <= 0:
        raise ValueError("lookback must be positive")

    window = candles[max(0, signal_index - lookback + 1) : signal_index + 1]
    if not window:
        return None, None, None

    range_high = max(float(candle.high) for candle in window)
    range_low = min(float(candle.low) for candle in window)
    range_size = range_high - range_low
    if range_size <= 0:
        return range_high, range_low, None

    signal_close = float(candles[signal_index].close)
    range_position_pct = ((signal_close - range_low) / range_size) * 100
    return range_high, range_low, range_position_pct


def _recent_extremes_context(
    candles: Sequence[Candle],
    *,
    signal_index: int,
    lookback: int,
) -> tuple[float | None, float | None, float | None, float | None]:
    if lookback <= 0:
        raise ValueError("lookback must be positive")

    window = candles[max(0, signal_index - lookback) : signal_index]
    if not window:
        return None, None, None, None

    signal_close = float(candles[signal_index].close)
    recent_high = max(float(candle.high) for candle in window)
    recent_low = min(float(candle.low) for candle in window)
    return (
        recent_high,
        recent_low,
        abs(recent_high - signal_close),
        abs(signal_close - recent_low),
    )


def _true_range(current_candle: Candle, previous_close: float | None) -> float:
    base_range = float(current_candle.high) - float(current_candle.low)
    if previous_close is None:
        return base_range
    return max(
        base_range,
        abs(float(current_candle.high) - previous_close),
        abs(float(current_candle.low) - previous_close),
    )


def _atr_context(
    candles: Sequence[Candle],
    *,
    signal_index: int,
    period: int,
) -> tuple[float | None, float | None, float | None, str | None]:
    if period <= 0:
        raise ValueError("period must be positive")

    if signal_index < 0 or signal_index >= len(candles):
        raise IndexError("signal_index is out of bounds")

    start_index = max(0, signal_index - period + 1)
    tr_values: list[float] = []
    for candle_index in range(start_index, signal_index + 1):
        previous_close = (
            float(candles[candle_index - 1].close)
            if candle_index > 0
            else None
        )
        tr_values.append(_true_range(candles[candle_index], previous_close))

    if not tr_values:
        return None, None, None, None

    atr_abs = sum(tr_values) / len(tr_values)
    signal_close = float(candles[signal_index].close)
    atr_pct = _pct_of_price(atr_abs, signal_close)
    signal_range = float(candles[signal_index].high) - float(candles[signal_index].low)
    signal_range_to_atr_ratio = (
        signal_range / atr_abs
        if atr_abs > 0
        else None
    )
    if signal_range_to_atr_ratio is None:
        volatility_regime = None
    elif signal_range_to_atr_ratio < 0.8:
        volatility_regime = "compressed"
    elif signal_range_to_atr_ratio > 1.2:
        volatility_regime = "expanded"
    else:
        volatility_regime = "normal"

    return atr_abs, atr_pct, signal_range_to_atr_ratio, volatility_regime


def build_signal_market_context(
    candles: Sequence[Candle],
    signal_index: int,
    *,
    range_lookback: int = DEFAULT_CONTEXT_RANGE_LOOKBACK,
    recent_lookback: int = DEFAULT_CONTEXT_RECENT_LOOKBACK,
    atr_period: int = DEFAULT_CONTEXT_ATR_PERIOD,
    bias_fast_period: int = DEFAULT_CONTEXT_BIAS_FAST_PERIOD,
    bias_slow_period: int = DEFAULT_CONTEXT_BIAS_SLOW_PERIOD,
) -> SignalMarketContext:
    if signal_index < 0 or signal_index >= len(candles):
        raise IndexError("signal_index is out of bounds")

    signal_candle = candles[signal_index]
    source_timeframe = signal_candle.timeframe
    if source_timeframe is None:
        raise ValueError("signal candle timeframe is required")

    signal_available_at_timestamp = (
        signal_candle.timestamp + timeframe_to_milliseconds(source_timeframe)
    )
    series_until_signal = candles[: signal_index + 1]

    (
        higher_timeframe,
        higher_timeframe_bias,
        higher_timeframe_close,
        higher_timeframe_fast_sma,
        higher_timeframe_slow_sma,
    ) = _higher_timeframe_bias(
        series_until_signal,
        source_timeframe=source_timeframe,
        signal_available_at_timestamp=signal_available_at_timestamp,
        fast_period=bias_fast_period,
        slow_period=bias_slow_period,
    )
    range_high, range_low, range_position_pct = _range_context(
        candles,
        signal_index=signal_index,
        lookback=range_lookback,
    )
    (
        recent_high,
        recent_low,
        distance_to_recent_high_abs,
        distance_to_recent_low_abs,
    ) = _recent_extremes_context(
        candles,
        signal_index=signal_index,
        lookback=recent_lookback,
    )
    atr_abs, atr_pct, signal_range_to_atr_ratio, volatility_regime = _atr_context(
        candles,
        signal_index=signal_index,
        period=atr_period,
    )

    signal_close = float(signal_candle.close)
    return SignalMarketContext(
        higher_timeframe=higher_timeframe,
        higher_timeframe_bias=higher_timeframe_bias,
        higher_timeframe_close=higher_timeframe_close,
        higher_timeframe_fast_sma=higher_timeframe_fast_sma,
        higher_timeframe_slow_sma=higher_timeframe_slow_sma,
        range_lookback=range_lookback,
        range_high=range_high,
        range_low=range_low,
        range_position_pct=range_position_pct,
        recent_lookback=recent_lookback,
        recent_high=recent_high,
        recent_low=recent_low,
        distance_to_recent_high_abs=distance_to_recent_high_abs,
        distance_to_recent_high_pct=_pct_of_price(distance_to_recent_high_abs, signal_close),
        distance_to_recent_low_abs=distance_to_recent_low_abs,
        distance_to_recent_low_pct=_pct_of_price(distance_to_recent_low_abs, signal_close),
        atr_period=atr_period,
        atr_abs=atr_abs,
        atr_pct=atr_pct,
        signal_range_to_atr_ratio=signal_range_to_atr_ratio,
        volatility_regime=volatility_regime,
    )


__all__ = [
    "DEFAULT_CONTEXT_ATR_PERIOD",
    "DEFAULT_CONTEXT_BIAS_FAST_PERIOD",
    "DEFAULT_CONTEXT_BIAS_SLOW_PERIOD",
    "DEFAULT_CONTEXT_RANGE_LOOKBACK",
    "DEFAULT_CONTEXT_RECENT_LOOKBACK",
    "HIGHER_TIMEFRAME_MAP",
    "SignalMarketContext",
    "build_signal_market_context",
]
