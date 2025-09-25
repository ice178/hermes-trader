#!/usr/bin/env python
"""Fetch last month's candles and print any price action signals."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from operator import truediv
from typing import List

from hermes_trading.candles import Candle, CandleBatch
from hermes_trading.connectors import BinanceConnector
from hermes_trading.connectors import BingXConnector
from hermes_trading.liquidity import LiquidityLevels
from hermes_trading.signals import PriceActionSignal
from hermes_trading.trading import Trade, open_trade, update_trades, is_open_trade_exists

import json


def main() -> None:
    profit = 0
    lose = 0
    opened = 0
    stop_moved = 0
    data = []
    # for symbol in ["BTC/USDT","ETH/USDT"]:
    #, "XRP/USDT", "LTC/USDT"]:
    for symbol in ["BTC/USDT"]:
        timeframe = "1h"
        # since = int((datetime.now(tz=timezone.utc) - timedelta(days=365)).timestamp() * 1000)
        since = int(datetime.fromisoformat('2024-10-15T00:00:00.000000+00:00').timestamp() * 1000)
        # since = int(datetime.fromisoformat('2025-08-28T00:00:00.000000+00:00').timestamp() * 1000)
        limit = 1201
        # limit = None

        # connector = BinanceConnector()
        connector = BingXConnector()
        ohlcv = connector.client.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=limit, params={"paginate": True})
        candles = [
            Candle(
                timestamp=ts,
                datetime=datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat(),
                open=o,
                high=h,
                low=l,
                close=c,
            )
            for ts, o, h, l, c, *_ in ohlcv
        ]

        signal = PriceActionSignal()
        levels = LiquidityLevels()
        levels.build(candles)
        trades: List[Trade] = []

        for i in range(9, len(candles)):
            current = candles[i]
            update_trades(trades, current)

            if is_open_trade_exists(trades):
                continue

            batch = CandleBatch(candles[i - 9 : i + 1])
            active_levels = levels.active_levels(current.timestamp)

            results = [
                match
                for match in signal.evaluate(batch, active_levels)
                if match.candle.timestamp == current.timestamp
            ]
            for match in results:
                trades.append(
                    open_trade(
                        match.candle,
                        match.pattern,
                        match.level,
                        symbol,
                        match.direction,
                    )
                )
            levels.prune(current)

        wins = sum(1 for t in trades if t.result == "take")
        losses = sum(1 for t in trades if t.result == "stop" and t.stop_is_moved == False)
        sm = sum(1 for t in trades if t.result == "stop" and t.stop_is_moved == True)
        o = sum(1 for t in trades if t.result is None)

        profit += wins
        lose += losses
        opened += o
        stop_moved += sm

        print(f"Symbol: {symbol}")
        print(f"Profitable trades: {wins}")
        print(f"Losing trades: {losses}")
        print(f"Stop is moved: {sm}")
        print("Signals:")
        for t in trades:
            data.append({
                "symbol": symbol,
                "type": "buy" if t.direction == "long" else "sell",
                "pattern": t.pattern,
                "opened_at": datetime.fromtimestamp(t.opened_at / 1000, tz=timezone.utc).isoformat(),
                "closed_at": None if t.result is None else t.take_candle.datetime if t.result == "take" else t.stop_candle.datetime,
                "open_price": t.open_candle.close,
                "take_price": t.take,
                "stop_price": t.stop,
                "is_successful": t.result == "take",
                "level_from": datetime.fromtimestamp(t.level_start / 1000, tz=timezone.utc).isoformat(),
                "level_price": t.level_price,
                "open_candle_price_open": t.open_candle.open,
                "open_candle_price_close": t.open_candle.close,
                "open_candle_price_high": t.open_candle.high,
                "open_candle_price_low": t.open_candle.low,
            })
            if t.stop_price is not None:
                ts = datetime.fromtimestamp(t.opened_at / 1000, tz=timezone.utc)
                lvl_ts = datetime.fromtimestamp(t.level_start / 1000, tz=timezone.utc)
                # print(f"{t.result} {t.pattern} at {ts.isoformat()} level {t.level_price} from {lvl_ts.isoformat()}")
                # print(t.stop, t.stop_price, t.stop - t.stop_price, t.entry, t.take)

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print()
    print(f"Profitable trades: {profit}")
    print(f"Losing trades: {lose}")
    print(f"Stop is moved: {stop_moved}")
    print(f"Opened trades: {opened}")

    depo = 1000
    initial_depo = 1000
    risk1 = 50

    # sorted_data = sorted(
    #     data,
    #     key=lambda x: datetime.fromisoformat(x["closed_at"].replace("Z", "+00:00"))
    # )

    sorted_data = data

    for item in sorted_data:
        if depo >= initial_depo * 1.2:
            risk1 = risk1 * 1.2
            initial_depo = depo

        if item["is_successful"]:
            depo += risk1 * 2
        else:
            depo -= risk1

    risk = 50
    total_sum = profit * 50 * 2 + stop_moved * risk * 1 - lose * risk

    income = depo - 1000

    print(f"Income: {total_sum} USD")
    print(f"Income with raising: {income} USD")
    print("risk is ", risk1)


    cnt = 0

    # for l in levels.levels:
    #     print(l.datetime, l.price, l.type)
    #     cnt += 1
    #
    # print("Levels count is ", cnt)

if __name__ == "__main__":
    main()

# risk - 50
# 1 on 1    50 5  - 2250
# 1 on 1.5  47 7  - 3175
# 1 on 1.75 45 8  - 3573.5
# 1 on 2    44 8  - 4000
# 1 on 3    42 10 - 5800
