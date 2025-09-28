from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PatternType(str, Enum):
    PIN_BAR = "pin_bar"
    RAILS = "rails"


@dataclass(frozen=True)
class RiskReward:
    risk: float
    reward: float

    def ratio(self) -> float:
        if self.risk == 0:
            raise ValueError("Risk cannot be zero when calculating risk/reward ratio")
        return self.reward / self.risk
