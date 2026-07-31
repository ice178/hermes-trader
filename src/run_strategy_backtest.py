#!/usr/bin/env python
"""Run a historical backtest using signals from signals_bot logic."""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from hermes_trading.backtest import (
    BacktestConfig,
    BacktestResult,
    StrategyConfig,
    build_signal_events,
    build_summary,
    create_connector,
    fetch_historical_candles,
    render_summary_text,
    save_backtest_artifacts,
    save_strategy_comparison,
    simulate_candles,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exchange", default="binance")
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--timeframes", nargs="+", required=True)
    parser.add_argument("--date-from", required=True)
    parser.add_argument("--date-to", required=True)
    parser.add_argument("--fetch-limit", type=int, default=1000)
    parser.add_argument("--output-dir", default="backtest_results")
    parser.add_argument("--patterns", nargs="+", default=["pin_bar", "railway_tracks"])
    parser.add_argument("--min-metric-increase-pct", type=float, default=10.0)
    parser.add_argument("--take-profit-r", type=float)
    parser.add_argument("--compare-fixed-takes-up-to", type=float)
    parser.add_argument("--fixed-take-step", type=float, default=0.5)
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


def _exit_model_name(take_profit_r: float | None) -> str:
    if take_profit_r is None:
        return "hold_to_stop"
    return f"fixed_take_{take_profit_r:.2f}R"


def _build_strategy_variants(
    args: argparse.Namespace,
    base_strategy: StrategyConfig,
) -> list[StrategyConfig]:
    if args.take_profit_r is not None and args.compare_fixed_takes_up_to is not None:
        raise ValueError("Use either --take-profit-r or --compare-fixed-takes-up-to, not both.")

    if args.take_profit_r is not None:
        return [
            replace(
                base_strategy,
                take_profit_r=args.take_profit_r,
                exit_model_name=_exit_model_name(args.take_profit_r),
            )
        ]

    if args.compare_fixed_takes_up_to is None:
        return [replace(base_strategy, exit_model_name=_exit_model_name(None))]

    if args.fixed_take_step <= 0:
        raise ValueError("--fixed-take-step must be positive.")
    if args.compare_fixed_takes_up_to <= 0:
        raise ValueError("--compare-fixed-takes-up-to must be positive.")

    variants = [replace(base_strategy, exit_model_name=_exit_model_name(None))]
    current = args.fixed_take_step
    while current <= args.compare_fixed_takes_up_to + 1e-9:
        rounded = round(current, 10)
        variants.append(
            replace(
                base_strategy,
                take_profit_r=rounded,
                exit_model_name=_exit_model_name(rounded),
            )
        )
        current += args.fixed_take_step
    return variants


def main() -> None:
    args = parse_args()

    config = BacktestConfig(
        exchange=args.exchange,
        symbols=tuple(args.symbols),
        timeframes=tuple(args.timeframes),
        date_from=args.date_from,
        date_to=args.date_to,
        fetch_limit=args.fetch_limit,
        output_dir=Path(args.output_dir),
        export_trades=not args.no_export_trades,
        export_summary=not args.no_export_summary,
    )
    strategy = StrategyConfig(
        patterns=tuple(args.patterns),
        min_metric_increase_pct=args.min_metric_increase_pct,
        take_step_r=args.take_step_r,
        direction_filter=_direction_filter(args),
    )
    strategy_variants = _build_strategy_variants(args, strategy)

    connector = create_connector(config.exchange)
    total_candles = 0
    total_events = 0
    series_cache = []

    for symbol in config.symbols:
        for timeframe in config.timeframes:
            candles = fetch_historical_candles(
                connector,
                symbol,
                timeframe,
                config.date_from,
                config.date_to,
                fetch_limit=config.fetch_limit,
            )
            total_candles += len(candles)
            events = build_signal_events(
                candles,
                strategy,
                symbol=symbol,
                timeframe=timeframe,
            )
            total_events += len(events)
            print(
                f"[{symbol} {timeframe}] "
                f"candles={len(candles)} "
                f"signal_events={len(events)}"
            )
            series_cache.append((symbol, timeframe, candles, events))

    if total_candles == 0:
        raise RuntimeError(
            "No candles were loaded for the requested range. "
            "If you are using BingX, switch to --exchange binance or narrow the date range."
        )

    if total_events == 0:
        print(
            "No signal events passed the current filters. "
            "Check the pattern set and min_metric_increase_pct."
        )

    results: list[BacktestResult] = []
    for strategy_variant in strategy_variants:
        trades = []
        print(f"\n=== Exit Model: {strategy_variant.exit_model_name} ===")
        for symbol, timeframe, candles, events in series_cache:
            series_trades = simulate_candles(candles, events, strategy_variant)
            trades.extend(series_trades)
            print(
                f"[{strategy_variant.exit_model_name} {symbol} {timeframe}] "
                f"trades={len(series_trades)}"
            )

        trades.sort(key=lambda trade: (trade.entry_timestamp, trade.symbol, trade.timeframe))
        summary = build_summary(trades, config, strategy_variant)
        result_config = replace(
            config,
            output_dir=(
                config.output_dir
                if len(strategy_variants) == 1
                else config.output_dir / strategy_variant.exit_model_name
            ),
        )
        result = BacktestResult(
            config=result_config,
            strategy=strategy_variant,
            trades=trades,
            summary=summary,
        )
        save_backtest_artifacts(result)
        results.append(result)
        print(render_summary_text(summary))

    save_strategy_comparison(results, config.output_dir)


if __name__ == "__main__":
    main()
