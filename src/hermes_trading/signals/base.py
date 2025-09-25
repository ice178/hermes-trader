"""Interfaces for trading signals."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Literal, Sequence

from ..candles import Candle, CandleBatch
from ..liquidity import Level


@dataclass(frozen=True)
class SignalMatch:
    """Structured description of a detected trading signal."""

    pattern: str
    direction: Literal["long", "short"]
    candle: Candle
    level: Level


class Signal(ABC):
    """Abstract interface for evaluating trading signals."""

    @abstractmethod
    def evaluate(self, candles: CandleBatch, levels: List[Level]) -> Sequence[SignalMatch]:
        """Return detected signals for the provided candles."""
