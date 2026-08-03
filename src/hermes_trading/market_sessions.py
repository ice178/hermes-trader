"""Market-session labels based on timezone-aware local trading hours."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from .candles import Candle
from .time_utils import timeframe_to_milliseconds


@dataclass(frozen=True)
class MarketSession:
    name: str
    timezone: ZoneInfo
    opens_at: time
    closes_at: time

    def is_active(self, timestamp_ms: int) -> bool:
        local_time = datetime.fromtimestamp(
            timestamp_ms / 1000,
            tz=timezone.utc,
        ).astimezone(self.timezone).time()
        return self.opens_at <= local_time < self.closes_at


MARKET_SESSIONS = (
    MarketSession(
        name="Tokyo",
        timezone=ZoneInfo("Asia/Tokyo"),
        opens_at=time(9),
        closes_at=time(18),
    ),
    MarketSession(
        name="London",
        timezone=ZoneInfo("Europe/London"),
        opens_at=time(8),
        closes_at=time(17),
    ),
    MarketSession(
        name="New York",
        timezone=ZoneInfo("America/New_York"),
        opens_at=time(8),
        closes_at=time(17),
    ),
)


def active_market_sessions(timestamp_ms: int) -> tuple[str, ...]:
    """Return all sessions active at a UTC instant expressed as epoch milliseconds."""

    return tuple(
        session.name
        for session in MARKET_SESSIONS
        if session.is_active(timestamp_ms)
    )


def market_session_label(timestamp_ms: int) -> str:
    names = active_market_sessions(timestamp_ms)
    return " + ".join(names) if names else "No major session"


def signal_candle_close_ms(candle: Candle) -> int:
    if candle.timeframe is None:
        raise ValueError("Signal candle timeframe is required")
    return candle.timestamp + timeframe_to_milliseconds(candle.timeframe)


def signal_candle_market_session_label(candle: Candle) -> str:
    """Classify a signal using the close time of its final pattern candle."""

    return market_session_label(signal_candle_close_ms(candle))
