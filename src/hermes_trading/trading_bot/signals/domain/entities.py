from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ...levels.domain.entities import Level
from ...shared.domain.value_objects import PatternType, RiskReward


@dataclass(frozen=True)
class Signal:
    pattern: PatternType
    level: Level
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_reward: RiskReward
    detected_at: datetime
    symbol: Optional[str] = None
