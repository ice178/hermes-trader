#!/usr/bin/env python
"""Fetch last month's candles and print any price action signals."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from operator import truediv
from pathlib import Path
from typing import List

from hermes_trading.candles import Candle, CandleBatch
from hermes_trading.connectors import BinanceConnector
from hermes_trading.connectors import BingXConnector
from hermes_trading.liquidity import LiquidityLevels
from hermes_trading.signals import PriceActionSignal
from hermes_trading.execution import (
    build_base_trade_plan,
    compute_mfe_mae,
    create_execution_state,
    isoformat_utc,
    update_execution_state,
)
from hermes_trading.features import compute_entry_features
from hermes_trading.filters import apply_pin_bar_sell_filters
from hermes_trading.idea import Idea, generate_idea_id, round_level_price
from hermes_trading.strategy_config import load_strategy_config
from hermes_trading.trade_store import TradeStore
from hermes_trading.trading import Trade, open_trade, update_trades, is_open_trade_exists

import json


def main() -> None:
    profit = 0
    lose = 0
    opened = 0
    stop_moved = 0
    data = []
    candlesRaw = []
    # for symbol in ["BTC/USDT"]:
    base_dir = Path(__file__).resolve().parents[1]
    config_path = base_dir / "config" / "strategy.json"
    config = load_strategy_config(config_path)
    strategy = config["strategy"]
    research_mode = strategy.get("research_mode", False)
    executions_enabled = strategy.get("executions_enabled", ["BASE_RR1"])

    trade_store = TradeStore(base_dir / "trade_records.json" if research_mode else None)

    for symbol in ["BTC/USDT","ETH/USDT","BNB/USDT"]:
    # for symbol in ["BTC/USDT","ETH/USDT","XRP/USDT","LTC/USDT"]:
        timeframe = strategy.get("timeframe", "1h")
        # since = int((datetime.now(tz=timezone.utc) - timedelta(days=365)).timestamp() * 1000)
        # since = int(datetime.fromisoformat('2024-10-15T00:00:00.000000+00:00').timestamp() * 1000)
        # since = int(datetime.fromisoformat('2025-09-01T00:00:00.000000+00:00').timestamp() * 1000)
        since = int(datetime.fromisoformat('2025-01-01T00:00:00.000000+00:00').timestamp() * 1000)
        limit = None
        # limit = 720

        connector = BinanceConnector()
        # connector = BingXConnector()
        ohlcv = connector.client.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=limit, params={"paginate": True})
        candles = [
            Candle(
                timestamp=ts,
                datetime=datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat(),
                open=o,
                high=h,
                low=l,
                close=c,
                volume=v
            )
            for ts, o, h, l, c, v in ohlcv
        ]

        for ts, o, h, l, c, v in ohlcv:
            candlesRaw.append({
                "datetime": datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat(),
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": v
            })

        with (base_dir / "candles2.json").open("w+", encoding="utf-8") as f:
            json.dump(candlesRaw, f, ensure_ascii=False, indent=2)


        signal = PriceActionSignal()
        levels = LiquidityLevels()
        levels.build(candles)
        trades: List[Trade] = []
        execution_states = []

        levels_raw = []

        for level in levels.levels:
            levels_raw.append({
                "datetime": level.datetime,
                "price": level.price,
                "type": level.type
            })

        # with open("levels.json", "w+", encoding="utf-8") as f:
        #     json.dump(levels_raw, f, ensure_ascii=False, indent=2)


        for i in range(9, len(candles)):
            current = candles[i]
            update_trades(trades, current)

            for state in execution_states:
                update_execution_state(
                    state,
                    current,
                    i,
                    execution_params=strategy.get("execution_params", {}),
                )

            if is_open_trade_exists(trades) or any(not s.is_closed() for s in execution_states):
                continue

            batch = CandleBatch(candles[i - 9 : i + 1])
            active_levels = levels.active_levels(current.timestamp)

            results = [
                match
                for match in signal.evaluate(batch, active_levels)
                if match.candle.timestamp == current.timestamp
            ]

            # if len(results) > 1:
            #     print(results)
            #     print("\n")

            for match in results:
                candle_date_time = datetime.fromtimestamp(match.candle.timestamp / 1000,tz=timezone.utc)
                if candle_date_time.weekday() >= 5:
                    continue

                if match.level.weight == 0.5:
                    continue

                if match.pattern == "pin_bar" and match.direction == "long":
                    continue

                if match.pattern == "pin_bar" and match.direction == "short" and match.level.weight == 1:
                    continue

                if not research_mode:
                    trades.append(
                        open_trade(
                            match.candle,
                            match.pattern,
                            match.level,
                            symbol,
                            match.direction,
                        )
                    )
                    break

                rounding = strategy.get("level_price_rounding", {})
                rounded_level = round_level_price(
                    match.level.price,
                    tick_size=rounding.get("tick_size"),
                    decimals=rounding.get("decimals"),
                )
                idea = Idea(
                    symbol=symbol,
                    timeframe=timeframe,
                    pattern=match.pattern,
                    side=match.direction,
                    signal_candle_time=match.candle.datetime,
                    level_price=match.level.price,
                    level_weight=match.level.weight,
                    level_timestamp=match.level.timestamp,
                    candle=match.candle,
                    rounded_level_price=rounded_level,
                )
                idea_id = generate_idea_id(idea)

                plan = build_base_trade_plan(idea)
                filters_config = strategy.get("filters", {}).get("pin_bar_sell", {})
                missing_indicator_policy = strategy.get("missing_indicator_policy", "skip")
                entry_features = compute_entry_features(
                    candles=candles,
                    index=i,
                    entry_price=plan.entry_price,
                    stop_loss=plan.stop_loss,
                    take_profit=plan.take_profit,
                    level_price=idea.level_price,
                    side=idea.side,
                    ema200_near_atr=filters_config.get("ema200_near_atr", 0.1),
                )

                filter_passed = True
                reject_reasons: list[str] = []
                if (
                    match.pattern == "pin_bar"
                    and match.direction == "short"
                    and filters_config.get("enabled", False)
                ):
                    filter_passed, reject_reasons = apply_pin_bar_sell_filters(
                        entry_features,
                        config=filters_config,
                        missing_indicator_policy=missing_indicator_policy,
                    )

                if not filter_passed:
                    continue

                for variant in executions_enabled:
                    if trade_store.has_record(idea_id, variant):
                        continue
                    state = create_execution_state(
                        idea,
                        idea_id,
                        plan,
                        variant,
                        execution_params=strategy.get("execution_params", {}),
                    )
                    state.filter_passed = filter_passed
                    state.filter_reject_reason = reject_reasons
                    state.entry_features = entry_features
                    execution_states.append(state)

                break

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
                "profit": t.profit,
                "losses": t.losses,
                "is_successful": t.result == "take",
                "level_from": datetime.fromtimestamp(t.level_start / 1000, tz=timezone.utc).isoformat(),
                "level_price": t.level_price,
                "level_weight": t.level.weight,
                "open_candle_price_open": t.open_candle.open,
                "open_candle_price_close": t.open_candle.close,
                "open_candle_price_high": t.open_candle.high,
                "open_candle_price_low": t.open_candle.low,
                "comment": "",
            })
            if t.stop_price is not None:
                ts = datetime.fromtimestamp(t.opened_at / 1000, tz=timezone.utc)
                lvl_ts = datetime.fromtimestamp(t.level_start / 1000, tz=timezone.utc)
                # print(f"{t.result} {t.pattern} at {ts.isoformat()} level {t.level_price} from {lvl_ts.isoformat()}")
                # print(t.stop, t.stop_price, t.stop - t.stop_price, t.entry, t.take)

    if not research_mode:
        with (base_dir / "data.json").open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        if research_mode:
            for state in execution_states:
                if state.open_index is None or state.open_index < 0:
                    continue
                close_index = state.close_index if state.close_index is not None else len(candles) - 1
                mfe_mae = compute_mfe_mae(
                    candles=candles,
                    open_index=state.open_index,
                    close_index=close_index,
                    entry_price=state.entry_price,
                    risk=state.risk,
                    side=state.idea.side,
                )
                entry_features = state.entry_features
                commission_config = strategy.get("commissions", {})
                commission = None
                slippage = None
                commission_r = None
                slippage_r = None
                if commission_config.get("enabled", False):
                    rate = commission_config.get("rate", 0.0)
                    commission = rate * state.entry_price
                    if state.risk:
                        commission_r = commission / state.risk
                    slippage_ticks = commission_config.get("slippage_ticks", 0)
                    tick_size = strategy.get("level_price_rounding", {}).get("tick_size", 0) or 0
                    slippage = slippage_ticks * tick_size
                    if state.risk:
                        slippage_r = slippage / state.risk

                record = {
                    "symbol": state.idea.symbol,
                    "timeframe": state.idea.timeframe,
                    "pattern": state.idea.pattern,
                    "side": state.idea.side,
                    "signal_candle_time": state.idea.signal_candle_time,
                    "idea_id": state.idea_id,
                    "execution_variant": state.execution_variant,
                    "execution_id": state.execution_id,
                    "is_live": False,
                    "filter_passed": state.filter_passed,
                    "filter_reject_reason": state.filter_reject_reason,
                    "risk_R": 1.0,
                    "tp_R": state.tp_r,
                    "realized_R": state.realized_r,
                    "exit_reason": state.exit_reason or "unknown",
                    "bars_in_trade": (close_index - state.open_index + 1) if state.open_index is not None else None,
                    "duration_seconds": (
                        (candles[close_index].timestamp - state.opened_at) // 1000
                        if state.open_index is not None
                        else None
                    ),
                    "commission": commission,
                    "slippage": slippage,
                    "commission_R": commission_r,
                    "slippage_R": slippage_r,
                    "mfe_price": mfe_mae["mfe_price"],
                    "mae_price": mfe_mae["mae_price"],
                    "mfe_R": mfe_mae["mfe_R"],
                    "mae_R": mfe_mae["mae_R"],
                    "reached_0_3R": mfe_mae["reached_0_3R"],
                    "reached_0_5R": mfe_mae["reached_0_5R"],
                    "reached_1R": mfe_mae["reached_1R"],
                    "time_to_0_3R_bars": mfe_mae["time_to_0_3R_bars"],
                    "time_to_0_5R_bars": mfe_mae["time_to_0_5R_bars"],
                    "time_to_1R_bars": mfe_mae["time_to_1R_bars"],
                    "atr14": entry_features.atr14,
                    "ema200": entry_features.ema200,
                    "ema200_side": entry_features.ema200_side,
                    "sl_in_atr": entry_features.sl_in_atr,
                    "tp_in_atr": entry_features.tp_in_atr,
                    "distance_to_level_atr": entry_features.distance_to_level_atr,
                    "hour_utc": entry_features.hour_utc,
                    "session": entry_features.session,
                    "candle_range": entry_features.candle_range,
                    "body_size": entry_features.body_size,
                    "upper_wick": entry_features.upper_wick,
                    "lower_wick": entry_features.lower_wick,
                    "wick_ratio": entry_features.wick_ratio,
                    "close_location": entry_features.close_location,
                    "touched_level": entry_features.touched_level,
                    "reclaimed_level": entry_features.reclaimed_level,
                    "sweep_size_atr": entry_features.sweep_size_atr,
                    "entry_price": state.entry_price,
                    "stop_loss": state.stop_loss,
                    "take_profit": state.take_profit,
                    "opened_at": isoformat_utc(state.opened_at),
                    "closed_at": isoformat_utc(candles[close_index].timestamp),
                }
                trade_store.add_record(record)

    if research_mode:
        trade_store.save()

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

    profit_total = 0

    for item in sorted_data:
        if item["is_successful"]:
            profit_total += item["profit"]
        else:
            profit_total -= item["losses"]

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

    print()
    print(f"Profit total: {profit_total} USD")
    print()


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
