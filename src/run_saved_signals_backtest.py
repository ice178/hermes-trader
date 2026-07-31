#!/usr/bin/env python
"""Run a historical backtest using previously saved signals."""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from hermes_trading.backtest import (
    BacktestConfig,
    BacktestResult,
    StrategyConfig,
    build_signal_events_from_saved_records,
    build_summary,
    create_connector,
    fetch_historical_candles,
    load_saved_signal_records,
    render_summary_text,
    save_backtest_artifacts,
    save_strategy_comparison,
    simulate_candles,
)
from hermes_trading.backtest.saved_signals import SavedSignalRecord

DEFAULT_TAKE_PROFITS = (0.25, 0.5, 0.7, 0.75, 1.0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--signals-file", required=True)
    parser.add_argument("--exchange", default="binance")
    parser.add_argument("--date-from")
    parser.add_argument("--date-to")
    parser.add_argument("--fetch-limit", type=int, default=1000)
    parser.add_argument("--output-dir", default="backtest_results/saved_signals")
    parser.add_argument("--symbols", nargs="+")
    parser.add_argument("--timeframes", nargs="+")
    parser.add_argument("--patterns", nargs="+")
    parser.add_argument(
        "--min-metric-increase-pct",
        type=float,
        default=10.0,
    )
    parser.add_argument(
        "--take-profit-r",
        nargs="+",
        type=float,
        default=list(DEFAULT_TAKE_PROFITS),
    )
    parser.add_argument("--take-step-r", type=float, default=0.25)
    parser.add_argument("--allow-long", action="store_true")
    parser.add_argument("--allow-short", action="store_true")
    parser.add_argument("--no-export-trades", action="store_true")
    parser.add_argument("--no-export-summary", action="store_true")
    return parser.parse_args()


def _direction_filter(args: argparse.Namespace) -> tuple[str, ...]:
    directions: list[str] = []
    if args.allow_long:
        directions.append("long")
    if args.allow_short:
        directions.append("short")
    if not directions:
        return ("long", "short")
    return tuple(directions)


def _exit_model_name(take_profit_r: float) -> str:
    return f"fixed_take_{take_profit_r:.2f}R"


def _dedupe_take_profits(values: list[float]) -> list[float]:
    deduped: list[float] = []
    seen: set[float] = set()
    for value in values:
        if value <= 0:
            raise ValueError("take-profit-r values must be positive.")
        rounded = round(value, 10)
        if rounded in seen:
            continue
        seen.add(rounded)
        deduped.append(rounded)
    return deduped


def _filter_records(
    records: list[SavedSignalRecord],
    *,
    symbols: list[str] | None,
    timeframes: list[str] | None,
    patterns: list[str] | None,
    directions: tuple[str, ...],
) -> list[SavedSignalRecord]:
    allowed_symbols = set(symbols) if symbols is not None else None
    allowed_timeframes = set(timeframes) if timeframes is not None else None
    allowed_patterns = set(patterns) if patterns is not None else None
    allowed_directions = set(directions)

    return [
        record
        for record in records
        if (allowed_symbols is None or record.symbol in allowed_symbols)
        and (allowed_timeframes is None or record.timeframe in allowed_timeframes)
        and (allowed_patterns is None or record.pattern in allowed_patterns)
        and record.direction in allowed_directions
    ]


def _resolved_date_from(
    records: list[SavedSignalRecord],
    explicit_date_from: str | None,
) -> str:
    if explicit_date_from is not None:
        return explicit_date_from
    earliest = min(record.signal_datetime for record in records)
    return earliest


def _resolved_date_to(explicit_date_to: str | None) -> str:
    if explicit_date_to is not None:
        return explicit_date_to
    return datetime.now(timezone.utc).isoformat()


def main() -> None:
    args = parse_args()
    take_profit_values = _dedupe_take_profits(args.take_profit_r)
    directions = _direction_filter(args)
    signals_path = Path(args.signals_file)
    output_dir = Path(args.output_dir)

    all_records = load_saved_signal_records(signals_path)
    filtered_records = _filter_records(
        all_records,
        symbols=args.symbols,
        timeframes=args.timeframes,
        patterns=args.patterns,
        directions=directions,
    )
    if not filtered_records:
        raise RuntimeError("No saved signals matched the provided filters.")

    date_from = _resolved_date_from(filtered_records, args.date_from)
    date_to = _resolved_date_to(args.date_to)
    symbols = tuple(sorted({record.symbol for record in filtered_records}))
    timeframes = tuple(sorted({record.timeframe for record in filtered_records}))
    patterns = tuple(sorted({record.pattern for record in filtered_records}))

    config = BacktestConfig(
        exchange=args.exchange,
        symbols=symbols,
        timeframes=timeframes,
        date_from=date_from,
        date_to=date_to,
        fetch_limit=args.fetch_limit,
        output_dir=output_dir,
        export_trades=not args.no_export_trades,
        export_summary=not args.no_export_summary,
    )

    connector = create_connector(config.exchange)
    records_by_series: dict[tuple[str, str], list[SavedSignalRecord]] = defaultdict(list)
    for record in filtered_records:
        records_by_series[(record.symbol, record.timeframe)].append(record)

    total_candles = 0
    total_events = 0
    total_missing_events = 0
    series_cache = []

    for (symbol, timeframe), series_records in sorted(records_by_series.items()):
        series_date_from = _resolved_date_from(series_records, args.date_from)
        candles = fetch_historical_candles(
            connector,
            symbol,
            timeframe,
            series_date_from,
            date_to,
            fetch_limit=config.fetch_limit,
        )
        total_candles += len(candles)

        available_timestamps = {candle.timestamp for candle in candles}
        events = [
            event
            for event in build_signal_events_from_saved_records(series_records)
            if event.signal_candle.timestamp in available_timestamps
        ]
        missing_events = len(series_records) - len(events)
        total_events += len(events)
        total_missing_events += missing_events
        print(
            f"[{symbol} {timeframe}] "
            f"candles={len(candles)} "
            f"saved_signals={len(series_records)} "
            f"usable_signal_events={len(events)} "
            f"missing_signal_candles={missing_events}"
        )
        series_cache.append((symbol, timeframe, candles, events))

    if total_candles == 0:
        raise RuntimeError("No candles were loaded for the requested range.")
    if total_events == 0:
        raise RuntimeError("No saved signals could be matched to loaded candles.")
    if total_missing_events > 0:
        print(f"Skipped saved signals without a matching candle: {total_missing_events}")

    results: list[BacktestResult] = []
    for take_profit_r in take_profit_values:
        strategy = StrategyConfig(
            patterns=patterns,
            min_metric_increase_pct=args.min_metric_increase_pct,
            take_profit_r=take_profit_r,
            take_step_r=args.take_step_r,
            direction_filter=directions,
            exit_model_name=_exit_model_name(take_profit_r),
        )

        trades = []
        print(f"\n=== Exit Model: {strategy.exit_model_name} ===")
        for symbol, timeframe, candles, events in series_cache:
            series_trades = simulate_candles(candles, events, strategy)
            trades.extend(series_trades)
            print(
                f"[{strategy.exit_model_name} {symbol} {timeframe}] "
                f"trades={len(series_trades)}"
            )

        trades.sort(key=lambda trade: (trade.entry_timestamp, trade.symbol, trade.timeframe))
        summary = build_summary(trades, config, strategy)
        result = BacktestResult(
            config=replace(config, output_dir=output_dir / strategy.exit_model_name),
            strategy=strategy,
            trades=trades,
            summary=summary,
        )
        save_backtest_artifacts(result)
        results.append(result)
        print(render_summary_text(summary))

    save_strategy_comparison(results, output_dir)


if __name__ == "__main__":
    main()
