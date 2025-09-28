from __future__ import annotations

from ..domain.services import RiskCalculator
from ...shared.domain.value_objects import RiskReward


class BasicRiskCalculator(RiskCalculator):
    """Basic risk calculator using entry-stop and entry-take profit distances."""

    def calculate(self, entry_price: float, stop_loss: float, take_profit: float) -> RiskReward:
        risk = abs(entry_price - stop_loss)
        reward = abs(take_profit - entry_price)
        return RiskReward(risk=risk, reward=reward)
