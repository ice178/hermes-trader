#!/usr/bin/env python
"""Fetch last month's candles and print any price action signals."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import html
import json
import math
from pathlib import Path

from hermes_trading.candles import Candle, CandleBatch
from hermes_trading.connectors import BingXConnector
from hermes_trading.signal_filters import (
    DEFAULT_MIN_METRIC_INCREASE_PCT,
    FilteredSignal,
    build_filtered_signal,
    latest_matches,
)
from hermes_trading.signals import PriceActionSignal
from hermes_trading.telegram import TelegramClient, TelegramConfig

SENT_SIGNALS_PATH = Path(__file__).resolve().parent / "signals_bot_sent.json"
MIN_METRIC_INCREASE_PCT = DEFAULT_MIN_METRIC_INCREASE_PCT


def match_key(signal: FilteredSignal) -> str:
    match = signal.match
    return "|".join(
        [
            str(match.pattern),
            str(match.direction),
            str(match.candle.timestamp),
            str(match.candle.timeframe),
            str(match.candle.symbol),
        ]
    )


def load_sent_keys(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    if not isinstance(payload, list):
        return set()
    return {str(item) for item in payload}


def save_sent_keys(path: Path, keys: set[str]) -> None:
    path.write_text(json.dumps(sorted(keys), ensure_ascii=True, indent=2), encoding="utf-8")


def format_percentage(value: float) -> str:
    if math.isinf(value):
        return "+inf%"
    return f"{value:+.1f}%"


def format_percentage_pair(values: tuple[float, float]) -> str:
    first, second = values
    first_formatted = html.escape(format_percentage(first))
    second_formatted = html.escape(format_percentage(second))
    return f"<code>{first_formatted}</code> / <code>{second_formatted}</code>"


def reference_context_label(pattern: str) -> str:
    if pattern == "railway_tracks":
        return "2 candles before pattern"
    return "previous 2 candles"


def format_signal_message(signal: FilteredSignal, index: int, total: int) -> str:
    match = signal.match
    pattern = html.escape(str(match.pattern).replace("_", " ").title())
    direction = html.escape(str(match.direction).upper())
    symbol = html.escape(str(match.candle.symbol))
    timeframe = html.escape(str(match.candle.timeframe))
    open_price = html.escape(str(match.candle.open))
    timestamp = html.escape(str(match.candle.datetime))
    reference_context = html.escape(reference_context_label(match.pattern))
    volatility = format_percentage_pair(signal.volatility_increase_pct)
    volume = format_percentage_pair(signal.volume_increase_pct)

    header = f"<b>Signal {index}/{total}</b>"
    details = (
        f"<b>Symbol:</b> {symbol}\n"
        f"<b>Timeframe:</b> {timeframe}\n"
        f"<b>Pattern:</b> <code>{pattern}</code>\n"
        f"<b>Direction:</b> <code>{direction}</code>\n"
        f"<b>Open:</b> <code>{open_price}</code>\n"
        f"<b>Time:</b> {timestamp}\n"
        f"<b>Volatility vs {reference_context}:</b> {volatility}\n"
        f"<b>Volume vs {reference_context}:</b> {volume}"
    )
    return f"{header}\n{details}"


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


def main() -> None:
    client = TelegramClient(TelegramConfig.from_env())
    connectors = [BingXConnector()]
    timeframes = ["15m", "30m", "1h"]
    symbols = ["BTC/USDT", "ETH/USDT", "XRP/USDT", "LINK/USDT", "TRX/USDT", "SOL/USDT", "NEAR/USDT", "ATOM/USDT", "BNB/USDT"]

    sent_keys = load_sent_keys(SENT_SIGNALS_PATH)

    for connector in connectors:
        signals: list[FilteredSignal] = []
        for symbol in symbols:
            for timeframe in timeframes:
                limit = 24
                since = since_ms(timeframe, limit)
                ohlcv = connector.client.fetch_ohlcv(
                    symbol,
                    timeframe=timeframe,
                    since=since,
                    limit=limit,
                    params={"paginate": True},
                )

                candles = [
                    Candle(
                        timestamp=ts,
                        datetime=datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat(),
                        open=o,
                        high=h,
                        low=l,
                        close=c,
                        volume=v,
                        symbol=symbol,
                        timeframe=timeframe,
                    )
                    for ts, o, h, l, c, v in ohlcv
                ]

                detector = PriceActionSignal()

                for i in range(3, len(candles)):
                    batch = CandleBatch(candles[i - 3: i + 1])

                    for match in latest_matches(detector, batch):
                        filtered_signal = build_filtered_signal(
                            match,
                            batch,
                            min_metric_increase_pct=MIN_METRIC_INCREASE_PCT,
                        )
                        if filtered_signal is not None:
                            signals.append(filtered_signal)

        seen = set()
        unique_signals: list[FilteredSignal] = []

        for signal in signals:
            key = match_key(signal)
            if key not in seen:
                seen.add(key)
                unique_signals.append(signal)

        new_signals = [signal for signal in unique_signals if match_key(signal) not in sent_keys]

        if len(new_signals) > 0:
            client.send_text(
                f"<b>Signals found:</b> <code>{len(new_signals)}</code>",
                parse_mode="HTML",
            )
        # else:
        #     client.send_text("<b>No new signals found.</b>", parse_mode="HTML")

        total_signals = len(new_signals)
        for idx, result in enumerate(new_signals, start=1):
            text = format_signal_message(result, idx, total_signals)
            client.send_text(text, parse_mode="HTML")
            sent_keys.add(match_key(result))

        save_sent_keys(SENT_SIGNALS_PATH, sent_keys)


if __name__ == "__main__":
    main()
