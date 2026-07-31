"""Analyze alternative exit policies from saved backtest trades."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json


@dataclass(frozen=True)
class TradeExitObservation:
    """Minimal trade data needed to evaluate an exit policy."""

    pnl_r: float
    best_take_step_r: float


@dataclass(frozen=True)
class ExitLeg:
    """A position fraction assigned to a take-profit target or the actual exit."""

    fraction: float
    take_profit_r: float | None


@dataclass(frozen=True)
class ExitPolicy:
    """A policy made of one or more exit legs."""

    name: str
    legs: tuple[ExitLeg, ...]


@dataclass(frozen=True)
class ExitPolicySummary:
    """Aggregate metrics for a policy across all trades."""

    policy_name: str
    total_trades: int
    win_trades: int
    loss_trades: int
    breakeven_trades: int
    win_rate: float
    total_pnl_r: float
    average_pnl_r: float
    profit_factor: float | None


def load_trade_observations(path: Path) -> list[TradeExitObservation]:
    """Load the fields needed for exit-policy analysis from a trades export."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    return [
        TradeExitObservation(
            pnl_r=float(item["pnl_r"]),
            best_take_step_r=float(item["best_take_step_r"]),
        )
        for item in payload
    ]


def parse_exit_policy(spec: str) -> ExitPolicy:
    """Parse a policy string such as hold, fixed:2, or scale:0.5@1,0.5@2."""

    normalized = spec.strip().lower()
    if normalized in {"hold", "actual"}:
        return ExitPolicy(name="hold", legs=(ExitLeg(1.0, None),))

    if normalized.startswith("fixed:"):
        target_r = float(normalized.split(":", maxsplit=1)[1])
        if target_r <= 0:
            raise ValueError("fixed take-profit targets must be positive")
        return ExitPolicy(
            name=_format_policy_name((ExitLeg(1.0, target_r),)),
            legs=(ExitLeg(1.0, target_r),),
        )

    if not normalized.startswith("scale:"):
        raise ValueError(f"unsupported policy: {spec}")

    legs: list[ExitLeg] = []
    fractions_total = 0.0
    body = normalized.split(":", maxsplit=1)[1]
    for raw_leg in body.split(","):
        fraction_text, target_text = raw_leg.split("@", maxsplit=1)
        fraction = float(fraction_text)
        if fraction <= 0:
            raise ValueError("scale-out fractions must be positive")

        take_profit_r: float | None
        if target_text in {"hold", "actual"}:
            take_profit_r = None
        else:
            take_profit_r = float(target_text)
            if take_profit_r <= 0:
                raise ValueError("scale-out targets must be positive")

        fractions_total += fraction
        if fractions_total > 1.0 + 1e-9:
            raise ValueError("scale-out fractions must sum to 1.0 or less")
        legs.append(ExitLeg(fraction, take_profit_r))

    if fractions_total < 1.0 - 1e-9:
        legs.append(ExitLeg(1.0 - fractions_total, None))

    policy_legs = tuple(legs)
    return ExitPolicy(name=_format_policy_name(policy_legs), legs=policy_legs)


def evaluate_policy_pnl(trade: TradeExitObservation, policy: ExitPolicy) -> float:
    """Evaluate one trade under a policy using its achieved best R step."""

    total_pnl_r = 0.0
    for leg in policy.legs:
        leg_pnl_r = trade.pnl_r
        if leg.take_profit_r is not None and trade.best_take_step_r >= leg.take_profit_r - 1e-9:
            leg_pnl_r = leg.take_profit_r
        total_pnl_r += leg.fraction * leg_pnl_r
    return total_pnl_r


def summarize_exit_policy(
    trades: list[TradeExitObservation],
    policy: ExitPolicy,
) -> ExitPolicySummary:
    """Aggregate policy metrics across all trades."""

    policy_pnls = [evaluate_policy_pnl(trade, policy) for trade in trades]
    total_trades = len(policy_pnls)
    win_trades = sum(1 for pnl_r in policy_pnls if pnl_r > 0)
    loss_trades = sum(1 for pnl_r in policy_pnls if pnl_r < 0)
    breakeven_trades = total_trades - win_trades - loss_trades
    total_pnl_r = sum(policy_pnls)
    average_pnl_r = total_pnl_r / total_trades if total_trades else 0.0

    positive_pnl = sum(pnl_r for pnl_r in policy_pnls if pnl_r > 0)
    negative_pnl = sum(pnl_r for pnl_r in policy_pnls if pnl_r < 0)
    profit_factor = None
    if negative_pnl < 0:
        profit_factor = positive_pnl / abs(negative_pnl)
    elif positive_pnl > 0:
        profit_factor = float("inf")

    return ExitPolicySummary(
        policy_name=policy.name,
        total_trades=total_trades,
        win_trades=win_trades,
        loss_trades=loss_trades,
        breakeven_trades=breakeven_trades,
        win_rate=(win_trades / total_trades) * 100 if total_trades else 0.0,
        total_pnl_r=total_pnl_r,
        average_pnl_r=average_pnl_r,
        profit_factor=profit_factor,
    )


def _format_policy_name(legs: tuple[ExitLeg, ...]) -> str:
    if len(legs) == 1 and legs[0].take_profit_r is None and abs(legs[0].fraction - 1.0) <= 1e-9:
        return "hold"
    if len(legs) == 1 and abs(legs[0].fraction - 1.0) <= 1e-9 and legs[0].take_profit_r is not None:
        return f"fixed:{legs[0].take_profit_r:g}"

    formatted_legs = []
    for leg in legs:
        target = "actual" if leg.take_profit_r is None else f"{leg.take_profit_r:g}"
        formatted_legs.append(f"{leg.fraction:g}@{target}")
    return f"scale:{','.join(formatted_legs)}"
