"""Simple trade management for backtesting."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Literal

from .candles import Candle
from .liquidity import Level


@dataclass
class Trade:
    symbol: str
    entry: float
    stop: float
    take: float
    risk: float
    opened_at: int
    pattern: str
    direction: Literal["long", "short"]
    level_price: float
    level_start: int
    level: Level
    closed_at: int | None = None
    result: str | None = None  # "take" or "stop"
    stop_price: float | None = None
    open_candle: Candle | None = None
    take_candle: Candle | None = None
    stop_candle: Candle | None = None
    stop_is_moved: bool = False


def open_trade(
    candle: Candle,
    pattern: str,
    level: Level,
    symbol: str,
    direction: Literal["long", "short"],
) -> Trade:
    """Create a direction-aware trade based on the closing candle."""

    if direction == "long":
        risk = max(candle.close - candle.low, 0) * 1.5
        stop = candle.close - risk
        take = candle.close + 2 * risk
    else:
        risk = max(candle.high - candle.close, 0) * 1.5
        stop = candle.close + risk
        take = candle.close - 2 * risk

    return Trade(
        symbol=symbol,
        entry=candle.close,
        stop=stop,
        take=take,
        risk=risk,
        opened_at=candle.timestamp,
        pattern=pattern,
        direction=direction,
        level_price=level.price,
        level_start=level.timestamp,
        level=level,
        open_candle=candle,
    )


def update_trades(trades: List[Trade], candle: Candle) -> None:
    """Update open trades based on a new candle."""
    for t in trades:
        if t.result:
            continue
        if t.direction == "long":
            stop_hit = candle.low <= t.stop
            take_hit = candle.high >= t.take
        else:
            stop_hit = candle.high >= t.stop
            take_hit = candle.low <= t.take

        if stop_hit:
            t.result = "stop"
            t.closed_at = candle.timestamp
            t.stop_price = candle.high if t.direction == "short" else candle.low
            t.stop_candle = candle
        elif take_hit:
            t.result = "take"
            t.closed_at = candle.timestamp
            t.take_candle = candle
        # elif candle.close > (t.entry + 1 * t.risk):
        #     t.stop_is_moved = True
        #     t.stop = t.entry + 1 * t.risk

def is_open_trade_exists(trades: List[Trade]) -> bool:
    for t in trades:
        if t.result is None:
            return True

    return False
