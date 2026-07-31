"""Backtest utilities for historical strategy evaluation."""

from .data_loader import create_connector, fetch_historical_candles
from .models import (
    BacktestConfig,
    BacktestResult,
    BacktestSummary,
    SignalEvent,
    StrategyConfig,
    TradeRecord,
)
from .reporting import (
    build_summary,
    render_summary_text,
    save_backtest_artifacts,
    save_strategy_comparison,
)
from .saved_signals import (
    SavedSignalRecord,
    build_signal_events_from_saved_records,
    load_saved_signal_records,
    merge_saved_signal_records,
    save_saved_signal_records,
)
from .signals_bot_adapter import build_signal_events
from .simulator import simulate_candles

__all__ = [
    "BacktestConfig",
    "BacktestResult",
    "BacktestSummary",
    "SignalEvent",
    "StrategyConfig",
    "TradeRecord",
    "build_signal_events",
    "build_signal_events_from_saved_records",
    "build_summary",
    "create_connector",
    "fetch_historical_candles",
    "load_saved_signal_records",
    "merge_saved_signal_records",
    "render_summary_text",
    "SavedSignalRecord",
    "save_backtest_artifacts",
    "save_saved_signal_records",
    "save_strategy_comparison",
    "simulate_candles",
]
