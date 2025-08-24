"""Abstract base class for exchange connectors."""

from abc import ABC, abstractmethod
from typing import Any


class ExchangeConnector(ABC):
    """Defines the common interface for all exchange connectors."""

    @abstractmethod
    def get_market_price(self, symbol: str) -> float:
        """Return the latest market price for a trading pair."""

    @abstractmethod
    def place_order(
        self, symbol: str, side: str, amount: float, price: float | None = None
    ) -> Any:
        """Place an order and return the exchange response."""
