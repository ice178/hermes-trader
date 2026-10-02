"""Manual date-range pattern scans using the live signal rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .backtest.data_loader import fetch_historical_candles
from .candles import Candle, CandleBatch
from .signal_filters import (
    FilteredSignal, build_signal_metrics, latest_matches, signal_metrics_pass,
)
from .signals import PriceActionSignal
from .time_utils import MADRID_TIMEZONE, timeframe_to_milliseconds

CONTEXT_CANDLES = 4
DEFAULT_SCAN_TIMEZONE = MADRID_TIMEZONE.key
HISTORICAL_TIMEFRAMES = (
    "1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h",
    "12h", "1d", "3d", "1w",
)


def _parse_scan_datetime(value: str, *, is_end: bool, zone: ZoneInfo) -> datetime:
    normalized = value.strip()
    date_only = len(normalized) == 10 and "T" not in normalized
    parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    if is_end and date_only:
        parsed += timedelta(days=1)
    if parsed.tzinfo is not None:
        return parsed.astimezone(timezone.utc)
    candidates = {}
    for fold in (0, 1):
        local = parsed.replace(tzinfo=zone, fold=fold)
        utc = local.astimezone(timezone.utc)
        if utc.astimezone(zone).replace(tzinfo=None) == parsed:
            candidates[local.utcoffset()] = utc
    if not candidates:
        raise ValueError(
            f"Local time {value} does not exist in {zone.key}; specify an explicit UTC offset"
        )
    if len(candidates) > 1:
        raise ValueError(
            f"Local time {value} is ambiguous in {zone.key}; specify an explicit UTC offset"
        )
    return next(iter(candidates.values()))


@dataclass(frozen=True)
class ScanRange:
    start_ms: int
    end_ms: int

    @classmethod
    def parse(
        cls, date_from: str, date_to: str, *,
        timezone_name: str = DEFAULT_SCAN_TIMEZONE,
    ) -> ScanRange:
        try:
            zone = ZoneInfo(timezone_name)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError(f"Unknown timezone: {timezone_name}") from None
        start = _parse_scan_datetime(date_from, is_end=False, zone=zone)
        end = _parse_scan_datetime(date_to, is_end=True, zone=zone)
        if end <= start:
            raise ValueError("--date-to must be later than --date-from")
        return cls(int(start.timestamp() * 1000), int(end.timestamp() * 1000))


@dataclass(frozen=True)
class HistoricalScan:
    loaded_candles: int
    eligible_candles: int
    evaluated_candles: int
    signals: tuple[FilteredSignal, ...]


def evaluate_historical_patterns(
    candles: list[Candle], timeframe: str, scan_range: ScanRange, *,
    now_ms: int, metric_filter_enabled: bool = False,
) -> HistoricalScan:
    """Evaluate closed candles by close time, with consecutive prior context."""
    step = timeframe_to_milliseconds(timeframe)
    ordered = sorted({candle.timestamp: candle for candle in candles}.values(),
                     key=lambda candle: candle.timestamp)
    signals: list[FilteredSignal] = []
    eligible = evaluated = 0
    detector = PriceActionSignal()
    for index, candle in enumerate(ordered):
        close_ms = candle.timestamp + step
        if not (scan_range.start_ms <= close_ms < scan_range.end_ms and close_ms <= now_ms):
            continue
        eligible += 1
        if index < CONTEXT_CANDLES - 1:
            continue
        window = ordered[index - CONTEXT_CANDLES + 1:index + 1]
        if any(right.timestamp - left.timestamp != step for left, right in zip(window, window[1:])):
            continue
        evaluated += 1
        batch = CandleBatch(window)
        for match in latest_matches(detector, batch):
            measured = build_signal_metrics(match, batch)
            if measured is not None and (
                not metric_filter_enabled or signal_metrics_pass(measured)
            ):
                signals.append(measured)
    return HistoricalScan(len(ordered), eligible, evaluated, tuple(signals))


def scan_historical_patterns(
    connector, symbol: str, timeframe: str, scan_range: ScanRange, *,
    now_ms: int, fetch_limit: int = 1000, metric_filter_enabled: bool = False,
) -> HistoricalScan:
    if timeframe not in HISTORICAL_TIMEFRAMES:
        raise ValueError(f"Unsupported historical timeframe: {timeframe}")
    if not 1 <= fetch_limit <= 1000:
        raise ValueError("--fetch-limit must be between 1 and 1000")
    if scan_range.end_ms <= scan_range.start_ms:
        raise ValueError("Scan end must be later than start")
    if scan_range.start_ms > now_ms:
        raise ValueError("--date-from must not be in the future")
    step = timeframe_to_milliseconds(timeframe)
    start = datetime.fromtimestamp(
        (scan_range.start_ms - CONTEXT_CANDLES * step) / 1000, tz=timezone.utc,
    )
    end = datetime.fromtimestamp(min(scan_range.end_ms, now_ms + 1) / 1000, tz=timezone.utc)
    candles = fetch_historical_candles(
        connector, symbol, timeframe, start.isoformat(), end.isoformat(),
        fetch_limit=fetch_limit,
    )
    return evaluate_historical_patterns(
        candles, timeframe, scan_range, now_ms=now_ms,
        metric_filter_enabled=metric_filter_enabled,
    )
