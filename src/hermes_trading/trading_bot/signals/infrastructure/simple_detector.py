from __future__ import annotations

from typing import Sequence

from ..domain.entities import Signal
from ..domain.services import RiskCalculator, SignalDetector
from ...candles.domain.entities import Candle
from ...levels.domain.entities import Level


class PriceActionSignalDetector(SignalDetector):
    """Placeholder detector returning no signals."""

    def __init__(self, risk_calculator: RiskCalculator) -> None:
        self._risk_calculator = risk_calculator

    def detect(self, candles: Sequence[Candle], levels: Sequence[Level]) -> Sequence[Signal]:
        # TODO: Implement real Price Action logic.
        return []
