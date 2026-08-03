#!/usr/bin/env python
"""Fetch last month's candles and print any price action signals."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import html
import math
import os

from hermes_trading.candles import Candle
from hermes_trading.connectors import BingXConnector
from hermes_trading.market_sessions import (
    signal_candle_close_ms,
    signal_candle_market_session_label,
)
from hermes_trading.signal_filters import (
    DEFAULT_MIN_METRIC_INCREASE_PCT,
    FilteredSignal,
    build_signal_metrics,
    latest_fresh_batch,
    latest_matches,
    metric_increase_passes,
    signal_metrics_pass,
)
from hermes_trading.signals import PriceActionSignal
from hermes_trading.telegram import TelegramClient, TelegramConfig
from hermes_trading.time_utils import (
    is_candle_closed,
    madrid_datetime_from_timestamp_ms,
    timeframe_to_milliseconds,
)

MIN_METRIC_INCREASE_PCT = DEFAULT_MIN_METRIC_INCREASE_PCT
SCAN_INTERVAL_MS = timeframe_to_milliseconds("15m")
ENV_METRIC_FILTER_ENABLED = "SIGNAL_METRIC_FILTER_ENABLED"
TRUTHY_CONFIG_VALUES = {"1", "true", "yes", "on"}
FALSY_CONFIG_VALUES = {"0", "false", "no", "off", ""}


def metric_filter_enabled_from_env(
    key: str = ENV_METRIC_FILTER_ENABLED,
) -> bool:
    value = os.getenv(key, "0").strip().lower()
    if value in TRUTHY_CONFIG_VALUES:
        return True
    if value in FALSY_CONFIG_VALUES:
        return False
    allowed = "0, 1, false, true, no, yes, off, on"
    raise ValueError(f"{key} must be one of: {allowed}")


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
    if pattern == "inside_bar":
        return "2 candles before mother candle"
    return "previous 2 candles"


def metric_status(values: tuple[float, float]) -> str:
    return (
        "YES"
        if metric_increase_passes(
            values,
            min_metric_increase_pct=MIN_METRIC_INCREASE_PCT,
        )
        else "NO"
    )


def should_send_signal(
    signal: FilteredSignal,
    *,
    metric_filter_enabled: bool,
) -> bool:
    return not metric_filter_enabled or signal_metrics_pass(
        signal,
        min_metric_increase_pct=MIN_METRIC_INCREASE_PCT,
    )


def metric_filter_label(
    signal: FilteredSignal,
    *,
    metric_filter_enabled: bool,
) -> str:
    if not metric_filter_enabled:
        return "DISABLED — metrics are informational only"
    if should_send_signal(signal, metric_filter_enabled=True):
        return "ENABLED — signal passed"
    return "ENABLED — signal failed"


def format_signal_message(
    signal: FilteredSignal,
    index: int,
    total: int,
    *,
    metric_filter_enabled: bool = False,
) -> str:
    match = signal.match
    pattern = html.escape(str(match.pattern).replace("_", " ").title())
    direction = html.escape(str(match.direction).upper())
    symbol = html.escape(str(match.candle.symbol))
    timeframe = html.escape(str(match.candle.timeframe))
    open_price = html.escape(str(match.candle.open))
    candle_close = html.escape(
        madrid_datetime_from_timestamp_ms(signal_candle_close_ms(match.candle))
    )
    reference_context = html.escape(reference_context_label(match.pattern))
    volatility = format_percentage_pair(signal.volatility_increase_pct)
    volume = format_percentage_pair(signal.volume_increase_pct)
    volatility_status = metric_status(signal.volatility_increase_pct)
    volume_status = metric_status(signal.volume_increase_pct)
    market_session = html.escape(signal_candle_market_session_label(match.candle))
    metric_filter = html.escape(
        metric_filter_label(
            signal,
            metric_filter_enabled=metric_filter_enabled,
        )
    )

    header = f"<b>Signal {index}/{total}</b>"
    details = (
        f"<b>Symbol:</b> {symbol}\n"
        f"<b>Timeframe:</b> {timeframe}\n"
        f"<b>Pattern:</b> <code>{pattern}</code>\n"
        f"<b>Direction:</b> <code>{direction}</code>\n"
        f"<b>Open price:</b> <code>{open_price}</code>\n"
        f"<b>Candle close:</b> {candle_close}\n"
        f"<b>Market session:</b> <code>{market_session}</code>\n"
        f"<b>Metric filter:</b> <code>{metric_filter}</code>\n"
        f"<b>Elevated volatility (≥10% vs both):</b> "
        f"<code>{volatility_status}</code>\n"
        f"<b>Volatility vs {reference_context}:</b> {volatility}\n"
        f"<b>Elevated volume (≥10% vs both):</b> <code>{volume_status}</code>\n"
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
    metric_filter_enabled = metric_filter_enabled_from_env()
    connectors = [BingXConnector()]
    timeframes = ["15m", "30m", "1h", "4h"]
    symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "NEAR/USDT"]

    for connector in connectors:
        signals: list[FilteredSignal] = []
        for symbol in symbols:
            for timeframe in timeframes:
                limit = 24
                since = since_ms(timeframe, limit)
                now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
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
                        datetime=madrid_datetime_from_timestamp_ms(int(ts)),
                        open=o,
                        high=h,
                        low=l,
                        close=c,
                        volume=v,
                        symbol=symbol,
                        timeframe=timeframe,
                    )
                    for ts, o, h, l, c, v in ohlcv
                    if is_candle_closed(int(ts), timeframe, now_ms=now_ms)
                ]

                batch = latest_fresh_batch(
                    candles,
                    timeframe,
                    now_ms=now_ms,
                    freshness_ms=SCAN_INTERVAL_MS,
                )
                if batch is None:
                    continue

                detector = PriceActionSignal()
                for match in latest_matches(detector, batch):
                    measured_signal = build_signal_metrics(match, batch)
                    if measured_signal is not None and should_send_signal(
                        measured_signal,
                        metric_filter_enabled=metric_filter_enabled,
                    ):
                        signals.append(measured_signal)

        seen = set()
        unique_signals: list[FilteredSignal] = []

        for signal in signals:
            key = match_key(signal)
            if key not in seen:
                seen.add(key)
                unique_signals.append(signal)

        if len(unique_signals) > 0:
            client.send_text(
                f"<b>Signals found:</b> <code>{len(unique_signals)}</code>",
                parse_mode="HTML",
            )
        # else:
        #     client.send_text("<b>No new signals found.</b>", parse_mode="HTML")

        total_signals = len(unique_signals)
        for idx, result in enumerate(unique_signals, start=1):
            text = format_signal_message(
                result,
                idx,
                total_signals,
                metric_filter_enabled=metric_filter_enabled,
            )
            client.send_text(text, parse_mode="HTML")


if __name__ == "__main__":
    main()
