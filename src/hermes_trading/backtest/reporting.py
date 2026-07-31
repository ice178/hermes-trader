"""Reporting helpers for backtest output."""

from __future__ import annotations

import csv
import json
import statistics
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path

from .models import BacktestConfig, BacktestResult, BacktestSummary, StrategyConfig, TradeRecord


def _round(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 6)


def _max_streak(trades: list[TradeRecord], target: str) -> int:
    best = 0
    current = 0
    for trade in trades:
        if trade.result == target:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def _step_sort_key(step: str) -> float:
    return float(step[:-1])


def build_summary(
    trades: list[TradeRecord],
    config: BacktestConfig,
    strategy: StrategyConfig,
) -> BacktestSummary:
    """Aggregate summary metrics across all finalized trades."""

    del config
    del strategy

    total_trades = len(trades)
    long_trades = sum(1 for trade in trades if trade.direction == "long")
    short_trades = total_trades - long_trades
    win_trades = sum(1 for trade in trades if trade.result == "win")
    loss_trades = sum(1 for trade in trades if trade.result == "loss")
    breakeven_trades = sum(1 for trade in trades if trade.result == "breakeven")
    forced_close_trades = sum(1 for trade in trades if trade.exit_reason == "end_of_data")

    total_pnl_r = sum(trade.pnl_r for trade in trades)
    average_pnl_r = total_pnl_r / total_trades if total_trades else 0.0
    average_mae_r = (
        sum(trade.mae_r for trade in trades) / total_trades if total_trades else 0.0
    )
    average_mfe_r = (
        sum(trade.mfe_r for trade in trades) / total_trades if total_trades else 0.0
    )

    positive_pnl = sum(trade.pnl_r for trade in trades if trade.pnl_r > 0)
    negative_pnl = sum(trade.pnl_r for trade in trades if trade.pnl_r < 0)
    profit_factor = None
    if negative_pnl < 0:
        profit_factor = positive_pnl / abs(negative_pnl)
    elif positive_pnl > 0:
        profit_factor = float("inf")

    pattern_counts = dict(Counter(trade.pattern for trade in trades))
    symbol_counts = dict(Counter(trade.symbol for trade in trades))
    best_take_step_counts = dict(
        Counter(f"{trade.best_take_step_r:.2f}R" for trade in trades)
    )

    step_hits: dict[str, list[dict[str, int]]] = defaultdict(list)
    for trade in trades:
        for step, payload in trade.r_step_hit_times.items():
            step_hits[step].append(payload)

    r_step_stats: dict[str, dict[str, float | int | None]] = {}
    for step in sorted(step_hits, key=_step_sort_key):
        payloads = step_hits[step]
        bars = [item["bars"] for item in payloads]
        milliseconds = [item["milliseconds"] for item in payloads]
        r_step_stats[step] = {
            "trade_count": len(payloads),
            "average_bars": _round(sum(bars) / len(bars)) if bars else None,
            "median_bars": _round(statistics.median(bars)) if bars else None,
            "average_milliseconds": _round(sum(milliseconds) / len(milliseconds))
            if milliseconds
            else None,
            "median_milliseconds": _round(statistics.median(milliseconds))
            if milliseconds
            else None,
        }

    same_direction_internal_signals = sum(
        trade.same_direction_signal_count for trade in trades
    )
    opposite_direction_internal_signals = sum(
        trade.opposite_direction_signal_count for trade in trades
    )
    intrabar_conflicts = sum(trade.intrabar_conflict_count for trade in trades)

    return BacktestSummary(
        total_trades=total_trades,
        long_trades=long_trades,
        short_trades=short_trades,
        win_trades=win_trades,
        loss_trades=loss_trades,
        breakeven_trades=breakeven_trades,
        forced_close_trades=forced_close_trades,
        win_rate=(win_trades / total_trades) * 100 if total_trades else 0.0,
        total_pnl_r=total_pnl_r,
        average_pnl_r=average_pnl_r,
        average_mae_r=average_mae_r,
        average_mfe_r=average_mfe_r,
        max_consecutive_losses=_max_streak(trades, "loss"),
        max_consecutive_wins=_max_streak(trades, "win"),
        profit_factor=profit_factor,
        expectancy_r=average_pnl_r,
        average_bars_in_trade=(
            sum(trade.bars_in_trade for trade in trades) / total_trades
            if total_trades
            else 0.0
        ),
        pattern_counts=pattern_counts,
        symbol_counts=symbol_counts,
        best_take_step_counts=best_take_step_counts,
        r_step_stats=r_step_stats,
        same_direction_internal_signals=same_direction_internal_signals,
        opposite_direction_internal_signals=opposite_direction_internal_signals,
        intrabar_conflicts=intrabar_conflicts,
    )


def render_summary_text(summary: BacktestSummary) -> str:
    """Format a concise console summary."""

    profit_factor = (
        "inf"
        if summary.profit_factor == float("inf")
        else f"{summary.profit_factor:.3f}"
        if summary.profit_factor is not None
        else "n/a"
    )
    return "\n".join(
        [
            f"Trades: {summary.total_trades}",
            f"Long/Short: {summary.long_trades}/{summary.short_trades}",
            (
                "Wins/Losses/BE: "
                f"{summary.win_trades}/{summary.loss_trades}/{summary.breakeven_trades}"
            ),
            f"Win rate: {summary.win_rate:.2f}%",
            f"Total PnL (R): {summary.total_pnl_r:.4f}",
            f"Avg PnL (R): {summary.average_pnl_r:.4f}",
            f"Avg MAE/MFE (R): {summary.average_mae_r:.4f}/{summary.average_mfe_r:.4f}",
            f"Profit factor: {profit_factor}",
            f"Max win/loss streak: {summary.max_consecutive_wins}/{summary.max_consecutive_losses}",
            (
                "Internal signals same/opposite: "
                f"{summary.same_direction_internal_signals}/"
                f"{summary.opposite_direction_internal_signals}"
            ),
            f"Intrabar conflicts: {summary.intrabar_conflicts}",
        ]
    )


def _summary_markdown(
    config: BacktestConfig,
    strategy: StrategyConfig,
    summary: BacktestSummary,
) -> str:
    lines = [
        "# Backtest Summary",
        "",
        f"- Exchange: `{config.exchange}`",
        f"- Symbols: `{', '.join(config.symbols)}`",
        f"- Timeframes: `{', '.join(config.timeframes)}`",
        f"- Date range: `{config.date_from}` -> `{config.date_to}`",
        f"- Patterns: `{', '.join(strategy.patterns)}`",
        f"- Metric filter: `{strategy.min_metric_increase_pct:.2f}%`",
        f"- Exit model: `{strategy.exit_model_name}`",
        (
            f"- Take profit: `{strategy.take_profit_r:.2f}R`"
            if strategy.take_profit_r is not None
            else "- Take profit: `disabled`"
        ),
        "",
        "## Results",
        "",
        f"- Total trades: `{summary.total_trades}`",
        f"- Win rate: `{summary.win_rate:.2f}%`",
        f"- Total PnL (R): `{summary.total_pnl_r:.4f}`",
        f"- Avg PnL (R): `{summary.average_pnl_r:.4f}`",
        f"- Avg MAE (R): `{summary.average_mae_r:.4f}`",
        f"- Avg MFE (R): `{summary.average_mfe_r:.4f}`",
        f"- Internal signals same/opposite: `{summary.same_direction_internal_signals}/{summary.opposite_direction_internal_signals}`",
        f"- Intrabar conflicts: `{summary.intrabar_conflicts}`",
        "",
        "## R Step Stats",
        "",
    ]

    if not summary.r_step_stats:
        lines.append("- No R-step hits recorded.")
    else:
        for step, payload in summary.r_step_stats.items():
            lines.append(
                (
                    f"- {step}: count=`{payload['trade_count']}`, "
                    f"avg bars=`{payload['average_bars']}`, "
                    f"median bars=`{payload['median_bars']}`"
                )
            )

    return "\n".join(lines)


def save_backtest_artifacts(result: BacktestResult) -> None:
    """Persist trade and summary output to disk."""

    output_dir = result.config.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    if result.config.export_trades:
        trades_path = output_dir / "trades.json"
        trades_path.write_text(
            json.dumps([asdict(trade) for trade in result.trades], ensure_ascii=True, indent=2),
            encoding="utf-8",
        )

        if result.trades:
            csv_path = output_dir / "trades.csv"
            fieldnames = list(asdict(result.trades[0]).keys())
            with csv_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                for trade in result.trades:
                    row = asdict(trade)
                    for key, value in row.items():
                        if isinstance(value, (dict, list)):
                            row[key] = json.dumps(value, ensure_ascii=True)
                    writer.writerow(row)

    if result.config.export_summary:
        summary_path = output_dir / "summary.json"
        summary_path.write_text(
            json.dumps(
                {
                    "config": asdict(result.config),
                    "strategy": asdict(result.strategy),
                    "summary": asdict(result.summary),
                },
                ensure_ascii=True,
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )

        markdown_path = output_dir / "summary.md"
        markdown_path.write_text(
            _summary_markdown(result.config, result.strategy, result.summary),
            encoding="utf-8",
        )


def save_strategy_comparison(
    results: list[BacktestResult],
    output_dir: Path,
) -> None:
    """Persist a compact comparison across multiple exit models."""

    if len(results) < 2:
        return

    comparison_rows = []
    markdown_lines = [
        "# Exit Model Comparison",
        "",
        "| Model | Take R | Trades | Win Rate | Total R | Avg R | Profit Factor | TP Exits | Stop Exits | End-of-Data |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    for result in results:
        take_profit_exits = sum(
            1 for trade in result.trades if trade.exit_reason == "take_profit"
        )
        stop_exits = sum(1 for trade in result.trades if trade.exit_reason == "stop_loss")
        end_of_data_exits = sum(
            1 for trade in result.trades if trade.exit_reason == "end_of_data"
        )
        profit_factor = (
            "inf"
            if result.summary.profit_factor == float("inf")
            else result.summary.profit_factor
        )

        row = {
            "model": result.strategy.exit_model_name,
            "take_profit_r": result.strategy.take_profit_r,
            "total_trades": result.summary.total_trades,
            "win_rate": round(result.summary.win_rate, 6),
            "total_pnl_r": round(result.summary.total_pnl_r, 6),
            "average_pnl_r": round(result.summary.average_pnl_r, 6),
            "profit_factor": profit_factor,
            "take_profit_exits": take_profit_exits,
            "stop_loss_exits": stop_exits,
            "end_of_data_exits": end_of_data_exits,
        }
        comparison_rows.append(row)

        take_r = (
            "hold"
            if result.strategy.take_profit_r is None
            else f"{result.strategy.take_profit_r:.2f}"
        )
        profit_factor_text = (
            "inf"
            if result.summary.profit_factor == float("inf")
            else f"{result.summary.profit_factor:.3f}"
            if result.summary.profit_factor is not None
            else "n/a"
        )
        markdown_lines.append(
            (
                f"| {result.strategy.exit_model_name} | {take_r} | "
                f"{result.summary.total_trades} | {result.summary.win_rate:.2f}% | "
                f"{result.summary.total_pnl_r:.4f} | {result.summary.average_pnl_r:.4f} | "
                f"{profit_factor_text} | {take_profit_exits} | {stop_exits} | {end_of_data_exits} |"
            )
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "comparison.json").write_text(
        json.dumps(comparison_rows, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    (output_dir / "comparison.md").write_text(
        "\n".join(markdown_lines),
        encoding="utf-8",
    )
