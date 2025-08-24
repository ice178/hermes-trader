"""Abstract base class for exchange connectors."""

from abc import ABC, abstractmethod
from typing import Any

from ..candles import CandleBatch


class ExchangeConnector(ABC):
    """Defines the common interface for all exchange connectors."""

    @abstractmethod
    def get_market_price(self, symbol: str) -> float:
        """Return the latest market price for a trading pair."""

    @abstractmethod
    def get_klines(
        self, symbol: str, interval: str, limit: int = 10
    ) -> CandleBatch:
        """Return a batch of ``limit`` candles for ``symbol``."""

    @abstractmethod
    def place_order(
        self, symbol: str, side: str, amount: float, price: float | None = None
    ) -> Any:
        """Place an order and return the exchange response."""
