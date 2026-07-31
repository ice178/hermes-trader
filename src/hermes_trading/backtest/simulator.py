"""Trade simulation for signal-driven backtests."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field

from .models import SignalEvent, StrategyConfig, TradeRecord
from ..candles import Candle
from ..trading import calculate_risk_distance


@dataclass
class _TradeState:
    event: SignalEvent
    entry_index: int
    entry_candle: Candle
    entry_price: float
    stop_price: float
    take_profit_price: float | None
    risk_per_unit: float
    best_price_reached: float
    worst_price_reached: float
    mfe_abs: float = 0.0
    mae_abs: float = 0.0
    best_take_step_r: float = 0.0
    time_to_best_take_step_bars: int | None = None
    time_to_best_take_step_ms: int | None = None
    r_step_hit_times: dict[str, dict[str, int]] = field(default_factory=dict)
    same_direction_signal_count: int = 0
    opposite_direction_signal_count: int = 0
    same_direction_signal_timestamps: list[int] = field(default_factory=list)
    opposite_direction_signal_timestamps: list[int] = field(default_factory=list)
    intrabar_conflict_count: int = 0
    intrabar_conflict_timestamps: list[int] = field(default_factory=list)


def _format_r_step(value: float) -> str:
    return f"{value:.2f}R"


def _floor_to_step(value: float, step: float) -> float:
    if step <= 0:
        raise ValueError("take_step_r must be positive")
    return round(math.floor((value + 1e-9) / step) * step, 10)


def _pnl_abs(direction: str, entry_price: float, exit_price: float) -> float:
    if direction == "long":
        return exit_price - entry_price
    return entry_price - exit_price


def _favorable_abs(direction: str, entry_price: float, candle: Candle) -> float:
    if direction == "long":
        return max(candle.high - entry_price, 0.0)
    return max(entry_price - candle.low, 0.0)


def _adverse_abs(direction: str, entry_price: float, candle: Candle) -> float:
    if direction == "long":
        return max(entry_price - candle.low, 0.0)
    return max(candle.high - entry_price, 0.0)


def _stop_hit(direction: str, stop_price: float, candle: Candle) -> bool:
    if direction == "long":
        return candle.low <= stop_price
    return candle.high >= stop_price


def _take_profit_hit(
    direction: str,
    take_profit_price: float | None,
    candle: Candle,
) -> bool:
    if take_profit_price is None:
        return False
    if direction == "long":
        return candle.high >= take_profit_price
    return candle.low <= take_profit_price


def _classify_result(pnl_r: float) -> str:
    if pnl_r > 0:
        return "win"
    if pnl_r < 0:
        return "loss"
    return "breakeven"


def _record_r_steps(
    state: _TradeState,
    candle: Candle,
    candle_index: int,
    strategy: StrategyConfig,
    candidate_step_r: float,
) -> None:
    next_step = round(state.best_take_step_r + strategy.take_step_r, 10)
    while next_step <= candidate_step_r + 1e-9:
        key = _format_r_step(next_step)
        bars_elapsed = candle_index - state.entry_index
        milliseconds = candle.timestamp - state.entry_candle.timestamp
        state.r_step_hit_times[key] = {
            "bars": bars_elapsed,
            "milliseconds": milliseconds,
            "timestamp": candle.timestamp,
        }
        state.best_take_step_r = next_step
        state.time_to_best_take_step_bars = bars_elapsed
        state.time_to_best_take_step_ms = milliseconds
        next_step = round(next_step + strategy.take_step_r, 10)


def _register_internal_signal(state: _TradeState, event: SignalEvent) -> None:
    if event.direction == state.event.direction:
        state.same_direction_signal_count += 1
        state.same_direction_signal_timestamps.append(event.signal_candle.timestamp)
        return

    state.opposite_direction_signal_count += 1
    state.opposite_direction_signal_timestamps.append(event.signal_candle.timestamp)


def _finalize_trade(
    state: _TradeState,
    exit_candle: Candle,
    exit_index: int,
    *,
    exit_price: float,
    exit_reason: str,
) -> TradeRecord:
    pnl_abs = _pnl_abs(state.event.direction, state.entry_price, exit_price)
    pnl_pct = (pnl_abs / state.entry_price) * 100 if state.entry_price else 0.0
    pnl_r = pnl_abs / state.risk_per_unit if state.risk_per_unit else 0.0
    mae_pct = (state.mae_abs / state.entry_price) * 100 if state.entry_price else 0.0
    mfe_pct = (state.mfe_abs / state.entry_price) * 100 if state.entry_price else 0.0

    return TradeRecord(
        symbol=state.event.symbol,
        timeframe=state.event.timeframe,
        pattern=state.event.pattern,
        direction=state.event.direction,
        signal_timestamp=state.event.signal_candle.timestamp,
        signal_datetime=state.event.signal_candle.datetime,
        entry_timestamp=state.entry_candle.timestamp,
        entry_datetime=state.entry_candle.datetime,
        exit_timestamp=exit_candle.timestamp,
        exit_datetime=exit_candle.datetime,
        entry_price=state.entry_price,
        stop_price=state.stop_price,
        take_profit_price=state.take_profit_price,
        exit_price=exit_price,
        risk_per_unit=state.risk_per_unit,
        result=_classify_result(pnl_r),
        exit_reason=exit_reason,
        bars_in_trade=(exit_index - state.entry_index) + 1,
        pnl_abs=pnl_abs,
        pnl_pct=pnl_pct,
        pnl_r=pnl_r,
        mae_abs=state.mae_abs,
        mae_pct=mae_pct,
        mae_r=(state.mae_abs / state.risk_per_unit) if state.risk_per_unit else 0.0,
        mfe_abs=state.mfe_abs,
        mfe_pct=mfe_pct,
        mfe_r=(state.mfe_abs / state.risk_per_unit) if state.risk_per_unit else 0.0,
        best_take_step_r=state.best_take_step_r,
        time_to_best_take_step_bars=state.time_to_best_take_step_bars,
        time_to_best_take_step_ms=state.time_to_best_take_step_ms,
        r_step_hit_times=state.r_step_hit_times,
        same_direction_signal_count=state.same_direction_signal_count,
        opposite_direction_signal_count=state.opposite_direction_signal_count,
        same_direction_signal_timestamps=state.same_direction_signal_timestamps,
        opposite_direction_signal_timestamps=state.opposite_direction_signal_timestamps,
        intrabar_conflict_count=state.intrabar_conflict_count,
        intrabar_conflict_timestamps=state.intrabar_conflict_timestamps,
        best_price_reached=state.best_price_reached,
        worst_price_reached=state.worst_price_reached,
    )


def _open_trade_state(
    event: SignalEvent,
    entry_candle: Candle,
    entry_index: int,
    strategy: StrategyConfig,
) -> _TradeState | None:
    risk_distance = calculate_risk_distance(
        event.signal_candle,
        event.pattern,
        event.direction,
    )
    if risk_distance <= 0:
        return None

    if event.direction == "long":
        stop_price = entry_candle.open - risk_distance
        take_profit_price = (
            entry_candle.open + (risk_distance * strategy.take_profit_r)
            if strategy.take_profit_r is not None
            else None
        )
    else:
        stop_price = entry_candle.open + risk_distance
        take_profit_price = (
            entry_candle.open - (risk_distance * strategy.take_profit_r)
            if strategy.take_profit_r is not None
            else None
        )

    return _TradeState(
        event=event,
        entry_index=entry_index,
        entry_candle=entry_candle,
        entry_price=entry_candle.open,
        stop_price=stop_price,
        take_profit_price=take_profit_price,
        risk_per_unit=risk_distance,
        best_price_reached=entry_candle.open,
        worst_price_reached=entry_candle.open,
    )


def _update_trade_state(
    state: _TradeState,
    candle: Candle,
    candle_index: int,
    strategy: StrategyConfig,
) -> TradeRecord | None:
    state.mfe_abs = max(
        state.mfe_abs,
        _favorable_abs(state.event.direction, state.entry_price, candle),
    )
    state.best_price_reached = (
        max(state.best_price_reached, candle.high)
        if state.event.direction == "long"
        else min(state.best_price_reached, candle.low)
    )
    state.worst_price_reached = (
        min(state.worst_price_reached, candle.low)
        if state.event.direction == "long"
        else max(state.worst_price_reached, candle.high)
    )

    stop_hit = _stop_hit(state.event.direction, state.stop_price, candle)
    take_profit_hit = _take_profit_hit(
        state.event.direction,
        state.take_profit_price,
        candle,
    )
    adverse_abs = _adverse_abs(state.event.direction, state.entry_price, candle)
    state.mae_abs = max(
        state.mae_abs,
        min(adverse_abs, state.risk_per_unit) if stop_hit else adverse_abs,
    )

    candidate_step_r = _floor_to_step(
        state.mfe_abs / state.risk_per_unit if state.risk_per_unit else 0.0,
        strategy.take_step_r,
    )
    has_new_step = candidate_step_r > state.best_take_step_r

    if stop_hit and take_profit_hit:
        state.intrabar_conflict_count += 1
        state.intrabar_conflict_timestamps.append(candle.timestamp)
        return _finalize_trade(
            state,
            candle,
            candle_index,
            exit_price=state.stop_price,
            exit_reason="stop_loss",
        )

    if stop_hit and has_new_step:
        state.intrabar_conflict_count += 1
        state.intrabar_conflict_timestamps.append(candle.timestamp)
    elif has_new_step:
        _record_r_steps(state, candle, candle_index, strategy, candidate_step_r)

    if take_profit_hit and state.take_profit_price is not None:
        take_step_r = candidate_step_r
        if strategy.take_profit_r is not None:
            take_step_r = min(
                take_step_r,
                _floor_to_step(strategy.take_profit_r, strategy.take_step_r),
            )
        if take_step_r > state.best_take_step_r:
            _record_r_steps(state, candle, candle_index, strategy, take_step_r)
        return _finalize_trade(
            state,
            candle,
            candle_index,
            exit_price=state.take_profit_price,
            exit_reason="take_profit",
        )

    if stop_hit:
        return _finalize_trade(
            state,
            candle,
            candle_index,
            exit_price=state.stop_price,
            exit_reason="stop_loss",
        )

    return None


def simulate_candles(
    candles: list[Candle],
    signal_events: list[SignalEvent],
    strategy: StrategyConfig,
) -> list[TradeRecord]:
    """Simulate trades for a single symbol/timeframe candle stream."""

    if not candles:
        return []

    events_by_timestamp: dict[int, list[SignalEvent]] = defaultdict(list)
    for event in sorted(signal_events, key=lambda current: current.signal_candle.timestamp):
        events_by_timestamp[event.signal_candle.timestamp].append(event)

    trades: list[TradeRecord] = []
    open_trade: _TradeState | None = None

    for candle_index, candle in enumerate(candles):
        if open_trade is not None and candle_index >= open_trade.entry_index:
            finished_trade = _update_trade_state(open_trade, candle, candle_index, strategy)
            if finished_trade is not None:
                trades.append(finished_trade)
                open_trade = None

        for event in events_by_timestamp.get(candle.timestamp, []):
            if event.direction not in strategy.direction_filter:
                continue

            if open_trade is not None and candle.timestamp >= open_trade.entry_candle.timestamp:
                if strategy.track_internal_signals:
                    _register_internal_signal(open_trade, event)
                continue

            if open_trade is not None:
                continue

            if candle_index + 1 >= len(candles):
                continue

            open_trade = _open_trade_state(
                event,
                candles[candle_index + 1],
                candle_index + 1,
                strategy,
            )
            if open_trade is not None and strategy.one_trade_per_symbol_timeframe:
                break

    if open_trade is not None:
        last_index = len(candles) - 1
        trades.append(
            _finalize_trade(
                open_trade,
                candles[last_index],
                last_index,
                exit_price=candles[last_index].close,
                exit_reason="end_of_data",
            )
        )

    return trades
