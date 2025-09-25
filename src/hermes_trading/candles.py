from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class Candle:
    """Represents a single OHLCV candle."""

    timestamp: int
    datetime: str
    open: float
    high: float
    low: float
    close: float


@dataclass
class CandleBatch:
    """Container for exactly ten sequential candles."""

    candles: List[Candle]

    def __post_init__(self) -> None:
        if len(self.candles) != 10:
            raise ValueError("CandleBatch must contain exactly 10 candles")
