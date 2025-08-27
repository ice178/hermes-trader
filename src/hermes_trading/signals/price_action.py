"""Price action pattern based trading signals."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from ..candles import Candle, CandleBatch
from ..liquidity import Level
from .base import Signal


@dataclass
class PriceActionSignal(Signal):
    """Detects price action patterns within a batch of candles."""

    def evaluate(self, candles: CandleBatch, levels: List[Level]) -> List[str]:  # type: ignore[override]
        """Return patterns that occur on provided liquidity levels."""

        signals: List[str] = []
        bars = candles.candles
        for i, bar in enumerate(bars):
            if not any(
                lvl.active and lvl.timestamp < bar.timestamp and bar.low <= lvl.price <= bar.high
                for lvl in levels
            ):
                continue
            if self._is_pin_bar(bar):
                signals.append(f"pin_bar@{i}")
            if i > 0 and self._is_bullish_engulfing(bars[i - 1], bar):
                signals.append(f"bullish_engulfing@{i}")
        return signals

    @staticmethod
    def _is_bullish_engulfing(prev: Candle, curr: Candle) -> bool:
        return (
            prev.close < prev.open
            and curr.close > curr.open
            and curr.close > prev.open
            and curr.open < prev.close
        )

    @staticmethod
    def _is_pin_bar(c: Candle) -> bool:
        body = abs(c.close - c.open)
        rng = c.high - c.low
        tail = min(c.open, c.close) - c.low
        head = c.high - max(c.open, c.close)
        return body < rng * 0.3 and tail > body * 2
