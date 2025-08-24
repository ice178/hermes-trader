"""Signal evaluation for trading strategies."""

from .base import Signal
from .price_action import PriceActionSignal

__all__ = ["Signal", "PriceActionSignal"]
