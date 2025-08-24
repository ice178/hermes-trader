"""Interfaces for trading signals."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence

from ..candles import CandleBatch


class Signal(ABC):
    """Abstract interface for evaluating trading signals."""

    @abstractmethod
    def evaluate(self, candles: CandleBatch) -> Sequence[str]:
        """Return detected signals for the provided candles."""
