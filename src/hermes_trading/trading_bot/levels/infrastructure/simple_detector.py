from __future__ import annotations

from typing import Sequence

from ..domain.entities import Level, LevelType
from ..domain.services import LevelDetector
from ...candles.domain.entities import Candle


class SwingHighLowLevelDetector(LevelDetector):
    """Naive detector using the last candle's extrema as levels."""

    def detect(self, candles: Sequence[Candle]) -> Sequence[Level]:
        if not candles:
            return []
        last = candles[-1]
        return [
            Level(price=last.high, level_type=LevelType.HIGH, candle_timestamp=last.timestamp.isoformat()),
            Level(price=last.low, level_type=LevelType.LOW, candle_timestamp=last.timestamp.isoformat()),
        ]
