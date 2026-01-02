from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from .candles import Candle
from .idea import Idea


@dataclass(frozen=True)
class BaseTradePlan:
    entry_price: float
    stop_loss: float
    take_profit: float
    risk: float
    tp_r: float


@dataclass
class ExecutionState:
    idea: Idea
    idea_id: str
    execution_variant: str
    execution_id: str
    entry_price: float
    stop_loss: float
    take_profit: float | None
    risk: float
    opened_at: int
    open_index: int
    closed_at: int | None = None
    close_index: int | None = None
    exit_reason: str | None = None
    realized_r: float | None = None
    stop_moved: bool = False
    reached_0_3r: bool = False
    tp1_price: float | None = None
    tp2_price: float | None = None
    tp1_size: float | None = None
    tp2_size: float | None = None
    remaining_size: float = 1.0
    tp1_hit: bool = False
    filter_passed: bool = True
    filter_reject_reason: list[str] | None = None
    entry_features: object | None = None
    tp_r: float | None = None

    def is_closed(self) -> bool:
        return self.closed_at is not None


def _risk_multiplicator(level_weight: float) -> int:
    return 2 if level_weight == 1.0 else 1


def build_base_trade_plan(idea: Idea) -> BaseTradePlan:
    candle = idea.candle
    if idea.side == "long":
        low = candle.open if idea.pattern == "railway_tracks" else candle.low
        risk = max(candle.close - low, 0) * 1.1
        stop = candle.close - risk
        take = candle.close + _risk_multiplicator(idea.level_weight) * risk
    else:
        high = candle.open if idea.pattern == "railway_tracks" else candle.high
        risk = max(high - candle.close, 0) * 1.1
        stop = candle.close + risk
        take = candle.close - _risk_multiplicator(idea.level_weight) * risk

    risk_value = abs(candle.close - stop)
    tp_r = abs(take - candle.close) / risk_value if risk_value else 0.0

    return BaseTradePlan(
        entry_price=candle.close,
        stop_loss=stop,
        take_profit=take,
        risk=risk_value,
        tp_r=tp_r,
    )


def create_execution_state(
    idea: Idea,
    idea_id: str,
    plan: BaseTradePlan,
    variant: str,
    *,
    execution_params: dict,
) -> ExecutionState:
    entry = plan.entry_price
    stop = plan.stop_loss
    take = plan.take_profit
    risk = plan.risk
    tp_r = plan.tp_r

    if variant == "RR2_FIXED":
        take = entry + 2 * risk if idea.side == "long" else entry - 2 * risk
        tp_r = 2.0
    elif variant == "RR2_HYBRID":
        tp1_r = execution_params.get("hybrid", {}).get("tp1_R", 1.0)
        tp2_r = execution_params.get("hybrid", {}).get("tp2_R", 2.0)
        tp1 = entry + tp1_r * risk if idea.side == "long" else entry - tp1_r * risk
        tp2 = entry + tp2_r * risk if idea.side == "long" else entry - tp2_r * risk
        tp1_size = execution_params.get("hybrid", {}).get("tp1_size", 0.5)
        tp2_size = execution_params.get("hybrid", {}).get("tp2_size", 0.5)
        return ExecutionState(
            idea=idea,
            idea_id=idea_id,
            execution_variant=variant,
            execution_id=str(uuid4()),
            entry_price=entry,
            stop_loss=stop,
            take_profit=None,
            risk=risk,
            opened_at=idea.candle.timestamp,
            open_index=-1,
            tp1_price=tp1,
            tp2_price=tp2,
            tp1_size=tp1_size,
            tp2_size=tp2_size,
            remaining_size=1.0,
            tp_r=tp2_r,
        )

    return ExecutionState(
        idea=idea,
        idea_id=idea_id,
        execution_variant=variant,
        execution_id=str(uuid4()),
        entry_price=entry,
        stop_loss=stop,
        take_profit=take,
        risk=risk,
        opened_at=idea.candle.timestamp,
        open_index=-1,
        tp_r=tp_r,
    )


def update_execution_state(
    state: ExecutionState,
    candle: Candle,
    index: int,
    *,
    execution_params: dict,
) -> None:
    if state.is_closed():
        return

    if state.open_index == -1:
        state.open_index = index

    if state.execution_variant == "RR2_HYBRID":
        _update_hybrid(state, candle, index, execution_params)
        return

    if state.execution_variant == "RR1_BE_TS":
        _update_with_be_time_stop(state, candle, index, execution_params)
        return

    _update_basic(state, candle, index)


def _update_basic(state: ExecutionState, candle: Candle, index: int) -> None:
    stop_hit, take_hit = _stop_take_hit(state, candle)

    if stop_hit:
        _close_trade(state, candle, index, "sl", state.stop_loss)
    elif take_hit and state.take_profit is not None:
        _close_trade(state, candle, index, "tp", state.take_profit)


def _update_with_be_time_stop(state: ExecutionState, candle: Candle, index: int, execution_params: dict) -> None:
    be_trigger = execution_params.get("be_trigger_R", 0.5)
    be_offset = execution_params.get("be_offset_R", 0.0)
    time_stop_bars = execution_params.get("time_stop_bars", 6)

    if not state.reached_0_3r:
        target = state.entry_price + 0.3 * state.risk if state.idea.side == "long" else state.entry_price - 0.3 * state.risk
        if (state.idea.side == "long" and candle.high >= target) or (
            state.idea.side == "short" and candle.low <= target
        ):
            state.reached_0_3r = True

    if not state.stop_moved:
        trigger = state.entry_price + be_trigger * state.risk if state.idea.side == "long" else state.entry_price - be_trigger * state.risk
        if (state.idea.side == "long" and candle.high >= trigger) or (
            state.idea.side == "short" and candle.low <= trigger
        ):
            offset = be_offset * state.risk
            state.stop_loss = state.entry_price + offset if state.idea.side == "long" else state.entry_price - offset
            state.stop_moved = True

    stop_hit, take_hit = _stop_take_hit(state, candle)
    if stop_hit:
        reason = "breakeven" if abs(state.stop_loss - state.entry_price) < 1e-9 else "sl"
        _close_trade(state, candle, index, reason, state.stop_loss)
        return
    if take_hit and state.take_profit is not None:
        _close_trade(state, candle, index, "tp", state.take_profit)
        return

    bars_since_entry = index - state.open_index
    if bars_since_entry >= time_stop_bars and not state.reached_0_3r:
        close_price = candle.close
        _close_trade(state, candle, index, "time_stop", close_price)


def _update_hybrid(state: ExecutionState, candle: Candle, index: int, execution_params: dict) -> None:
    stop_hit = candle.low <= state.stop_loss if state.idea.side == "long" else candle.high >= state.stop_loss

    if stop_hit:
        reason = "partial" if state.tp1_hit else "sl"
        if state.tp1_hit:
            tp1_r = execution_params.get("hybrid", {}).get("tp1_R", 1.0)
            realized = (state.tp1_size or 0.0) * tp1_r
            realized += state.remaining_size * -1.0
            state.realized_r = realized
            _close_trade(state, candle, index, reason, state.stop_loss, preset_realized=True)
        else:
            _close_trade(state, candle, index, reason, state.stop_loss)
        return

    tp1_hit = False
    tp2_hit = False

    if state.tp1_price is not None:
        tp1_hit = candle.high >= state.tp1_price if state.idea.side == "long" else candle.low <= state.tp1_price
    if state.tp2_price is not None:
        tp2_hit = candle.high >= state.tp2_price if state.idea.side == "long" else candle.low <= state.tp2_price

    if tp2_hit:
        tp1_r = execution_params.get("hybrid", {}).get("tp1_R", 1.0)
        tp2_r = execution_params.get("hybrid", {}).get("tp2_R", 2.0)
        state.realized_r = (state.tp1_size or 0.0) * tp1_r + (state.tp2_size or 0.0) * tp2_r
        _close_trade(state, candle, index, "tp", state.tp2_price or candle.close, preset_realized=True)
        return

    if tp1_hit and not state.tp1_hit:
        tp1_r = execution_params.get("hybrid", {}).get("tp1_R", 1.0)
        state.realized_r = (state.tp1_size or 0.0) * tp1_r
        state.tp1_hit = True
        state.remaining_size = max(0.0, 1.0 - (state.tp1_size or 0.0))
        move_stop = execution_params.get("hybrid", {}).get("move_stop_to_be", True)
        if move_stop:
            state.stop_loss = state.entry_price
        return


def _stop_take_hit(state: ExecutionState, candle: Candle) -> tuple[bool, bool]:
    stop_hit = candle.low <= state.stop_loss if state.idea.side == "long" else candle.high >= state.stop_loss
    take_hit = False
    if state.take_profit is not None:
        take_hit = candle.high >= state.take_profit if state.idea.side == "long" else candle.low <= state.take_profit
    return stop_hit, take_hit


def _close_trade(
    state: ExecutionState,
    candle: Candle,
    index: int,
    reason: str,
    close_price: float,
    *,
    preset_realized: bool = False,
) -> None:
    state.closed_at = candle.timestamp
    state.close_index = index
    state.exit_reason = reason

    if preset_realized:
        if state.realized_r is None:
            state.realized_r = 0.0
        return

    if state.risk == 0:
        state.realized_r = 0.0
        return

    if state.idea.side == "long":
        state.realized_r = (close_price - state.entry_price) / state.risk
    else:
        state.realized_r = (state.entry_price - close_price) / state.risk


def compute_mfe_mae(
    *,
    candles: list[Candle],
    open_index: int,
    close_index: int,
    entry_price: float,
    risk: float,
    side: Literal["long", "short"],
) -> dict:
    segment = candles[open_index : close_index + 1]
    if not segment:
        return {
            "mfe_price": entry_price,
            "mae_price": entry_price,
            "mfe_R": 0.0,
            "mae_R": 0.0,
            "reached_0_3R": False,
            "reached_0_5R": False,
            "reached_1R": False,
            "time_to_0_3R_bars": None,
            "time_to_0_5R_bars": None,
            "time_to_1R_bars": None,
        }

    if side == "long":
        mfe_price = max(candle.high for candle in segment)
        mae_price = min(candle.low for candle in segment)
        mfe_r = (mfe_price - entry_price) / risk if risk else 0.0
        mae_r = (entry_price - mae_price) / risk if risk else 0.0
        thresholds = [0.3, 0.5, 1.0]
        time_to = _time_to_thresholds_long(segment, entry_price, risk, thresholds)
    else:
        mfe_price = min(candle.low for candle in segment)
        mae_price = max(candle.high for candle in segment)
        mfe_r = (entry_price - mfe_price) / risk if risk else 0.0
        mae_r = (mae_price - entry_price) / risk if risk else 0.0
        thresholds = [0.3, 0.5, 1.0]
        time_to = _time_to_thresholds_short(segment, entry_price, risk, thresholds)

    return {
        "mfe_price": mfe_price,
        "mae_price": mae_price,
        "mfe_R": mfe_r,
        "mae_R": mae_r,
        "reached_0_3R": mfe_r >= 0.3,
        "reached_0_5R": mfe_r >= 0.5,
        "reached_1R": mfe_r >= 1.0,
        "time_to_0_3R_bars": time_to.get(0.3),
        "time_to_0_5R_bars": time_to.get(0.5),
        "time_to_1R_bars": time_to.get(1.0),
    }


def _time_to_thresholds_long(
    segment: list[Candle],
    entry: float,
    risk: float,
    thresholds: list[float],
) -> dict[float, int | None]:
    results = {t: None for t in thresholds}
    if risk == 0:
        return results
    for idx, candle in enumerate(segment):
        for t in thresholds:
            if results[t] is None and candle.high >= entry + t * risk:
                results[t] = idx
    return results


def _time_to_thresholds_short(
    segment: list[Candle],
    entry: float,
    risk: float,
    thresholds: list[float],
) -> dict[float, int | None]:
    results = {t: None for t in thresholds}
    if risk == 0:
        return results
    for idx, candle in enumerate(segment):
        for t in thresholds:
            if results[t] is None and candle.low <= entry - t * risk:
                results[t] = idx
    return results


def isoformat_utc(timestamp_ms: int | None) -> str | None:
    if timestamp_ms is None:
        return None
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).isoformat()
