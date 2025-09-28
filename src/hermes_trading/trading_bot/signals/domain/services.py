from __future__ import annotations

from typing import Protocol, Sequence

from ...candles.domain.entities import Candle
from ...levels.domain.entities import Level
from ...shared.domain.value_objects import RiskReward
from .entities import Signal


class SignalDetector(Protocol):
    """Identifies price action signals based on candles and levels."""

    def detect(self, candles: Sequence[Candle], levels: Sequence[Level]) -> Sequence[Signal]:
        ...


class RiskCalculator(Protocol):
    """Calculates risk-reward for signals."""

    def calculate(self, entry_price: float, stop_loss: float, take_profit: float) -> RiskReward:
        ...
