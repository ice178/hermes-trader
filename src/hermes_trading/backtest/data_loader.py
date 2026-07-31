"""Historical candle loading through exchange connectors."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import ccxt

from ..candles import Candle
from ..connectors import BinanceConnector, BingXConnector
from ..time_utils import madrid_datetime_from_timestamp_ms


def create_connector(exchange: str):
    """Return the configured exchange connector for the requested venue."""

    normalized = exchange.strip().lower()
    if normalized == "bingx":
        return BingXConnector()
    if normalized == "binance":
        return BinanceConnector()
    raise ValueError(f"Unsupported exchange: {exchange}")


def parse_datetime_value(value: str, *, is_end: bool) -> datetime:
    """Parse a CLI datetime value and normalize it to UTC."""

    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    date_only = "T" not in normalized and len(normalized) == 10
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)

    if is_end and date_only:
        dt += timedelta(days=1)
    return dt


def timeframe_to_milliseconds(timeframe: str) -> int:
    units = {
        "m": 60_000,
        "h": 3_600_000,
        "d": 86_400_000,
        "w": 604_800_000,
    }

    value = int(timeframe[:-1])
    unit = timeframe[-1]
    if unit not in units:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    return value * units[unit]


def fetch_historical_candles(
    connector,
    symbol: str,
    timeframe: str,
    date_from: str,
    date_to: str,
    *,
    fetch_limit: int = 1000,
) -> list[Candle]:
    """Load candles for the requested range using the exchange connector."""

    start_dt = parse_datetime_value(date_from, is_end=False)
    end_dt = parse_datetime_value(date_to, is_end=True)
    if end_dt <= start_dt:
        raise ValueError("date_to must be greater than date_from")

    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)
    step_ms = timeframe_to_milliseconds(timeframe)

    seen_timestamps: set[int] = set()
    candles: list[Candle] = []
    since = start_ms

    while since < end_ms:
        try:
            batch = connector.client.fetch_ohlcv(
                symbol,
                timeframe=timeframe,
                since=since,
                limit=fetch_limit,
            )
        except ccxt.BadRequest as exc:
            if connector.client.id == "bingx" and "date of query is too wide" in str(exc):
                raise ValueError(
                    "BingX rejected the historical range as too wide. "
                    "Use a narrower date range or run the backtest with --exchange binance."
                ) from exc
            raise
        if not batch:
            break

        last_timestamp = batch[-1][0]
        for ts, open_, high, low, close, volume, *_ in batch:
            if ts < start_ms or ts >= end_ms or ts in seen_timestamps:
                continue

            seen_timestamps.add(ts)
            candles.append(
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
            )

        next_since = last_timestamp + step_ms
        if next_since <= since:
            break
        since = next_since

    candles.sort(key=lambda candle: candle.timestamp)
    return candles
