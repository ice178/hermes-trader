"""Shared datetime helpers for exchange and user-facing timestamps."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

MADRID_TIMEZONE = ZoneInfo("Europe/Madrid")


def timeframe_to_milliseconds(interval: str) -> int:
    """Convert a timeframe like 15m or 1h to milliseconds."""

    units = {
        "s": 1000,
        "m": 60_000,
        "h": 3_600_000,
        "d": 86_400_000,
        "w": 604_800_000,
    }
    suffix = interval[-1]
    if suffix not in units:
        raise ValueError(f"Unsupported interval: {interval}")
    value = int(interval[:-1])
    return value * units[suffix]


def is_candle_closed(
    timestamp_ms: int,
    timeframe: str,
    *,
    now_ms: int | None = None,
) -> bool:
    """Return whether the candle interval has fully elapsed."""

    current_ms = (
        now_ms
        if now_ms is not None
        else int(datetime.now(timezone.utc).timestamp() * 1000)
    )
    return timestamp_ms + timeframe_to_milliseconds(timeframe) <= current_ms


def is_candle_freshly_closed(
    timestamp_ms: int,
    timeframe: str,
    *,
    freshness_ms: int,
    now_ms: int | None = None,
) -> bool:
    """Return whether a candle closed within the current freshness window."""

    if freshness_ms <= 0:
        raise ValueError("freshness_ms must be positive")
    current_ms = (
        now_ms
        if now_ms is not None
        else int(datetime.now(timezone.utc).timestamp() * 1000)
    )
    close_ms = timestamp_ms + timeframe_to_milliseconds(timeframe)
    close_age_ms = current_ms - close_ms
    return 0 <= close_age_ms < freshness_ms


def madrid_datetime_from_timestamp_ms(timestamp_ms: int) -> str:
    """Return an ISO datetime string in Europe/Madrid for a millisecond timestamp."""

    return (
        datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
        .astimezone(MADRID_TIMEZONE)
        .isoformat()
    )
