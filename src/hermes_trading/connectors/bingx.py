"""Connector for the BingX exchange using CCXT."""

from __future__ import annotations

import ccxt

from .base import ExchangeConnector
from ..candles import Candle, CandleBatch


class BingXConnector(ExchangeConnector):
    """Provides basic market data and order execution for BingX."""

    def __init__(self, api_key: str | None = None, secret: str | None = None):
        self.client = ccxt.bingx({"apiKey": api_key, "secret": secret})

    def get_market_price(self, symbol: str) -> float:
        ticker = self.client.fetch_ticker(symbol)
        return ticker["last"]

    def get_klines(
        self, symbol: str, interval: str, limit: int = 10
    ) -> CandleBatch:
        ohlcv = self.client.fetch_ohlcv(symbol, timeframe=interval, limit=limit)
        candles = [
            Candle(ts, open_, high, low, close)
            for ts, open_, high, low, close, *_ in ohlcv
        ]
        return CandleBatch(candles)

    def place_order(
        self, symbol: str, side: str, amount: float, price: float | None = None
    ) -> dict:
        order_type = "market" if price is None else "limit"
        return self.client.create_order(symbol, order_type, side, amount, price)
