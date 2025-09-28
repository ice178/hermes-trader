from __future__ import annotations

from typing import Iterable, Protocol, Sequence

from .entities import Candle


class CandleRepository(Protocol):
    """Abstract storage for candles."""

    def add(self, candle: Candle) -> None:
        """Persist a single candle."""

    def list(self, limit: int | None = None) -> Sequence[Candle]:
        """Return candles ordered by timestamp ascending."""

    def extend(self, candles: Iterable[Candle]) -> None:
        for candle in candles:
            self.add(candle)
