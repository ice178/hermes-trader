"""Interfaces for trading signals."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence


class Signal(ABC):
    """Abstract interface for evaluating trading signals."""

    @abstractmethod
    def evaluate(self, prices: Sequence[float]) -> bool:
        """Return ``True`` if a signal is triggered for the given prices."""
