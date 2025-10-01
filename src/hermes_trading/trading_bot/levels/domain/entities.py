from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class LevelType(str, Enum):
    HIGH = "high"
    LOW = "low"


class LevelStatus(str, Enum):
    ACTIVE = "active"
    TAKEN = "taken"


@dataclass(frozen=True)
class Level:
    price: float
    level_type: LevelType
    status: LevelStatus = LevelStatus.ACTIVE
    candle_timestamp: Optional[str] = None
