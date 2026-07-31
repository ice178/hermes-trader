"""Analyze saved signals_bot backtest results."""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
from typing import Any, Callable, Sequence

from .signals_bot_backtest import format_variant_key

DEFAULT_INPUT_PATH = Path(__file__).resolve().parents[1] / "signals_bot_backtest_results.json"
DEFAULT_OUTPUT_PATH = Path(__file__).resolve().parents[1] / "signals_bot_backtest_analysis.json"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-file", default=str(DEFAULT_INPUT_PATH))
    parser.add_argument("--output-file", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--bucket-count", type=int, default=5)
    parser.add_argument("--min-group-trades", type=int, default=5)
    parser.add_argument("--take-multiple", type=float)
    parser.add_argument("--stop-multiple", type=float)
    return parser.parse_args(argv)


def load_backtest_result(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def extract_variant_summaries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    variants = payload.get("variant_summaries")
    if variants is not None:
        return list(variants)

    config = payload.get("config", {})
    default_stop_multiple = float(config.get("stop_multiple", 1.0))
    return [
        {
            "take_multiple": float(item["take_multiple"]),
            "stop_multiple": default_stop_multiple,
            "summary": item["summary"],
        }
        for item in payload.get("take_variant_summaries", [])
    ]


def select_variant_trades(
    payload: dict[str, Any],
    *,
    take_multiple: float | None = None,
    stop_multiple: float | None = None,
) -> list[dict[str, Any]]:
    if take_multiple is None and stop_multiple is None:
        return list(payload.get("trades", []))

    if take_multiple is None or stop_multiple is None:
        raise ValueError("take_multiple and stop_multiple must be provided together")

    variant_trades = payload.get("variant_trades")
    if variant_trades is not None:
        variant_key = format_variant_key(float(take_multiple), float(stop_multiple))
        if variant_key not in variant_trades:
            raise ValueError(f"variant trades not found for {variant_key}")
        return list(variant_trades[variant_key])

    config = payload.get("config", {})
    if (
        float(config.get("take_multiple", 1.0)) == float(take_multiple)
        and float(config.get("stop_multiple", 1.0)) == float(stop_multiple)
    ):
        return list(payload.get("trades", []))

    raise ValueError(
        "variant_trades are not present in this export; rerun backtest with "
        "--save-all-variant-trades or analyze the primary setup only"
    )


def _summary_snapshot(variant: dict[str, Any]) -> dict[str, Any]:
    summary = variant["summary"]
    return {
        "take_multiple": float(variant["take_multiple"]),
        "stop_multiple": float(variant.get("stop_multiple", 1.0)),
        "rr_ratio": (
            float(variant["take_multiple"]) / float(variant.get("stop_multiple", 1.0))
            if float(variant.get("stop_multiple", 1.0))
            else 0.0
        ),
        "total_trades_opened": int(summary.get("total_trades_opened", 0)),
        "win_rate": float(summary.get("win_rate", 0.0)),
        "total_pnl_r": float(summary.get("total_pnl_r", 0.0)),
        "total_pnl_signal_r": float(summary.get("total_pnl_signal_r", 0.0)),
        "average_pnl_r": float(summary.get("average_pnl_r", 0.0)),
        "profit_factor": summary.get("profit_factor"),
        "max_equity_drawdown_r": float(summary.get("max_equity_drawdown_r", 0.0)),
        "average_win_r": float(summary.get("average_win_r", 0.0)),
        "average_loss_r": float(summary.get("average_loss_r", 0.0)),
    }


def _sort_profit_factor(value: Any) -> tuple[int, float]:
    if value is None:
        return (0, float("-inf"))
    return (1, float(value))


def _mean(trades: Sequence[dict[str, Any]], field: str) -> float | None:
    values = [float(trade[field]) for trade in trades if trade.get(field) is not None]
    if not values:
        return None
    return sum(values) / len(values)


def summarize_trade_group(group: str, trades: Sequence[dict[str, Any]]) -> dict[str, Any]:
    total_trades = len(trades)
    wins = sum(1 for trade in trades if float(trade.get("pnl_r", 0.0)) > 0)
    losses = sum(1 for trade in trades if float(trade.get("pnl_r", 0.0)) < 0)
    breakevens = total_trades - wins - losses
    total_pnl_r = sum(float(trade.get("pnl_r", 0.0)) for trade in trades)

    return {
        "group": group,
        "total_trades": total_trades,
        "wins": wins,
        "losses": losses,
        "breakevens": breakevens,
        "win_rate": (wins / total_trades) * 100 if total_trades else 0.0,
        "loss_rate": (losses / total_trades) * 100 if total_trades else 0.0,
        "total_pnl_r": total_pnl_r,
        "average_pnl_r": total_pnl_r / total_trades if total_trades else 0.0,
        "average_signal_range_pct": _mean(trades, "signal_range_pct"),
        "average_risk_pct_from_entry": _mean(trades, "risk_pct_from_entry"),
        "average_signal_volatility_increase_max_pct": _mean(
            trades,
            "signal_volatility_increase_max_pct",
        ),
        "average_signal_volume_increase_max_pct": _mean(
            trades,
            "signal_volume_increase_max_pct",
        ),
        "average_context_range_position_pct": _mean(
            trades,
            "context_range_position_pct",
        ),
        "average_context_atr_pct": _mean(
            trades,
            "context_atr_pct",
        ),
        "average_context_signal_range_to_atr_ratio": _mean(
            trades,
            "context_signal_range_to_atr_ratio",
        ),
    }


def _group_sort_key(group_value: str) -> tuple[int, float | str]:
    try:
        return (0, float(group_value))
    except ValueError:
        return (1, group_value)


def summarize_groups(
    trades: Sequence[dict[str, Any]],
    group_builder: Callable[[dict[str, Any]], str | None],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trade in trades:
        group = group_builder(trade)
        if group is None:
            continue
        grouped[group].append(trade)

    return [
        summarize_trade_group(group, grouped[group])
        for group in sorted(grouped, key=_group_sort_key)
    ]


def summarize_quantile_groups(
    trades: Sequence[dict[str, Any]],
    field: str,
    *,
    bucket_count: int,
) -> list[dict[str, Any]]:
    indexed_values = [
        (index, float(trade[field]))
        for index, trade in enumerate(trades)
        if trade.get(field) is not None
    ]
    if not indexed_values:
        return []

    bucket_total = max(1, min(bucket_count, len(indexed_values)))
    sorted_values = sorted(indexed_values, key=lambda item: item[1])
    grouped_indexes: dict[int, list[tuple[int, float]]] = defaultdict(list)
    for rank, indexed_value in enumerate(sorted_values):
        bucket_index = min((rank * bucket_total) // len(sorted_values), bucket_total - 1)
        grouped_indexes[bucket_index].append(indexed_value)

    summaries: list[dict[str, Any]] = []
    for bucket_index in sorted(grouped_indexes):
        bucket_entries = grouped_indexes[bucket_index]
        bucket_values = [value for _, value in bucket_entries]
        label = f"q{bucket_index + 1}:{min(bucket_values):.4f}..{max(bucket_values):.4f}"
        bucket_trades = [trades[index] for index, _ in bucket_entries]
        summaries.append(summarize_trade_group(label, bucket_trades))
    return summaries


def extract_filter_candidates(
    grouped_summaries: Sequence[dict[str, Any]],
    *,
    overall_loss_rate: float,
    min_group_trades: int,
    top_n: int,
) -> list[dict[str, Any]]:
    candidates = [
        item
        for item in grouped_summaries
        if item["total_trades"] >= min_group_trades
        and item["loss_rate"] > overall_loss_rate
        and item["total_pnl_r"] < 0
    ]
    return sorted(
        candidates,
        key=lambda item: (
            item["loss_rate"],
            -item["total_pnl_r"],
            item["total_trades"],
        ),
        reverse=True,
    )[:top_n]


def analyze_backtest_result(
    payload: dict[str, Any],
    *,
    top_n: int = 10,
    bucket_count: int = 5,
    min_group_trades: int = 5,
    selected_take_multiple: float | None = None,
    selected_stop_multiple: float | None = None,
) -> dict[str, Any]:
    variants = extract_variant_summaries(payload)
    variant_snapshots = [_summary_snapshot(variant) for variant in variants]
    trades = select_variant_trades(
        payload,
        take_multiple=selected_take_multiple,
        stop_multiple=selected_stop_multiple,
    )
    summary = payload.get("summary", {})
    selected_variant = {
        "take_multiple": (
            float(selected_take_multiple)
            if selected_take_multiple is not None
            else float(payload.get("config", {}).get("take_multiple", 1.0))
        ),
        "stop_multiple": (
            float(selected_stop_multiple)
            if selected_stop_multiple is not None
            else float(payload.get("config", {}).get("stop_multiple", 1.0))
        ),
    }

    grouped_stats = {
        "by_pattern": summarize_groups(trades, lambda trade: str(trade["pattern"])),
        "by_timeframe": summarize_groups(
            trades,
            lambda trade: str(trade.get("signal_timeframe") or trade.get("timeframe")),
        ),
        "by_direction": summarize_groups(trades, lambda trade: str(trade["direction"])),
        "by_level_weight": summarize_groups(
            trades,
            lambda trade: (
                str(trade["level_weight"])
                if trade.get("level_weight") is not None
                else "none"
            ),
        ),
        "by_level_type": summarize_groups(
            trades,
            lambda trade: (
                str(trade["level_type"])
                if trade.get("level_type") is not None
                else "none"
            ),
        ),
        "by_higher_timeframe_bias": summarize_groups(
            trades,
            lambda trade: (
                str(trade["context_higher_timeframe_bias"])
                if trade.get("context_higher_timeframe_bias") is not None
                else "none"
            ),
        ),
        "by_volatility_regime": summarize_groups(
            trades,
            lambda trade: (
                str(trade["context_volatility_regime"])
                if trade.get("context_volatility_regime") is not None
                else "none"
            ),
        ),
        "by_hour": summarize_groups(
            trades,
            lambda trade: (
                str(int(trade["signal_hour"]))
                if trade.get("signal_hour") is not None
                else None
            ),
        ),
        "by_weekday": summarize_groups(
            trades,
            lambda trade: str(trade.get("signal_weekday_name"))
            if trade.get("signal_weekday_name") is not None
            else None,
        ),
        "by_signal_range_pct_bucket": summarize_quantile_groups(
            trades,
            "signal_range_pct",
            bucket_count=bucket_count,
        ),
        "by_risk_pct_from_entry_bucket": summarize_quantile_groups(
            trades,
            "risk_pct_from_entry",
            bucket_count=bucket_count,
        ),
        "by_signal_volatility_increase_max_pct_bucket": summarize_quantile_groups(
            trades,
            "signal_volatility_increase_max_pct",
            bucket_count=bucket_count,
        ),
        "by_signal_volume_increase_max_pct_bucket": summarize_quantile_groups(
            trades,
            "signal_volume_increase_max_pct",
            bucket_count=bucket_count,
        ),
        "by_context_range_position_pct_bucket": summarize_quantile_groups(
            trades,
            "context_range_position_pct",
            bucket_count=bucket_count,
        ),
        "by_context_atr_pct_bucket": summarize_quantile_groups(
            trades,
            "context_atr_pct",
            bucket_count=bucket_count,
        ),
        "by_context_signal_range_to_atr_ratio_bucket": summarize_quantile_groups(
            trades,
            "context_signal_range_to_atr_ratio",
            bucket_count=bucket_count,
        ),
        "by_context_distance_to_recent_high_pct_bucket": summarize_quantile_groups(
            trades,
            "context_distance_to_recent_high_pct",
            bucket_count=bucket_count,
        ),
        "by_context_distance_to_recent_low_pct_bucket": summarize_quantile_groups(
            trades,
            "context_distance_to_recent_low_pct",
            bucket_count=bucket_count,
        ),
    }

    total_trades = int(summary.get("total_trades_opened", len(trades)))
    overall_loss_rate = (
        (float(summary.get("losses", 0)) / total_trades) * 100
        if total_trades
        else 0.0
    )

    candidate_filters = {
        section: extract_filter_candidates(
            grouped_summaries,
            overall_loss_rate=overall_loss_rate,
            min_group_trades=min_group_trades,
            top_n=top_n,
        )
        for section, grouped_summaries in grouped_stats.items()
    }

    return {
        "input_summary": summary,
        "primary_variant": {
            "take_multiple": float(payload.get("config", {}).get("take_multiple", 1.0)),
            "stop_multiple": float(payload.get("config", {}).get("stop_multiple", 1.0)),
        },
        "selected_variant": selected_variant,
        "total_variants": len(variant_snapshots),
        "top_variants_by_total_pnl": sorted(
            variant_snapshots,
            key=lambda item: (
                item["total_pnl_r"],
                _sort_profit_factor(item["profit_factor"]),
                item["win_rate"],
            ),
            reverse=True,
        )[:top_n],
        "top_variants_by_profit_factor": sorted(
            variant_snapshots,
            key=lambda item: (
                _sort_profit_factor(item["profit_factor"]),
                item["total_pnl_r"],
                item["win_rate"],
            ),
            reverse=True,
        )[:top_n],
        "top_variants_by_win_rate": sorted(
            variant_snapshots,
            key=lambda item: (
                item["win_rate"],
                item["total_pnl_r"],
                _sort_profit_factor(item["profit_factor"]),
            ),
            reverse=True,
        )[:top_n],
        "grouped_stats": grouped_stats,
        "candidate_filters": candidate_filters,
    }


def save_analysis(analysis: dict[str, Any], output_file: str | Path) -> Path:
    path = Path(output_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(analysis, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    return path


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    input_path = Path(args.input_file)
    analysis = analyze_backtest_result(
        load_backtest_result(input_path),
        top_n=int(args.top_n),
        bucket_count=int(args.bucket_count),
        min_group_trades=int(args.min_group_trades),
        selected_take_multiple=args.take_multiple,
        selected_stop_multiple=args.stop_multiple,
    )
    output_path = save_analysis(analysis, args.output_file)

    print(f"Input file: {input_path}")
    print(f"Output file: {output_path}")
    primary_variant = analysis["primary_variant"]
    selected_variant = analysis["selected_variant"]
    print(
        f"Primary variant: take={primary_variant['take_multiple']:.2f} "
        f"stop={primary_variant['stop_multiple']:.2f}"
    )
    print(
        f"Selected variant: take={selected_variant['take_multiple']:.2f} "
        f"stop={selected_variant['stop_multiple']:.2f}"
    )
    print("Top setups by total PnL:")
    for item in analysis["top_variants_by_total_pnl"][: min(int(args.top_n), 5)]:
        print(
            f"  take={item['take_multiple']:.2f} stop={item['stop_multiple']:.2f} "
            f"win_rate={item['win_rate']:.2f}% total_pnl_r={item['total_pnl_r']:.4f}"
        )


__all__ = [
    "analyze_backtest_result",
    "extract_filter_candidates",
    "extract_variant_summaries",
    "load_backtest_result",
    "main",
    "save_analysis",
    "select_variant_trades",
    "summarize_groups",
    "summarize_quantile_groups",
    "summarize_trade_group",
]
