from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class TradeSide(str, Enum):
    LONG = "long"
    SHORT = "short"


@dataclass(frozen=True)
class Trade:
    symbol: str
    side: TradeSide
    size: float
    entry_price: float
    stop_loss: float
    take_profit: float
    opened_at: datetime
    signal_id: Optional[int] = None
