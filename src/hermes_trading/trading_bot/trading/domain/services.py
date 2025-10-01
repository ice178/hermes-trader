from __future__ import annotations

from typing import Protocol

from .entities import Trade


class TradeExecutor(Protocol):
    """Executes trades on an exchange."""

    def open_trade(self, trade: Trade) -> None:
        ...
