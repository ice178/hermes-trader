from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from .candles import Candle


@dataclass(frozen=True)
class CandleGeometry:
    candle_range: float
    body_size: float
    upper_wick: float
    lower_wick: float
    wick_ratio: float
    close_location: float | None


@dataclass(frozen=True)
class EntryFeatures:
    atr14: float | None
    ema200: float | None
    ema200_side: Literal["above", "below", "near"] | None
    sl_in_atr: float | None
    tp_in_atr: float | None
    distance_to_level_atr: float | None
    hour_utc: int
    session: Literal["asia", "europe", "us"]
    candle_range: float
    body_size: float
    upper_wick: float
    lower_wick: float
    wick_ratio: float
    close_location: float | None
    touched_level: bool
    reclaimed_level: bool
    sweep_size_atr: float | None


def compute_true_range(prev_close: float, candle: Candle) -> float:
    return max(
        candle.high - candle.low,
        abs(candle.high - prev_close),
        abs(candle.low - prev_close),
    )


def compute_atr(candles: list[Candle], period: int, index: int) -> float | None:
    if index < period:
        return None
    trs: list[float] = []
    for i in range(index - period + 1, index + 1):
        prev_close = candles[i - 1].close
        trs.append(compute_true_range(prev_close, candles[i]))
    if not trs:
        return None
    return sum(trs) / period


def compute_ema(candles: list[Candle], period: int, index: int) -> float | None:
    if index < period - 1:
        return None
    closes = [c.close for c in candles[: index + 1]]
    if len(closes) < period:
        return None
    sma = sum(closes[:period]) / period
    multiplier = 2 / (period + 1)
    ema = sma
    for close in closes[period:]:
        ema = (close - ema) * multiplier + ema
    return ema


def compute_candle_geometry(candle: Candle, *, epsilon: float = 1e-9) -> CandleGeometry:
    candle_range = candle.high - candle.low
    body_size = abs(candle.close - candle.open)
    upper_wick = candle.high - max(candle.open, candle.close)
    lower_wick = min(candle.open, candle.close) - candle.low
    wick_ratio = max(upper_wick, lower_wick) / max(body_size, epsilon)
    close_location = None
    if candle_range > 0:
        close_location = (candle.close - candle.low) / candle_range
    return CandleGeometry(
        candle_range=candle_range,
        body_size=body_size,
        upper_wick=upper_wick,
        lower_wick=lower_wick,
        wick_ratio=wick_ratio,
        close_location=close_location,
    )


def compute_session(hour_utc: int) -> Literal["asia", "europe", "us"]:
    if 0 <= hour_utc <= 7:
        return "asia"
    if 8 <= hour_utc <= 15:
        return "europe"
    return "us"


def compute_entry_features(
    *,
    candles: list[Candle],
    index: int,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    level_price: float,
    side: Literal["long", "short"],
    ema200_near_atr: float,
) -> EntryFeatures:
    candle = candles[index]
    atr14 = compute_atr(candles, 14, index)
    ema200 = compute_ema(candles, 200, index)

    ema200_side: Literal["above", "below", "near"] | None = None
    if ema200 is not None:
        if atr14 is not None and abs(entry_price - ema200) < ema200_near_atr * atr14:
            ema200_side = "near"
        elif entry_price > ema200:
            ema200_side = "above"
        else:
            ema200_side = "below"

    sl_in_atr = None
    tp_in_atr = None
    distance_to_level_atr = None
    sweep_size_atr = None
    if atr14 is not None and atr14 != 0:
        sl_in_atr = abs(entry_price - stop_loss) / atr14
        tp_in_atr = abs(entry_price - take_profit) / atr14
        distance_to_level_atr = abs(entry_price - level_price) / atr14

        if side == "short":
            sweep_size_atr = max(candle.high - level_price, 0) / atr14
        else:
            sweep_size_atr = max(level_price - candle.low, 0) / atr14

    geometry = compute_candle_geometry(candle)

    touched_level = candle.high >= level_price if side == "short" else candle.low <= level_price
    reclaimed_level = candle.close < level_price if side == "short" else candle.close > level_price

    dt = datetime.fromisoformat(candle.datetime)
    hour_utc = dt.hour

    return EntryFeatures(
        atr14=atr14,
        ema200=ema200,
        ema200_side=ema200_side,
        sl_in_atr=sl_in_atr,
        tp_in_atr=tp_in_atr,
        distance_to_level_atr=distance_to_level_atr,
        hour_utc=hour_utc,
        session=compute_session(hour_utc),
        candle_range=geometry.candle_range,
        body_size=geometry.body_size,
        upper_wick=geometry.upper_wick,
        lower_wick=geometry.lower_wick,
        wick_ratio=geometry.wick_ratio,
        close_location=geometry.close_location,
        touched_level=touched_level,
        reclaimed_level=reclaimed_level,
        sweep_size_atr=sweep_size_atr,
    )
