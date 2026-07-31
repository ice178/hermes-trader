#!/usr/bin/env python
"""Scan recent signals and append new ones to a JSON file."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from hermes_trading.backtest import (
    SavedSignalRecord,
    create_connector,
    load_saved_signal_records,
    merge_saved_signal_records,
    save_saved_signal_records,
)
from hermes_trading.candles import Candle, CandleBatch
from hermes_trading.signal_filters import (
    DEFAULT_MIN_METRIC_INCREASE_PCT,
    filtered_latest_matches,
)
from hermes_trading.time_utils import (
    is_candle_closed,
    madrid_datetime_from_timestamp_ms,
)

DEFAULT_OUTPUT_PATH = Path(__file__).resolve().parent / "signals_bot_signals.json"
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exchange", default="bingx")
    parser.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS))
    parser.add_argument("--timeframes", nargs="+", default=list(DEFAULT_TIMEFRAMES))
    parser.add_argument("--limit", type=int, default=24)
    parser.add_argument(
        "--min-metric-increase-pct",
        type=float,
        default=DEFAULT_MIN_METRIC_INCREASE_PCT,
    )
    parser.add_argument("--output-file", default=str(DEFAULT_OUTPUT_PATH))
    return parser.parse_args()


def since_ms(interval: str, multiplier: int = 1) -> int:
    units = {
        "s": 1,
        "m": 60,
        "h": 3600,
        "d": 86400,
        "w": 604800,
    }

    value = int(interval[:-1])
    unit = interval[-1]
    if unit not in units:
        raise ValueError(f"Unsupported interval: {interval}")

    seconds = value * units[unit] * multiplier
    dt = datetime.now(timezone.utc) - timedelta(seconds=seconds)
    return int(dt.timestamp() * 1000)


def _build_candles(
    raw_ohlcv: list[list[float]],
    *,
    symbol: str,
    timeframe: str,
) -> list[Candle]:
    return [
        Candle(
            timestamp=int(ts),
            datetime=madrid_datetime_from_timestamp_ms(int(ts)),
            open=float(open_),
            high=float(high),
            low=float(low),
            close=float(close),
            volume=float(volume),
            symbol=symbol,
            timeframe=timeframe,
        )
        for ts, open_, high, low, close, volume, *_ in raw_ohlcv
    ]


def _format_signal(record: SavedSignalRecord) -> str:
    return (
        f"{record.signal_datetime} "
        f"{record.symbol} {record.timeframe} "
        f"{record.direction.upper()} {record.pattern}"
    )


def main() -> None:
    args = parse_args()
    if args.limit < 4:
        raise ValueError("--limit must be at least 4 candles.")

    connector = create_connector(args.exchange)
    output_path = Path(args.output_file)
    existing_records = load_saved_signal_records(output_path)
    known_keys = {record.key for record in existing_records}
    new_records: list[SavedSignalRecord] = []

    for symbol in args.symbols:
        for timeframe in args.timeframes:
            now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
            raw_ohlcv = connector.client.fetch_ohlcv(
                symbol,
                timeframe=timeframe,
                since=since_ms(timeframe, args.limit),
                limit=args.limit,
                params={"paginate": True},
            )
            candles = _build_candles(
                [
                    row
                    for row in raw_ohlcv
                    if is_candle_closed(int(row[0]), timeframe, now_ms=now_ms)
                ],
                symbol=symbol,
                timeframe=timeframe,
            )

            for idx in range(3, len(candles)):
                batch = CandleBatch(candles[idx - 3: idx + 1])
                for filtered in filtered_latest_matches(
                    batch,
                    min_metric_increase_pct=args.min_metric_increase_pct,
                ):
                    record = SavedSignalRecord.from_filtered_signal(filtered)
                    if record.key in known_keys:
                        continue
                    known_keys.add(record.key)
                    new_records.append(record)

    merged_records = merge_saved_signal_records(existing_records, new_records)
    save_saved_signal_records(output_path, merged_records)

    print(f"Saved signals file: {output_path}")
    print(f"Existing signals kept: {len(existing_records)}")
    print(f"New signals appended: {len(new_records)}")

    if not new_records:
        print("No new signals found.")
        return

    for record in sorted(
        new_records,
        key=lambda current: (
            current.signal_timestamp,
            current.symbol,
            current.timeframe,
            current.pattern,
            current.direction,
        ),
    ):
        print(_format_signal(record))


if __name__ == "__main__":
    main()
