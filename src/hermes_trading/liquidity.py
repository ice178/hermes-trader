"""Utilities for detecting and managing liquidity levels."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

import numpy as np
import pandas as pd

from .candles import Candle


@dataclass
class Level:
    """Represents a liquidity level derived from an extreme candle."""

    price: float
    type: str  # "high" or "low"
    timestamp: int
    active: bool = True


class LiquidityLevels:
    """Builds and maintains a list of liquidity levels."""

    def __init__(self, window: int = 4) -> None:
        self.window = window
        self.levels: List[Level] = []

    def build(self, candles: List[Candle]) -> None:
        """Build initial levels from the provided candles."""
        if not candles:
            return
        df = _candles_to_df(candles)
        highs_idx, lows_idx = [], []
        H, L = df["High"].values, df["Low"].values
        for i in range(self.window, len(df) - self.window):
            if H[i] == np.max(H[i - self.window : i + self.window + 1]):
                highs_idx.append(i)
            if L[i] == np.min(L[i - self.window : i + self.window + 1]):
                lows_idx.append(i)
        levels: List[Level] = []
        for i in highs_idx:
            ts = int(df.index[i].timestamp() * 1000)
            levels.append(Level(price=float(H[i]), type="high", timestamp=ts))
        for i in lows_idx:
            ts = int(df.index[i].timestamp() * 1000)
            levels.append(Level(price=float(L[i]), type="low", timestamp=ts))
        levels.sort(key=lambda x: x.timestamp)
        self.levels = levels

    def active_levels(self, timestamp: int) -> List[Level]:
        """Return all active levels that formed before given timestamp."""
        return [l for l in self.levels if l.active and l.timestamp <= timestamp]

    def prune(self, candle: Candle) -> None:
        """Mark levels as inactive if the candle touches them."""
        for lvl in self.levels:
            if not lvl.active:
                continue
            if candle.low <= lvl.price <= candle.high:
                lvl.active = False


def _candles_to_df(candles: List[Candle]) -> pd.DataFrame:
    data = {
        "Open": [c.open for c in candles],
        "High": [c.high for c in candles],
        "Low": [c.low for c in candles],
        "Close": [c.close for c in candles],
    }
    index = pd.to_datetime([c.timestamp for c in candles], unit="ms", utc=True)
    return pd.DataFrame(data, index=index)
