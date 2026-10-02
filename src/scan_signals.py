#!/usr/bin/env python3
"""Manually find price-action patterns between two dates (no trade simulation)."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
import sqlite3
from typing import Sequence
from zoneinfo import ZoneInfo

from hermes_trading.backtest.data_loader import create_connector
from hermes_trading.historical_signals import (
    DEFAULT_SCAN_TIMEZONE, HISTORICAL_TIMEFRAMES, ScanRange, scan_historical_patterns,
)
from hermes_trading.level_store import LevelStore
from hermes_trading.manual_levels import PriceArea, describe_area, matching_areas
from hermes_trading.market_sessions import signal_candle_close_ms
from hermes_trading.scanner_config import SCAN_MARKETS, SCAN_TIMEFRAMES
from hermes_trading.telegram import TelegramClient, TelegramConfig
from hermes_trading.time_utils import madrid_datetime_from_timestamp_ms
from signals_bot import format_signal_messages, metric_filter_enabled_from_env


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date-from", required=True,
                        help="Start close time, inclusive; uses --timezone if no offset is given")
    parser.add_argument("--date-to", required=True,
                        help="End close time, exclusive; date-only includes the whole local day")
    parser.add_argument("--timezone", default=DEFAULT_SCAN_TIMEZONE,
                        help="Timezone for naive input (default: Europe/Madrid, Barcelona time)")
    parser.add_argument("--exchange", choices=("bingx", "binance"), default="bingx")
    parser.add_argument("--symbols", nargs="+", default=list(SCAN_MARKETS["bingx"]))
    parser.add_argument("--timeframes", nargs="+", choices=HISTORICAL_TIMEFRAMES,
                        default=list(SCAN_TIMEFRAMES))
    parser.add_argument("--fetch-limit", type=int, default=1000, help="Page size, 1–1000")
    parser.add_argument("--metric-filter", action=argparse.BooleanOptionalAction, default=None,
                        help="Override SIGNAL_METRIC_FILTER_ENABLED (default: on)")
    parser.add_argument("--send-telegram", action="store_true",
                        help="Also send clearly labeled historical signals to Telegram")
    parser.add_argument("--check-levels", action="store_true",
                        help="Test current active areas from LEVELS_DB_PATH against past patterns")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    try:
        scan_range = ScanRange.parse(args.date_from, args.date_to, timezone_name=args.timezone)
        if scan_range.start_ms > now_ms:
            raise ValueError("--date-from must not be in the future")
        if not 1 <= args.fetch_limit <= 1000:
            raise ValueError("--fetch-limit must be between 1 and 1000")
        metric_filter = (metric_filter_enabled_from_env() if args.metric_filter is None
                         else args.metric_filter)
    except (ValueError, OverflowError) as exc:
        parser.error(str(exc))

    symbols = list(dict.fromkeys(value.upper() for value in args.symbols))
    area_snapshot: dict[str, list[PriceArea]] = {}
    if args.check_levels:
        db_path = os.getenv("LEVELS_DB_PATH", "").strip()
        if not db_path:
            parser.error("--check-levels requires LEVELS_DB_PATH from the listener configuration")
        try:
            store = LevelStore(db_path)
            area_snapshot = {
                symbol: store.active_areas(args.exchange, symbol) for symbol in symbols
            }
        except (OSError, sqlite3.Error, ValueError):
            parser.error("Cannot read LEVELS_DB_PATH; check its path, permissions and schema")

    # Validate Telegram configuration before fetching when delivery was requested.
    client = TelegramClient(TelegramConfig.from_env()) if args.send_telegram else None
    connector = create_connector(args.exchange)
    all_signals = []
    incomplete = False
    input_zone = ZoneInfo(args.timezone)
    start = datetime.fromtimestamp(scan_range.start_ms / 1000, tz=input_zone).isoformat()
    end = datetime.fromtimestamp(scan_range.end_ms / 1000, tz=input_zone).isoformat()
    print(f"Historical scan ({args.timezone}): [{start}, {end}) by candle close time")
    print(f"Exchange: {args.exchange}; metric filter: {'on' if metric_filter else 'off'}")
    if args.check_levels:
        print("Testing CURRENT active areas against past patterns; historical area state is not reconstructed.")
        for symbol, areas in area_snapshot.items():
            print(f"Current active areas [{args.exchange} {symbol}]: {len(areas)}")
            for area in areas:
                print("  " + describe_area(area))
    for symbol in symbols:
        for timeframe in dict.fromkeys(args.timeframes):
            result = scan_historical_patterns(
                connector, symbol, timeframe, scan_range, now_ms=now_ms,
                fetch_limit=args.fetch_limit, metric_filter_enabled=metric_filter,
            )
            print(f"[{symbol} {timeframe}] loaded={result.loaded_candles} "
                  f"in_range={result.eligible_candles} evaluated={result.evaluated_candles} "
                  f"signals={len(result.signals)}")
            if result.evaluated_candles == 0:
                incomplete = True
                print("No evaluable candles: check the interval, history availability, and context.")
            elif result.evaluated_candles < result.eligible_candles:
                incomplete = True
                print("Some candles were skipped because preceding context is missing or has gaps.")
            all_signals.extend(result.signals)

    all_signals.sort(key=lambda signal: (
        signal_candle_close_ms(signal.match.candle), signal.match.candle.symbol,
        signal.match.candle.timeframe, signal.match.pattern, signal.match.direction,
    ))
    matched_signals = 0
    for signal in all_signals:
        match = signal.match
        close = madrid_datetime_from_timestamp_ms(signal_candle_close_ms(match.candle))
        print(f"{close} {match.candle.symbol} {match.candle.timeframe} "
              f"{match.direction.upper()} {match.pattern} open={match.candle.open}")
        annotations: list[str] = []
        if args.check_levels:
            areas = matching_areas(match, args.exchange, area_snapshot[match.candle.symbol])
            if areas:
                matched_signals += 1
                annotations = ["Matched current area: " + describe_area(area) for area in areas]
            else:
                annotations = ["Current levels: no match"]
            pattern_candles = match.pattern_candles or (match.candle,)
            low = min(candle.low for candle in pattern_candles)
            high = max(candle.high for candle in pattern_candles)
            print(f"  Pattern price range (including wicks): {low}–{high}")
            for annotation in annotations:
                print("  " + annotation)
        if client is not None:
            title = "Historical scan — current levels test" if args.check_levels else "Historical scan"
            for message in format_signal_messages(signal, annotations=annotations, title=title):
                client.send_text(message, parse_mode="HTML")
    print(f"Patterns found: {len(all_signals)}")
    if args.check_levels:
        print(f"Patterns matching current levels: {matched_signals}/{len(all_signals)}")
    if incomplete:
        print("Scan has incomplete data; results above cover evaluable candles only.")
    return 1 if incomplete else 0


if __name__ == "__main__":
    raise SystemExit(main())
