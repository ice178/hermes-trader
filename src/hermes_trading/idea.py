from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1
from typing import Literal

from .candles import Candle


@dataclass(frozen=True)
class Idea:
    symbol: str
    timeframe: str
    pattern: str
    side: Literal["long", "short"]
    signal_candle_time: str
    level_price: float
    level_weight: float
    level_timestamp: int
    candle: Candle
    rounded_level_price: float


def round_level_price(price: float, *, tick_size: float | None, decimals: int | None) -> float:
    if tick_size:
        if tick_size == 0:
            return price
        return round(price / tick_size) * tick_size
    if decimals is not None:
        return round(price, decimals)
    return price


def generate_idea_id(idea: Idea) -> str:
    raw = "|".join(
        [
            idea.symbol,
            idea.timeframe,
            idea.pattern,
            idea.side,
            idea.signal_candle_time,
            str(idea.rounded_level_price),
        ]
    )
    return sha1(raw.encode("utf-8")).hexdigest()
