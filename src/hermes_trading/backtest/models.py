"""Data models for backtest execution and reporting."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from ..candles import Candle

Direction = Literal["long", "short"]


@dataclass(frozen=True)
class StrategyConfig:
    """Strategy-level settings used during signal detection and trade simulation."""

    patterns: tuple[str, ...] = (
        "pin_bar",
        "railway_tracks",
        "buy_engulfing",
        "sell_engulfing",
        "inside_bar",
    )
    min_metric_increase_pct: float = 10.0
    entry_mode: Literal["next_open"] = "next_open"
    stop_mode: Literal["current_trading_formula"] = "current_trading_formula"
    risk_model: Literal["entry_to_stop"] = "entry_to_stop"
    take_profit_r: float | None = None
    take_step_r: float = 0.25
    track_r_step_hit_times: bool = True
    track_internal_signals: bool = True
    close_on_opposite_signal: bool = False
    one_trade_per_symbol_timeframe: bool = True
    direction_filter: tuple[Direction, ...] = ("long", "short")
    use_levels: bool = False
    exit_model_name: str = "hold_to_stop"


@dataclass(frozen=True)
class BacktestConfig:
    """Execution-level settings for a backtest run."""

    exchange: str
    symbols: tuple[str, ...]
    timeframes: tuple[str, ...]
    date_from: str
    date_to: str
    fetch_limit: int = 1000
    output_dir: Path = Path("backtest_results")
    export_trades: bool = True
    export_summary: bool = True


@dataclass(frozen=True)
class SignalEvent:
    """A filtered signal that can trigger or update a trade."""

    symbol: str
    timeframe: str
    pattern: str
    direction: Direction
    signal_candle: Candle
    volatility_increase_pct: tuple[float, float]
    volume_increase_pct: tuple[float, float]


@dataclass(frozen=True)
class TradeRecord:
    """Finalized trade information stored in reports."""

    symbol: str
    timeframe: str
    pattern: str
    direction: Direction
    signal_timestamp: int
    signal_datetime: str
    entry_timestamp: int
    entry_datetime: str
    exit_timestamp: int
    exit_datetime: str
    entry_price: float
    stop_price: float
    take_profit_price: float | None
    exit_price: float
    risk_per_unit: float
    result: str
    exit_reason: str
    bars_in_trade: int
    pnl_abs: float
    pnl_pct: float
    pnl_r: float
    mae_abs: float
    mae_pct: float
    mae_r: float
    mfe_abs: float
    mfe_pct: float
    mfe_r: float
    best_take_step_r: float
    time_to_best_take_step_bars: int | None
    time_to_best_take_step_ms: int | None
    r_step_hit_times: dict[str, dict[str, int]]
    same_direction_signal_count: int = 0
    opposite_direction_signal_count: int = 0
    same_direction_signal_timestamps: list[int] = field(default_factory=list)
    opposite_direction_signal_timestamps: list[int] = field(default_factory=list)
    intrabar_conflict_count: int = 0
    intrabar_conflict_timestamps: list[int] = field(default_factory=list)
    best_price_reached: float = 0.0
    worst_price_reached: float = 0.0


@dataclass(frozen=True)
class BacktestSummary:
    """Aggregated metrics across all simulated trades."""

    total_trades: int
    long_trades: int
    short_trades: int
    win_trades: int
    loss_trades: int
    breakeven_trades: int
    forced_close_trades: int
    win_rate: float
    total_pnl_r: float
    average_pnl_r: float
    average_mae_r: float
    average_mfe_r: float
    max_consecutive_losses: int
    max_consecutive_wins: int
    profit_factor: float | None
    expectancy_r: float
    average_bars_in_trade: float
    pattern_counts: dict[str, int]
    symbol_counts: dict[str, int]
    best_take_step_counts: dict[str, int]
    r_step_stats: dict[str, dict[str, float | int | None]]
    same_direction_internal_signals: int
    opposite_direction_internal_signals: int
    intrabar_conflicts: int


@dataclass(frozen=True)
class BacktestResult:
    """Top-level object returned by the CLI workflow."""

    config: BacktestConfig
    strategy: StrategyConfig
    trades: list[TradeRecord]
    summary: BacktestSummary
