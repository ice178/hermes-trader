#!/usr/bin/env python
"""Fetch last month's candles and print any price action signals."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from hermes_trading.candles import Candle, CandleBatch
from hermes_trading.connectors import BinanceConnector
from hermes_trading.signals import PriceActionSignal


def main() -> None:
    symbol = "BTC/USDT"
    timeframe = "1h"
    since = int((datetime.utcnow() - timedelta(days=30)).timestamp() * 1000)

    connector = BinanceConnector()
    ohlcv = connector.client.fetch_ohlcv(symbol, timeframe=timeframe, since=since)
    candles = [Candle(ts, o, h, l, c) for ts, o, h, l, c, *_ in ohlcv]

    signal = PriceActionSignal()
    seen: set[tuple[int, str]] = set()

    for i in range(0, len(candles) - 9):
        batch = CandleBatch(candles[i : i + 10])
        for res in signal.evaluate(batch):
            name, idx = res.split("@")
            candle = batch.candles[int(idx)]
            key = (candle.timestamp, name)
            if key in seen:
                continue
            seen.add(key)
            ts = datetime.fromtimestamp(candle.timestamp / 1000, tz=timezone.utc)
            print(
                f"{name} at {ts.isoformat()} - O:{candle.open} H:{candle.high} L:{candle.low} C:{candle.close}"
            )


if __name__ == "__main__":
    main()
