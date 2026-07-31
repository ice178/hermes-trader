"""Simple backtest runner for signals_bot pattern signals."""

from __future__ import annotations

import argparse
from bisect import bisect_left
import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, time, timezone
from itertools import product
from pathlib import Path
from typing import Sequence

from .backtest.data_loader import create_connector, fetch_historical_candles
from .candles import Candle, CandleBatch
from .liquidity import Level, LiquidityLevels
from .market_context import SignalMarketContext, build_signal_market_context
from .signal_filters import (
    DEFAULT_MIN_METRIC_INCREASE_PCT,
    FilteredSignal,
    filtered_latest_matches,
)
from .time_utils import (
    MADRID_TIMEZONE,
    is_candle_closed,
    madrid_datetime_from_timestamp_ms,
    timeframe_to_milliseconds,
)

DEFAULT_SYMBOLS = (
    "BTC/USDT",
    "ETH/USDT",
    "XRP/USDT",
    "LINK/USDT",
    "TRX/USDT",
    "SOL/USDT",
    "NEAR/USDT",
    "ATOM/USDT",
    "BNB/USDT",
)
DEFAULT_TIMEFRAMES = ("15m", "30m", "1h")
DEFAULT_PATTERNS = (
    "pin_bar",
    "railway_tracks",
    "buy_engulfing",
    "sell_engulfing",
    "inside_bar",
)
DEFAULT_OUTPUT_PATH = Path(__file__).resolve().parents[1] / "signals_bot_backtest_results.json"


@dataclass(frozen=True)
class SignalBotBacktestConfig:
    exchange: str
    symbols: tuple[str, ...]
    timeframes: tuple[str, ...]
    date_from: str
    date_to: str
    fetch_limit: int
    patterns: tuple[str, ...]
    min_metric_increase_pct: float
    use_levels: bool
    min_level_weight: float
    exclude_hours: tuple[int, ...]
    allowed_higher_timeframe_biases: tuple[str, ...]
    allowed_volatility_regimes: tuple[str, ...]
    min_distance_to_recent_low_pct: float | None
    min_distance_to_recent_high_pct: float | None
    execution_timeframe: str | None
    take_multiple: float
    take_multiples: tuple[float, ...]
    stop_multiple: float
    stop_multiples: tuple[float, ...]
    save_all_variant_trades: bool
    output_file: str
    normalized_date_from_madrid: str
    normalized_date_to_madrid: str
    normalized_date_from_utc: str
    normalized_date_to_utc: str


@dataclass(frozen=True)
class DetectedSignal:
    filtered_signal: FilteredSignal
    candle_index: int


@dataclass(frozen=True)
class EntryContext:
    entry_price: float
    entry_timestamp: int
    entry_datetime: str
    execution_timeframe: str
    entry_source: str
    signal_available_at_timestamp: int
    signal_available_at: str
    signal_to_entry_minutes: float
    tracking_start_index: int
    bars_reference_index: int


@dataclass(frozen=True)
class SignalBotBacktestTrade:
    symbol: str
    timeframe: str
    signal_timeframe: str
    execution_timeframe: str
    pattern: str
    direction: str
    is_suitable: bool | None
    comment: str | None
    mistake_reason: str | None
    signal_timestamp: int
    signal_datetime: str
    signal_open: float
    signal_high: float
    signal_low: float
    signal_close: float
    signal_volume: float
    signal_volatility_increase_pct: tuple[float, float]
    signal_volume_increase_pct: tuple[float, float]
    signal_volatility_increase_min_pct: float
    signal_volatility_increase_max_pct: float
    signal_volume_increase_min_pct: float
    signal_volume_increase_max_pct: float
    signal_hour: int
    signal_weekday: int
    signal_weekday_name: str
    signal_range_abs: float
    signal_range_pct: float
    signal_body_abs: float
    signal_body_pct_of_range: float
    signal_upper_wick_abs: float
    signal_upper_wick_pct_of_range: float
    signal_lower_wick_abs: float
    signal_lower_wick_pct_of_range: float
    context_higher_timeframe: str | None
    context_higher_timeframe_bias: str | None
    context_higher_timeframe_close: float | None
    context_higher_timeframe_fast_sma: float | None
    context_higher_timeframe_slow_sma: float | None
    context_range_lookback: int
    context_range_high: float | None
    context_range_low: float | None
    context_range_position_pct: float | None
    context_recent_lookback: int
    context_recent_high: float | None
    context_recent_low: float | None
    context_distance_to_recent_high_abs: float | None
    context_distance_to_recent_high_pct: float | None
    context_distance_to_recent_low_abs: float | None
    context_distance_to_recent_low_pct: float | None
    context_atr_period: int
    context_atr_abs: float | None
    context_atr_pct: float | None
    context_signal_range_to_atr_ratio: float | None
    context_volatility_regime: str | None
    level_price: float | None
    level_type: str | None
    level_weight: float | None
    level_timestamp: int | None
    level_datetime: str | None
    level_confirmed_timestamp: int | None
    level_confirmed_datetime: str | None
    level_to_entry_abs: float | None
    level_to_entry_pct: float | None
    signal_available_at_timestamp: int
    signal_available_at: str
    take_multiple: float
    stop_multiple: float
    rr_ratio: float
    entry_timestamp: int
    entry_datetime: str
    entry_source: str
    signal_to_entry_minutes: float
    entry_price: float
    stop_price: float
    take_price: float
    signal_risk_per_unit: float
    risk_per_unit: float
    risk_pct_from_entry: float
    signal_risk_pct_from_entry: float
    exit_timestamp: int
    exit_datetime: str
    closed_at: str
    exit_price: float
    exit_reason: str
    result: str
    pnl_abs: float
    pnl_pct: float
    pnl_r: float
    pnl_signal_r: float
    bars_in_trade: int
    duration_minutes: float
    max_drawdown_abs: float
    max_drawdown_pct: float
    max_drawdown_r: float
    max_drawdown_signal_r: float
    max_profit_abs: float
    max_profit_pct: float
    max_profit_r: float
    max_profit_signal_r: float
    intrabar_conflict: bool
    intrabar_conflict_reason: str | None


@dataclass(frozen=True)
class SignalBotBacktestSummary:
    total_signals: int
    total_trades_opened: int
    skipped_invalid_risk: int
    skipped_missing_entry_candle: int
    wins: int
    losses: int
    breakevens: int
    end_of_data_closes: int
    intrabar_conflicts: int
    win_rate: float
    total_pnl_r: float
    total_pnl_signal_r: float
    average_pnl_r: float
    average_pnl_signal_r: float
    average_win_r: float
    average_loss_r: float
    profit_factor: float | None
    max_equity_drawdown_r: float
    average_max_drawdown_r: float
    average_max_profit_r: float
    counts_by_pattern: dict[str, int]
    counts_by_symbol: dict[str, int]
    counts_by_timeframe: dict[str, int]
    counts_by_level_weight: dict[str, int]
    counts_by_level_type: dict[str, int]


@dataclass(frozen=True)
class SignalBotSeriesStats:
    symbol: str
    timeframe: str
    candle_count: int
    signal_count: int
    trade_count: int
    skipped_invalid_risk: int
    skipped_missing_entry_candle: int


@dataclass(frozen=True)
class SignalBotVariantSummary:
    take_multiple: float
    stop_multiple: float
    summary: SignalBotBacktestSummary


@dataclass(frozen=True)
class SignalBotBacktestResult:
    config: SignalBotBacktestConfig
    summary: SignalBotBacktestSummary
    variant_summaries: list[SignalBotVariantSummary]
    take_variant_summaries: list[SignalBotVariantSummary]
    series: list[SignalBotSeriesStats]
    trades: list[SignalBotBacktestTrade]
    variant_trades: dict[str, list[SignalBotBacktestTrade]] | None


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exchange", default="binance")
    parser.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS))
    parser.add_argument("--timeframes", nargs="+", default=list(DEFAULT_TIMEFRAMES))
    parser.add_argument("--date-from", required=True)
    parser.add_argument("--date-to", required=True)
    parser.add_argument("--fetch-limit", type=int, default=1000)
    parser.add_argument("--patterns", nargs="+", default=list(DEFAULT_PATTERNS))
    parser.add_argument(
        "--min-metric-increase-pct",
        type=float,
        default=DEFAULT_MIN_METRIC_INCREASE_PCT,
    )
    parser.add_argument("--use-levels", action="store_true")
    parser.add_argument("--min-level-weight", type=float, default=0.0)
    parser.add_argument("--exclude-hours", nargs="+", type=int)
    parser.add_argument("--allowed-higher-timeframe-biases", nargs="+")
    parser.add_argument("--allowed-volatility-regimes", nargs="+")
    parser.add_argument("--min-distance-to-recent-low-pct", type=float)
    parser.add_argument("--min-distance-to-recent-high-pct", type=float)
    parser.add_argument("--execution-timeframe")
    parser.add_argument("--take-multiple", type=float, default=1.0)
    parser.add_argument("--compare-take-multiples", nargs="+", type=float)
    parser.add_argument("--compare-take-range", nargs=3, type=float)
    parser.add_argument("--stop-multiple", type=float, default=1.0)
    parser.add_argument("--compare-stop-multiples", nargs="+", type=float)
    parser.add_argument("--compare-stop-range", nargs=3, type=float)
    parser.add_argument("--save-all-variant-trades", action="store_true")
    parser.add_argument("--output-file", default=str(DEFAULT_OUTPUT_PATH))
    return parser.parse_args(argv)


def _parse_cli_datetime(value: str, *, is_end: bool) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    if "T" not in normalized and len(normalized) == 10:
        base = datetime.fromisoformat(normalized).date()
        selected_time = time.max if is_end else time.min
        return datetime.combine(base, selected_time, tzinfo=MADRID_TIMEZONE)

    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=MADRID_TIMEZONE)
    return dt.astimezone(MADRID_TIMEZONE)


def normalize_date_range(date_from: str, date_to: str) -> tuple[datetime, datetime]:
    start_dt = _parse_cli_datetime(date_from, is_end=False)
    end_dt = _parse_cli_datetime(date_to, is_end=True)
    if end_dt <= start_dt:
        raise ValueError("date_to must be greater than date_from")
    return start_dt, end_dt


def _expand_multiple_range(
    compare_range: Sequence[float] | None,
    *,
    label: str,
) -> list[float]:
    if compare_range is None:
        return []

    if len(compare_range) != 3:
        raise ValueError(f"{label} range requires start, end, step")

    start, end, step = (float(value) for value in compare_range)
    if start <= 0 or end <= 0 or step <= 0:
        raise ValueError(f"{label} range values must be positive")
    if end < start:
        raise ValueError(f"{label} range end must be greater than or equal to start")

    values: list[float] = []
    current = start
    while current <= end + (step * 1e-9):
        values.append(round(current, 10))
        current += step
    return values


def _normalize_multiples(
    primary_multiple: float,
    compare_multiples: Sequence[float] | None = None,
    compare_range: Sequence[float] | None = None,
    *,
    label: str,
) -> tuple[float, tuple[float, ...]]:
    values = [primary_multiple]
    if compare_multiples is not None:
        values.extend(compare_multiples)
    values.extend(_expand_multiple_range(compare_range, label=label))

    normalized: list[float] = []
    seen: set[float] = set()
    for value in values:
        current = float(value)
        if current <= 0:
            raise ValueError(f"{label} multiples must be positive")
        if current in seen:
            continue
        seen.add(current)
        normalized.append(current)
    return float(primary_multiple), tuple(normalized)


def normalize_take_multiples(
    take_multiple: float,
    compare_take_multiples: Sequence[float] | None = None,
    compare_take_range: Sequence[float] | None = None,
) -> tuple[float, tuple[float, ...]]:
    return _normalize_multiples(
        take_multiple,
        compare_take_multiples,
        compare_take_range,
        label="take",
    )


def normalize_stop_multiples(
    stop_multiple: float,
    compare_stop_multiples: Sequence[float] | None = None,
    compare_stop_range: Sequence[float] | None = None,
) -> tuple[float, tuple[float, ...]]:
    return _normalize_multiples(
        stop_multiple,
        compare_stop_multiples,
        compare_stop_range,
        label="stop",
    )


def _normalize_hours(values: Sequence[int] | None) -> tuple[int, ...]:
    if values is None:
        return ()

    normalized: list[int] = []
    seen: set[int] = set()
    for value in values:
        hour = int(value)
        if hour < 0 or hour > 23:
            raise ValueError("hours must be in the range 0..23")
        if hour in seen:
            continue
        seen.add(hour)
        normalized.append(hour)
    return tuple(normalized)


def _normalize_optional_choices(
    values: Sequence[str] | None,
    *,
    label: str,
    allowed_values: set[str],
) -> tuple[str, ...]:
    if values is None:
        return ()

    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        current = str(value).strip().lower()
        if current not in allowed_values:
            raise ValueError(
                f"{label} must be one of: {', '.join(sorted(allowed_values))}"
            )
        if current in seen:
            continue
        seen.add(current)
        normalized.append(current)
    return tuple(normalized)


def _normalize_optional_non_negative(
    value: float | None,
    *,
    label: str,
) -> float | None:
    if value is None:
        return None
    current = float(value)
    if current < 0:
        raise ValueError(f"{label} must be greater than or equal to 0")
    return current


def build_config(args: argparse.Namespace) -> SignalBotBacktestConfig:
    start_dt, end_dt = normalize_date_range(args.date_from, args.date_to)
    take_multiple, take_multiples = normalize_take_multiples(
        float(args.take_multiple),
        args.compare_take_multiples,
        args.compare_take_range,
    )
    stop_multiple, stop_multiples = normalize_stop_multiples(
        float(args.stop_multiple),
        args.compare_stop_multiples,
        args.compare_stop_range,
    )
    return SignalBotBacktestConfig(
        exchange=str(args.exchange),
        symbols=tuple(str(symbol) for symbol in args.symbols),
        timeframes=tuple(str(timeframe) for timeframe in args.timeframes),
        date_from=str(args.date_from),
        date_to=str(args.date_to),
        fetch_limit=int(args.fetch_limit),
        patterns=tuple(str(pattern) for pattern in args.patterns),
        min_metric_increase_pct=float(args.min_metric_increase_pct),
        use_levels=bool(args.use_levels),
        min_level_weight=float(args.min_level_weight),
        exclude_hours=_normalize_hours(args.exclude_hours),
        allowed_higher_timeframe_biases=_normalize_optional_choices(
            args.allowed_higher_timeframe_biases,
            label="allowed_higher_timeframe_biases",
            allowed_values={"bullish", "bearish", "neutral", "none"},
        ),
        allowed_volatility_regimes=_normalize_optional_choices(
            args.allowed_volatility_regimes,
            label="allowed_volatility_regimes",
            allowed_values={"compressed", "normal", "expanded", "none"},
        ),
        min_distance_to_recent_low_pct=_normalize_optional_non_negative(
            args.min_distance_to_recent_low_pct,
            label="min_distance_to_recent_low_pct",
        ),
        min_distance_to_recent_high_pct=_normalize_optional_non_negative(
            args.min_distance_to_recent_high_pct,
            label="min_distance_to_recent_high_pct",
        ),
        execution_timeframe=(
            str(args.execution_timeframe)
            if args.execution_timeframe is not None
            else None
        ),
        take_multiple=take_multiple,
        take_multiples=take_multiples,
        stop_multiple=stop_multiple,
        stop_multiples=stop_multiples,
        save_all_variant_trades=bool(args.save_all_variant_trades),
        output_file=str(args.output_file),
        normalized_date_from_madrid=start_dt.isoformat(),
        normalized_date_to_madrid=end_dt.isoformat(),
        normalized_date_from_utc=start_dt.astimezone(timezone.utc).isoformat(),
        normalized_date_to_utc=end_dt.astimezone(timezone.utc).isoformat(),
    )


def collect_filtered_signals(
    candles: Sequence[Candle],
    *,
    patterns: Sequence[str] | None = None,
    min_metric_increase_pct: float = DEFAULT_MIN_METRIC_INCREASE_PCT,
    use_levels: bool = False,
    min_level_weight: float = 0.0,
    levels_state: LiquidityLevels | None = None,
) -> list[DetectedSignal]:
    if len(candles) < 4:
        return []

    if min_level_weight < 0:
        raise ValueError("min_level_weight must be greater than or equal to 0")

    active_levels_state = levels_state
    if use_levels:
        active_levels_state = active_levels_state or LiquidityLevels()
        if levels_state is None:
            active_levels_state.build(list(candles))

    signals: list[DetectedSignal] = []
    for idx in range(3, len(candles)):
        current_candle = candles[idx]
        batch = CandleBatch(list(candles[idx - 3: idx + 1]))
        active_levels: list[Level] | None = None
        if use_levels and active_levels_state is not None:
            active_levels = [
                level
                for level in active_levels_state.active_levels(current_candle.timestamp)
                if level.weight >= min_level_weight
            ]
        for filtered in filtered_latest_matches(
            batch,
            patterns=patterns,
            min_metric_increase_pct=min_metric_increase_pct,
            levels=active_levels,
        ):
            signals.append(
                DetectedSignal(
                    filtered_signal=filtered,
                    candle_index=idx,
                )
            )
        if use_levels and active_levels_state is not None:
            active_levels_state.prune(current_candle)
    return signals


def _stop_hit(direction: str, stop_price: float, candle: Candle) -> bool:
    if direction == "long":
        return candle.low <= stop_price
    return candle.high >= stop_price


def _take_hit(direction: str, take_price: float, candle: Candle) -> bool:
    if direction == "long":
        return candle.high >= take_price
    return candle.low <= take_price


def _adverse_abs(direction: str, entry_price: float, candle: Candle) -> float:
    if direction == "long":
        return max(entry_price - candle.low, 0.0)
    return max(candle.high - entry_price, 0.0)


def _favorable_abs(direction: str, entry_price: float, candle: Candle) -> float:
    if direction == "long":
        return max(candle.high - entry_price, 0.0)
    return max(entry_price - candle.low, 0.0)


def _pnl_abs(direction: str, entry_price: float, exit_price: float) -> float:
    if direction == "long":
        return exit_price - entry_price
    return entry_price - exit_price


def _classify_result(pnl_r: float) -> str:
    if pnl_r > 0:
        return "win"
    if pnl_r < 0:
        return "loss"
    return "breakeven"


def _signal_parts(signal_datetime: str) -> tuple[int, int, str]:
    dt = datetime.fromisoformat(signal_datetime)
    return dt.hour, dt.weekday(), dt.strftime("%A").lower()


def signal_passes_context_filters(
    detected_signal: DetectedSignal,
    market_context: SignalMarketContext,
    config: SignalBotBacktestConfig,
) -> bool:
    signal_hour, _, _ = _signal_parts(detected_signal.filtered_signal.match.candle.datetime)
    if signal_hour in config.exclude_hours:
        return False

    if config.allowed_higher_timeframe_biases:
        bias = market_context.higher_timeframe_bias or "none"
        if bias not in config.allowed_higher_timeframe_biases:
            return False

    if config.allowed_volatility_regimes:
        regime = market_context.volatility_regime or "none"
        if regime not in config.allowed_volatility_regimes:
            return False

    direction = detected_signal.filtered_signal.match.direction
    if direction == "long" and config.min_distance_to_recent_low_pct is not None:
        distance_to_recent_low_pct = market_context.distance_to_recent_low_pct
        if (
            distance_to_recent_low_pct is None
            or distance_to_recent_low_pct < config.min_distance_to_recent_low_pct
        ):
            return False

    if direction == "short" and config.min_distance_to_recent_high_pct is not None:
        distance_to_recent_high_pct = market_context.distance_to_recent_high_pct
        if (
            distance_to_recent_high_pct is None
            or distance_to_recent_high_pct < config.min_distance_to_recent_high_pct
        ):
            return False

    return True


def _signal_range_abs(signal_candle: Candle) -> float:
    return float(signal_candle.high) - float(signal_candle.low)


def _signal_body_abs(signal_candle: Candle) -> float:
    return abs(float(signal_candle.close) - float(signal_candle.open))


def _signal_upper_wick_abs(signal_candle: Candle) -> float:
    candle_high = float(signal_candle.high)
    candle_body_high = max(float(signal_candle.open), float(signal_candle.close))
    return max(candle_high - candle_body_high, 0.0)


def _signal_lower_wick_abs(signal_candle: Candle) -> float:
    candle_low = float(signal_candle.low)
    candle_body_low = min(float(signal_candle.open), float(signal_candle.close))
    return max(candle_body_low - candle_low, 0.0)


def _pct_of_range(value: float, range_abs: float) -> float:
    return (value / range_abs) * 100 if range_abs else 0.0


def _pct_of_price(value: float, price: float) -> float:
    return (value / price) * 100 if price else 0.0


def _profit_factor(trades: Sequence[SignalBotBacktestTrade]) -> float | None:
    positive_pnl = sum(trade.pnl_r for trade in trades if trade.pnl_r > 0)
    negative_pnl = sum(trade.pnl_r for trade in trades if trade.pnl_r < 0)
    if negative_pnl < 0:
        return positive_pnl / abs(negative_pnl)
    if positive_pnl > 0:
        return float("inf")
    return None


def _max_equity_drawdown_r(trades: Sequence[SignalBotBacktestTrade]) -> float:
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for trade in sorted(
        trades,
        key=lambda trade: (
            trade.entry_timestamp,
            trade.signal_timestamp,
            trade.symbol,
            trade.timeframe,
            trade.pattern,
        ),
    ):
        equity += trade.pnl_r
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    return max_drawdown


def build_variant_keys(config: SignalBotBacktestConfig) -> list[tuple[float, float]]:
    variant_keys = list(
        product(
            config.take_multiples,
            config.stop_multiples,
        )
    )
    primary_key = (config.take_multiple, config.stop_multiple)
    ordered_keys = [primary_key]
    ordered_keys.extend(
        key
        for key in variant_keys
        if key != primary_key
    )
    return ordered_keys


def format_variant_key(take_multiple: float, stop_multiple: float) -> str:
    return f"take={take_multiple:.10g}|stop={stop_multiple:.10g}"


def signal_available_timestamp(detected_signal: DetectedSignal) -> int:
    signal_candle = detected_signal.filtered_signal.match.candle
    timeframe = signal_candle.timeframe
    if timeframe is None:
        raise ValueError("signal candle timeframe is required")
    return signal_candle.timestamp + timeframe_to_milliseconds(timeframe)


def find_entry_candle_index(
    candles: Sequence[Candle],
    signal_available_at_timestamp: int,
) -> int | None:
    if not candles:
        return None
    timestamps = [candle.timestamp for candle in candles]
    index = bisect_left(timestamps, signal_available_at_timestamp)
    if index >= len(candles):
        return None
    return index


def build_entry_context(
    detected_signal: DetectedSignal,
    source_candles: Sequence[Candle],
    *,
    execution_candles: Sequence[Candle] | None = None,
    execution_timeframe: str | None = None,
) -> EntryContext | None:
    del source_candles

    signal_candle = detected_signal.filtered_signal.match.candle
    signal_available_at_timestamp = signal_available_timestamp(detected_signal)
    signal_available_at = madrid_datetime_from_timestamp_ms(signal_available_at_timestamp)

    if execution_candles is not None and execution_timeframe is not None:
        entry_index = find_entry_candle_index(execution_candles, signal_available_at_timestamp)
        if entry_index is None:
            return None
        entry_candle = execution_candles[entry_index]
        return EntryContext(
            entry_price=float(entry_candle.open),
            entry_timestamp=entry_candle.timestamp,
            entry_datetime=entry_candle.datetime,
            execution_timeframe=execution_timeframe,
            entry_source="execution_timeframe_open",
            signal_available_at_timestamp=signal_available_at_timestamp,
            signal_available_at=signal_available_at,
            signal_to_entry_minutes=max(
                (entry_candle.timestamp - signal_available_at_timestamp) / 60000.0,
                0.0,
            ),
            tracking_start_index=entry_index,
            bars_reference_index=entry_index,
        )

    signal_timeframe = signal_candle.timeframe
    if signal_timeframe is None:
        raise ValueError("signal candle timeframe is required")

    return EntryContext(
        entry_price=float(signal_candle.close),
        entry_timestamp=signal_available_at_timestamp,
        entry_datetime=signal_available_at,
        execution_timeframe=signal_timeframe,
        entry_source="signal_close",
        signal_available_at_timestamp=signal_available_at_timestamp,
        signal_available_at=signal_available_at,
        signal_to_entry_minutes=0.0,
        tracking_start_index=detected_signal.candle_index + 1,
        bars_reference_index=detected_signal.candle_index,
    )


def simulate_trade(
    detected_signal: DetectedSignal,
    candles: Sequence[Candle],
    *,
    execution_candles: Sequence[Candle] | None = None,
    execution_timeframe: str | None = None,
    entry_context: EntryContext | None = None,
    market_context: SignalMarketContext | None = None,
    take_multiple: float = 1.0,
    stop_multiple: float = 1.0,
) -> SignalBotBacktestTrade | None:
    if take_multiple <= 0:
        raise ValueError("take_multiple must be positive")
    if stop_multiple <= 0:
        raise ValueError("stop_multiple must be positive")

    filtered = detected_signal.filtered_signal
    match = filtered.match
    signal_candle = match.candle
    entry_context = entry_context or build_entry_context(
        detected_signal,
        candles,
        execution_candles=execution_candles,
        execution_timeframe=execution_timeframe,
    )
    if entry_context is None:
        return None

    entry_price = entry_context.entry_price

    if match.direction == "long":
        signal_risk_per_unit = entry_price - float(signal_candle.low)
        risk_per_unit = signal_risk_per_unit * stop_multiple
        stop_price = entry_price - risk_per_unit
        take_price = entry_price + (signal_risk_per_unit * take_multiple)
    else:
        signal_risk_per_unit = float(signal_candle.high) - entry_price
        risk_per_unit = signal_risk_per_unit * stop_multiple
        stop_price = entry_price + risk_per_unit
        take_price = entry_price - (signal_risk_per_unit * take_multiple)

    if signal_risk_per_unit <= 0 or risk_per_unit <= 0:
        return None

    max_drawdown_abs = 0.0
    max_profit_abs = 0.0
    intrabar_conflict = False
    intrabar_conflict_reason: str | None = None

    tracking_candles = execution_candles if entry_context.entry_source == "execution_timeframe_open" else candles

    exit_timestamp = entry_context.entry_timestamp
    exit_datetime = entry_context.entry_datetime
    exit_price = entry_price
    exit_reason = "end_of_data"
    exit_index = entry_context.bars_reference_index

    for candle_index in range(entry_context.tracking_start_index, len(tracking_candles)):
        candle = tracking_candles[candle_index]
        max_drawdown_abs = max(
            max_drawdown_abs,
            _adverse_abs(match.direction, entry_price, candle),
        )
        max_profit_abs = max(
            max_profit_abs,
            _favorable_abs(match.direction, entry_price, candle),
        )

        stop_hit = _stop_hit(match.direction, stop_price, candle)
        take_hit = _take_hit(match.direction, take_price, candle)

        if stop_hit and take_hit:
            intrabar_conflict = True
            intrabar_conflict_reason = "stop_and_take_hit_same_candle"
            exit_timestamp = candle.timestamp
            exit_datetime = candle.datetime
            exit_price = stop_price
            exit_reason = "stop_loss"
            exit_index = candle_index
            break

        if stop_hit:
            exit_timestamp = candle.timestamp
            exit_datetime = candle.datetime
            exit_price = stop_price
            exit_reason = "stop_loss"
            exit_index = candle_index
            break

        if take_hit:
            exit_timestamp = candle.timestamp
            exit_datetime = candle.datetime
            exit_price = take_price
            exit_reason = "take_profit"
            exit_index = candle_index
            break

        exit_timestamp = candle.timestamp
        exit_datetime = candle.datetime
        exit_price = float(candle.close)
        exit_index = candle_index

    pnl_abs = _pnl_abs(match.direction, entry_price, exit_price)
    pnl_pct = (pnl_abs / entry_price) * 100 if entry_price else 0.0
    pnl_r = pnl_abs / risk_per_unit if risk_per_unit else 0.0
    pnl_signal_r = pnl_abs / signal_risk_per_unit if signal_risk_per_unit else 0.0
    signal_hour, signal_weekday, signal_weekday_name = _signal_parts(signal_candle.datetime)
    signal_range_abs = _signal_range_abs(signal_candle)
    signal_body_abs = _signal_body_abs(signal_candle)
    signal_upper_wick_abs = _signal_upper_wick_abs(signal_candle)
    signal_lower_wick_abs = _signal_lower_wick_abs(signal_candle)
    level = match.level
    market_context = market_context or build_signal_market_context(
        candles,
        detected_signal.candle_index,
    )
    level_to_entry_abs = (
        abs(entry_price - float(level.price))
        if level is not None
        else None
    )

    return SignalBotBacktestTrade(
        symbol=signal_candle.symbol or "",
        timeframe=signal_candle.timeframe or "",
        signal_timeframe=signal_candle.timeframe or "",
        execution_timeframe=entry_context.execution_timeframe,
        pattern=match.pattern,
        direction=match.direction,
        is_suitable=None,
        comment=None,
        mistake_reason=None,
        signal_timestamp=signal_candle.timestamp,
        signal_datetime=signal_candle.datetime,
        signal_open=float(signal_candle.open),
        signal_high=float(signal_candle.high),
        signal_low=float(signal_candle.low),
        signal_close=float(signal_candle.close),
        signal_volume=float(signal_candle.volume),
        signal_volatility_increase_pct=filtered.volatility_increase_pct,
        signal_volume_increase_pct=filtered.volume_increase_pct,
        signal_volatility_increase_min_pct=min(filtered.volatility_increase_pct),
        signal_volatility_increase_max_pct=max(filtered.volatility_increase_pct),
        signal_volume_increase_min_pct=min(filtered.volume_increase_pct),
        signal_volume_increase_max_pct=max(filtered.volume_increase_pct),
        signal_hour=signal_hour,
        signal_weekday=signal_weekday,
        signal_weekday_name=signal_weekday_name,
        signal_range_abs=signal_range_abs,
        signal_range_pct=_pct_of_price(signal_range_abs, float(signal_candle.close)),
        signal_body_abs=signal_body_abs,
        signal_body_pct_of_range=_pct_of_range(signal_body_abs, signal_range_abs),
        signal_upper_wick_abs=signal_upper_wick_abs,
        signal_upper_wick_pct_of_range=_pct_of_range(signal_upper_wick_abs, signal_range_abs),
        signal_lower_wick_abs=signal_lower_wick_abs,
        signal_lower_wick_pct_of_range=_pct_of_range(signal_lower_wick_abs, signal_range_abs),
        context_higher_timeframe=market_context.higher_timeframe,
        context_higher_timeframe_bias=market_context.higher_timeframe_bias,
        context_higher_timeframe_close=market_context.higher_timeframe_close,
        context_higher_timeframe_fast_sma=market_context.higher_timeframe_fast_sma,
        context_higher_timeframe_slow_sma=market_context.higher_timeframe_slow_sma,
        context_range_lookback=market_context.range_lookback,
        context_range_high=market_context.range_high,
        context_range_low=market_context.range_low,
        context_range_position_pct=market_context.range_position_pct,
        context_recent_lookback=market_context.recent_lookback,
        context_recent_high=market_context.recent_high,
        context_recent_low=market_context.recent_low,
        context_distance_to_recent_high_abs=market_context.distance_to_recent_high_abs,
        context_distance_to_recent_high_pct=market_context.distance_to_recent_high_pct,
        context_distance_to_recent_low_abs=market_context.distance_to_recent_low_abs,
        context_distance_to_recent_low_pct=market_context.distance_to_recent_low_pct,
        context_atr_period=market_context.atr_period,
        context_atr_abs=market_context.atr_abs,
        context_atr_pct=market_context.atr_pct,
        context_signal_range_to_atr_ratio=market_context.signal_range_to_atr_ratio,
        context_volatility_regime=market_context.volatility_regime,
        level_price=float(level.price) if level is not None else None,
        level_type=level.type if level is not None else None,
        level_weight=float(level.weight) if level is not None else None,
        level_timestamp=int(level.timestamp) if level is not None else None,
        level_datetime=level.datetime if level is not None else None,
        level_confirmed_timestamp=(
            int(level.confirmed_timestamp)
            if level is not None
            else None
        ),
        level_confirmed_datetime=(
            level.confirmed_datetime
            if level is not None
            else None
        ),
        level_to_entry_abs=level_to_entry_abs,
        level_to_entry_pct=(
            _pct_of_price(level_to_entry_abs, entry_price)
            if level_to_entry_abs is not None
            else None
        ),
        signal_available_at_timestamp=entry_context.signal_available_at_timestamp,
        signal_available_at=entry_context.signal_available_at,
        take_multiple=take_multiple,
        stop_multiple=stop_multiple,
        rr_ratio=(take_multiple / stop_multiple) if stop_multiple else 0.0,
        entry_timestamp=entry_context.entry_timestamp,
        entry_datetime=entry_context.entry_datetime,
        entry_source=entry_context.entry_source,
        signal_to_entry_minutes=entry_context.signal_to_entry_minutes,
        entry_price=entry_price,
        stop_price=stop_price,
        take_price=take_price,
        signal_risk_per_unit=signal_risk_per_unit,
        risk_per_unit=risk_per_unit,
        risk_pct_from_entry=_pct_of_price(risk_per_unit, entry_price),
        signal_risk_pct_from_entry=_pct_of_price(signal_risk_per_unit, entry_price),
        exit_timestamp=exit_timestamp,
        exit_datetime=exit_datetime,
        closed_at=exit_datetime,
        exit_price=exit_price,
        exit_reason=exit_reason,
        result=_classify_result(pnl_r),
        pnl_abs=pnl_abs,
        pnl_pct=pnl_pct,
        pnl_r=pnl_r,
        pnl_signal_r=pnl_signal_r,
        bars_in_trade=max(exit_index - entry_context.bars_reference_index, 0),
        duration_minutes=max((exit_timestamp - entry_context.entry_timestamp) / 60000.0, 0.0),
        max_drawdown_abs=max_drawdown_abs,
        max_drawdown_pct=(max_drawdown_abs / entry_price) * 100 if entry_price else 0.0,
        max_drawdown_r=max_drawdown_abs / risk_per_unit if risk_per_unit else 0.0,
        max_drawdown_signal_r=(
            max_drawdown_abs / signal_risk_per_unit if signal_risk_per_unit else 0.0
        ),
        max_profit_abs=max_profit_abs,
        max_profit_pct=(max_profit_abs / entry_price) * 100 if entry_price else 0.0,
        max_profit_r=max_profit_abs / risk_per_unit if risk_per_unit else 0.0,
        max_profit_signal_r=(
            max_profit_abs / signal_risk_per_unit if signal_risk_per_unit else 0.0
        ),
        intrabar_conflict=intrabar_conflict,
        intrabar_conflict_reason=intrabar_conflict_reason,
    )


def build_summary(
    *,
    total_signals: int,
    trades: Sequence[SignalBotBacktestTrade],
    skipped_invalid_risk: int,
    skipped_missing_entry_candle: int,
) -> SignalBotBacktestSummary:
    total_trades_opened = len(trades)
    wins = sum(1 for trade in trades if trade.result == "win")
    losses = sum(1 for trade in trades if trade.result == "loss")
    breakevens = sum(1 for trade in trades if trade.result == "breakeven")
    end_of_data_closes = sum(1 for trade in trades if trade.exit_reason == "end_of_data")
    intrabar_conflicts = sum(1 for trade in trades if trade.intrabar_conflict)
    total_pnl_r = sum(trade.pnl_r for trade in trades)
    total_pnl_signal_r = sum(trade.pnl_signal_r for trade in trades)
    winning_trades = [trade for trade in trades if trade.pnl_r > 0]
    losing_trades = [trade for trade in trades if trade.pnl_r < 0]

    return SignalBotBacktestSummary(
        total_signals=total_signals,
        total_trades_opened=total_trades_opened,
        skipped_invalid_risk=skipped_invalid_risk,
        skipped_missing_entry_candle=skipped_missing_entry_candle,
        wins=wins,
        losses=losses,
        breakevens=breakevens,
        end_of_data_closes=end_of_data_closes,
        intrabar_conflicts=intrabar_conflicts,
        win_rate=(wins / total_trades_opened) * 100 if total_trades_opened else 0.0,
        total_pnl_r=total_pnl_r,
        total_pnl_signal_r=total_pnl_signal_r,
        average_pnl_r=total_pnl_r / total_trades_opened if total_trades_opened else 0.0,
        average_pnl_signal_r=(
            total_pnl_signal_r / total_trades_opened if total_trades_opened else 0.0
        ),
        average_win_r=(
            sum(trade.pnl_r for trade in winning_trades) / len(winning_trades)
            if winning_trades
            else 0.0
        ),
        average_loss_r=(
            sum(trade.pnl_r for trade in losing_trades) / len(losing_trades)
            if losing_trades
            else 0.0
        ),
        profit_factor=_profit_factor(trades),
        max_equity_drawdown_r=_max_equity_drawdown_r(trades),
        average_max_drawdown_r=(
            sum(trade.max_drawdown_r for trade in trades) / total_trades_opened
            if total_trades_opened
            else 0.0
        ),
        average_max_profit_r=(
            sum(trade.max_profit_r for trade in trades) / total_trades_opened
            if total_trades_opened
            else 0.0
        ),
        counts_by_pattern=dict(Counter(trade.pattern for trade in trades)),
        counts_by_symbol=dict(Counter(trade.symbol for trade in trades)),
        counts_by_timeframe=dict(Counter(trade.timeframe for trade in trades)),
        counts_by_level_weight=dict(
            Counter(
                (
                    f"{float(trade.level_weight):g}"
                    if trade.level_weight is not None
                    else "none"
                )
                for trade in trades
            )
        ),
        counts_by_level_type=dict(
            Counter(
                trade.level_type if trade.level_type is not None else "none"
                for trade in trades
            )
        ),
    )


def filter_closed_candles(
    candles: Sequence[Candle],
    *,
    now_ms: int | None = None,
) -> list[Candle]:
    return [
        candle
        for candle in candles
        if candle.timeframe is not None
        and is_candle_closed(candle.timestamp, candle.timeframe, now_ms=now_ms)
    ]


def run_backtest(config: SignalBotBacktestConfig) -> SignalBotBacktestResult:
    connector = create_connector(config.exchange)
    variant_keys = build_variant_keys(config)
    trades_by_variant: dict[tuple[float, float], list[SignalBotBacktestTrade]] = {
        variant_key: []
        for variant_key in variant_keys
    }
    series_stats: list[SignalBotSeriesStats] = []
    total_signals = 0
    skipped_invalid_risk = 0
    skipped_missing_entry_candle = 0
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    for symbol in config.symbols:
        execution_candles: list[Candle] | None = None
        if config.execution_timeframe is not None:
            execution_candles = filter_closed_candles(
                fetch_historical_candles(
                    connector,
                    symbol,
                    config.execution_timeframe,
                    config.normalized_date_from_utc,
                    config.normalized_date_to_utc,
                    fetch_limit=config.fetch_limit,
                ),
                now_ms=now_ms,
            )
        for timeframe in config.timeframes:
            candles = fetch_historical_candles(
                connector,
                symbol,
                timeframe,
                config.normalized_date_from_utc,
                config.normalized_date_to_utc,
                fetch_limit=config.fetch_limit,
            )
            closed_candles = filter_closed_candles(candles, now_ms=now_ms)
            detected_signals = collect_filtered_signals(
                closed_candles,
                patterns=config.patterns,
                min_metric_increase_pct=config.min_metric_increase_pct,
                use_levels=config.use_levels,
                min_level_weight=config.min_level_weight,
            )

            primary_variant_key = (config.take_multiple, config.stop_multiple)
            primary_trades_before = len(trades_by_variant[primary_variant_key])
            skipped_before = skipped_invalid_risk
            skipped_missing_before = skipped_missing_entry_candle
            filtered_signal_count = 0

            for detected_signal in detected_signals:
                market_context = build_signal_market_context(
                    closed_candles,
                    detected_signal.candle_index,
                )
                if not signal_passes_context_filters(
                    detected_signal,
                    market_context,
                    config,
                ):
                    continue
                filtered_signal_count += 1

                entry_context = build_entry_context(
                    detected_signal,
                    closed_candles,
                    execution_candles=execution_candles,
                    execution_timeframe=config.execution_timeframe,
                )
                if entry_context is None:
                    skipped_missing_entry_candle += 1
                    continue

                invalid_risk = False
                for take_multiple, stop_multiple in variant_keys:
                    trade = simulate_trade(
                        detected_signal,
                        closed_candles,
                        execution_candles=execution_candles,
                        execution_timeframe=config.execution_timeframe,
                        entry_context=entry_context,
                        market_context=market_context,
                        take_multiple=take_multiple,
                        stop_multiple=stop_multiple,
                    )
                    if trade is None:
                        invalid_risk = True
                        continue
                    trades_by_variant[(take_multiple, stop_multiple)].append(trade)
                if invalid_risk:
                    skipped_invalid_risk += 1
            total_signals += filtered_signal_count

            series_stats.append(
                SignalBotSeriesStats(
                    symbol=symbol,
                    timeframe=timeframe,
                    candle_count=len(closed_candles),
                    signal_count=filtered_signal_count,
                    trade_count=(
                        len(trades_by_variant[primary_variant_key])
                        - primary_trades_before
                    ),
                    skipped_invalid_risk=skipped_invalid_risk - skipped_before,
                    skipped_missing_entry_candle=(
                        skipped_missing_entry_candle - skipped_missing_before
                    ),
                )
            )

            print(
                f"[{symbol} {timeframe}] "
                f"candles={len(closed_candles)} "
                f"signals={filtered_signal_count} "
                f"trades={len(trades_by_variant[primary_variant_key]) - primary_trades_before}"
            )

    variant_summaries = [
        SignalBotVariantSummary(
            take_multiple=take_multiple,
            stop_multiple=stop_multiple,
            summary=build_summary(
                total_signals=total_signals,
                trades=trades_by_variant[(take_multiple, stop_multiple)],
                skipped_invalid_risk=skipped_invalid_risk,
                skipped_missing_entry_candle=skipped_missing_entry_candle,
            ),
        )
        for take_multiple, stop_multiple in variant_keys
    ]
    take_variant_summaries = [
        variant
        for variant in variant_summaries
        if variant.stop_multiple == config.stop_multiple
    ]
    primary_trades = sorted(
        trades_by_variant[(config.take_multiple, config.stop_multiple)],
        key=lambda trade: (
            trade.entry_timestamp,
            trade.signal_timestamp,
            trade.symbol,
            trade.timeframe,
            trade.pattern,
        ),
    )
    summary = next(
        variant.summary
        for variant in variant_summaries
        if (
            variant.take_multiple == config.take_multiple
            and variant.stop_multiple == config.stop_multiple
        )
    )
    return SignalBotBacktestResult(
        config=config,
        summary=summary,
        variant_summaries=variant_summaries,
        take_variant_summaries=take_variant_summaries,
        series=series_stats,
        trades=primary_trades,
        variant_trades=(
            {
                format_variant_key(take_multiple, stop_multiple): sorted(
                    trades_by_variant[(take_multiple, stop_multiple)],
                    key=lambda trade: (
                        trade.entry_timestamp,
                        trade.signal_timestamp,
                        trade.symbol,
                        trade.timeframe,
                        trade.pattern,
                    ),
                )
                for take_multiple, stop_multiple in variant_keys
            }
            if config.save_all_variant_trades
            else None
        ),
    )


def save_result(result: SignalBotBacktestResult, output_file: str | Path | None = None) -> Path:
    path = Path(output_file or result.config.output_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(result), ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    return path


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    config = build_config(args)
    result = run_backtest(config)
    output_path = save_result(result)

    print(f"Output file: {output_path}")
    print(f"Signals: {result.summary.total_signals}")
    print(f"Trades: {result.summary.total_trades_opened}")
    print(
        "Wins/Losses/BE: "
        f"{result.summary.wins}/"
        f"{result.summary.losses}/"
        f"{result.summary.breakevens}"
    )
    print(f"Win rate: {result.summary.win_rate:.2f}%")
    print(f"Total PnL (R): {result.summary.total_pnl_r:.4f}")
    if result.config.use_levels:
        print(
            "Level mix: "
            f"weights={result.summary.counts_by_level_weight} "
            f"types={result.summary.counts_by_level_type}"
        )
    if len(result.variant_summaries) > 1:
        print("Setup comparison:")
        for variant in result.variant_summaries:
            print(
                f"  take={variant.take_multiple:.2f} stop={variant.stop_multiple:.2f} -> "
                f"win_rate={variant.summary.win_rate:.2f}% "
                f"total_pnl_r={variant.summary.total_pnl_r:.4f}"
            )


__all__ = [
    "DEFAULT_PATTERNS",
    "DEFAULT_SYMBOLS",
    "DEFAULT_TIMEFRAMES",
    "DetectedSignal",
    "EntryContext",
    "SignalBotBacktestConfig",
    "SignalBotBacktestResult",
    "SignalBotBacktestSummary",
    "SignalBotVariantSummary",
    "SignalBotBacktestTrade",
    "SignalBotSeriesStats",
    "build_config",
    "build_entry_context",
    "build_signal_market_context",
    "build_summary",
    "build_variant_keys",
    "collect_filtered_signals",
    "find_entry_candle_index",
    "filter_closed_candles",
    "format_variant_key",
    "main",
    "normalize_date_range",
    "normalize_stop_multiples",
    "normalize_take_multiples",
    "run_backtest",
    "save_result",
    "signal_available_timestamp",
    "signal_passes_context_filters",
    "simulate_trade",
    "SignalBotVariantSummary",
]
