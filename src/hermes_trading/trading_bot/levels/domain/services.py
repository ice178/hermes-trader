from __future__ import annotations

from typing import Protocol, Sequence

from ..candles.domain.entities import Candle
from .entities import Level


class LevelDetector(Protocol):
    """Detects liquidity levels from candle history."""

    def detect(self, candles: Sequence[Candle]) -> Sequence[Level]:
        ...
