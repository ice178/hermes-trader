"""Simple trade management for backtesting."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .candles import Candle
from .liquidity import Level


@dataclass
class Trade:
    entry: float
    stop: float
    take: float
    opened_at: int
    pattern: str
    level_price: float
    level_start: int
    closed_at: int | None = None
    result: str | None = None  # "take" or "stop"


def open_trade(candle: Candle, pattern: str, level: Level) -> Trade:
    """Create a trade based on the closing candle."""
    risk = candle.close - candle.low
    return Trade(
        entry=candle.close,
        stop=candle.low,
        take=candle.close + 2 * risk,
        opened_at=candle.timestamp,
        pattern=pattern,
        level_price=level.price,
        level_start=level.timestamp,
    )


def update_trades(trades: List[Trade], candle: Candle) -> None:
    """Update open trades based on a new candle."""
    for t in trades:
        if t.result:
            continue
        if candle.low <= t.stop:
            t.result = "stop"
            t.closed_at = candle.timestamp
        elif candle.high >= t.take:
            t.result = "take"
            t.closed_at = candle.timestamp
