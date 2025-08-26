#!/usr/bin/env python
"""Fetch last month's candles and print any price action signals."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List

from hermes_trading.candles import Candle, CandleBatch
from hermes_trading.connectors import BinanceConnector
from hermes_trading.liquidity import LiquidityLevels
from hermes_trading.signals import PriceActionSignal
from hermes_trading.trading import Trade, open_trade, update_trades


def main() -> None:
    symbol = "BTC/USDT"
    timeframe = "1h"
    since = int((datetime.utcnow() - timedelta(days=30)).timestamp() * 1000)

    connector = BinanceConnector()
    ohlcv = connector.client.fetch_ohlcv(symbol, timeframe=timeframe, since=since)
    candles = [Candle(ts, o, h, l, c) for ts, o, h, l, c, *_ in ohlcv]

    signal = PriceActionSignal()
    levels = LiquidityLevels()
    levels.build(candles)
    trades: List[Trade] = []

    for i in range(9, len(candles)):
        current = candles[i]
        update_trades(trades, current)

        batch = CandleBatch(candles[i - 9 : i + 1])
        active_levels = levels.active_levels(current.timestamp)
        results = [r for r in signal.evaluate(batch, active_levels) if r.endswith("@9")]
        for res in results:
            name, _ = res.split("@")
            touched = next(
                lvl for lvl in active_levels if current.low <= lvl.price <= current.high
            )
            trades.append(open_trade(current, name, touched))
        levels.prune(current)

    wins = sum(1 for t in trades if t.result == "take")
    losses = sum(1 for t in trades if t.result == "stop")
    print(f"Profitable trades: {wins}")
    print(f"Losing trades: {losses}")
    print("Signals:")
    for t in trades:
        ts = datetime.fromtimestamp(t.opened_at / 1000, tz=timezone.utc)
        lvl_ts = datetime.fromtimestamp(t.level_start / 1000, tz=timezone.utc)
        print(f"{t.pattern} at {ts.isoformat()} level {t.level_price} from {lvl_ts.isoformat()}")


if __name__ == "__main__":
    main()
