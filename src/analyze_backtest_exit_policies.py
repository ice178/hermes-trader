#!/usr/bin/env python
"""Compare alternative exit policies using an existing trades.json export."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from hermes_trading.backtest.policy_analysis import (
    load_trade_observations,
    parse_exit_policy,
    summarize_exit_policy,
)


DEFAULT_POLICIES = (
    "fixed:1",
    "fixed:2",
    "scale:0.5@1,0.5@2",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trades", default="backtest_results/trades.json")
    parser.add_argument("--policy", action="append", default=[])
    parser.add_argument("--fixed-take-max", type=float)
    parser.add_argument("--fixed-take-step", type=float, default=0.25)
    parser.add_argument("--output-dir")
    parser.add_argument("--no-save", action="store_true")
    return parser.parse_args()


def _build_policy_specs(args: argparse.Namespace) -> list[str]:
    specs = ["hold"]
    if args.policy:
        specs.extend(args.policy)
    else:
        specs.extend(DEFAULT_POLICIES)

    if args.fixed_take_max is not None:
        if args.fixed_take_max <= 0:
            raise ValueError("--fixed-take-max must be positive.")
        if args.fixed_take_step <= 0:
            raise ValueError("--fixed-take-step must be positive.")

        current = args.fixed_take_step
        while current <= args.fixed_take_max + 1e-9:
            specs.append(f"fixed:{round(current, 10)}")
            current += args.fixed_take_step

    deduped_specs: list[str] = []
    seen: set[str] = set()
    for spec in specs:
        policy_name = parse_exit_policy(spec).name
        if policy_name in seen:
            continue
        seen.add(policy_name)
        deduped_specs.append(spec)
    return deduped_specs


def _render_markdown(
    trades_path: Path,
    summaries: list[dict[str, object]],
) -> str:
    lines = [
        "# Exit Policy Analysis",
        "",
        f"- Source: `{trades_path}`",
        (
            "- Assumption: any fraction not closed at its target follows the "
            "original exit stored in `trades.json`."
        ),
        "- Accuracy note: use targets aligned with the original `take_step_r` for best results.",
        "",
        "| Policy | Trades | Wins | Losses | BE | Win Rate | Total R | Avg R | Profit Factor |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    for summary in summaries:
        profit_factor = summary["profit_factor"]
        if profit_factor == float("inf"):
            profit_factor_text = "inf"
        elif profit_factor is None:
            profit_factor_text = "n/a"
        else:
            profit_factor_text = f"{profit_factor:.3f}"

        lines.append(
            (
                f"| {summary['policy_name']} | {summary['total_trades']} | "
                f"{summary['win_trades']} | {summary['loss_trades']} | "
                f"{summary['breakeven_trades']} | {summary['win_rate']:.2f}% | "
                f"{summary['total_pnl_r']:.4f} | {summary['average_pnl_r']:.4f} | "
                f"{profit_factor_text} |"
            )
        )

    best_summary = max(summaries, key=lambda item: item["total_pnl_r"])
    lines.extend(
        [
            "",
            (
                "Best total R: "
                f"`{best_summary['policy_name']}` with `{best_summary['total_pnl_r']:.4f}R`."
            ),
        ]
    )
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    trades_path = Path(args.trades)
    output_dir = Path(args.output_dir) if args.output_dir else trades_path.parent

    trades = load_trade_observations(trades_path)
    policies = [parse_exit_policy(spec) for spec in _build_policy_specs(args)]
    summaries = [asdict(summarize_exit_policy(trades, policy)) for policy in policies]

    markdown = _render_markdown(trades_path, summaries)
    print(markdown)

    if args.no_save:
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "exit_policy_analysis.json").write_text(
        json.dumps(summaries, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    (output_dir / "exit_policy_analysis.md").write_text(
        markdown,
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
