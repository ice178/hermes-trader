"""Utilities for persisting and replaying filtered signals."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Iterable, Sequence

from ..candles import Candle
from ..signal_filters import FilteredSignal
from .models import Direction, SignalEvent


@dataclass(frozen=True)
class SavedSignalRecord:
    """Serializable representation of a filtered signal."""

    symbol: str
    timeframe: str
    pattern: str
    direction: Direction
    signal_timestamp: int
    signal_datetime: str
    signal_open: float
    signal_high: float
    signal_low: float
    signal_close: float
    signal_volume: float
    volatility_increase_pct: tuple[float, float]
    volume_increase_pct: tuple[float, float]

    @property
    def key(self) -> str:
        return "|".join(
            [
                self.symbol,
                self.timeframe,
                self.pattern,
                self.direction,
                str(self.signal_timestamp),
                self.signal_datetime,
            ]
        )

    @classmethod
    def from_filtered_signal(cls, signal: FilteredSignal) -> SavedSignalRecord:
        match = signal.match
        candle = match.candle
        return cls(
            symbol=candle.symbol or "",
            timeframe=candle.timeframe or "",
            pattern=match.pattern,
            direction=match.direction,
            signal_timestamp=candle.timestamp,
            signal_datetime=candle.datetime,
            signal_open=float(candle.open),
            signal_high=float(candle.high),
            signal_low=float(candle.low),
            signal_close=float(candle.close),
            signal_volume=float(candle.volume),
            volatility_increase_pct=tuple(float(value) for value in signal.volatility_increase_pct),
            volume_increase_pct=tuple(float(value) for value in signal.volume_increase_pct),
        )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SavedSignalRecord:
        return cls(
            symbol=str(payload["symbol"]),
            timeframe=str(payload["timeframe"]),
            pattern=str(payload["pattern"]),
            direction=str(payload["direction"]),
            signal_timestamp=int(payload["signal_timestamp"]),
            signal_datetime=str(payload["signal_datetime"]),
            signal_open=float(payload["signal_open"]),
            signal_high=float(payload["signal_high"]),
            signal_low=float(payload["signal_low"]),
            signal_close=float(payload["signal_close"]),
            signal_volume=float(payload.get("signal_volume", 0.0)),
            volatility_increase_pct=_coerce_pair(payload["volatility_increase_pct"]),
            volume_increase_pct=_coerce_pair(payload["volume_increase_pct"]),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "pattern": self.pattern,
            "direction": self.direction,
            "signal_timestamp": self.signal_timestamp,
            "signal_datetime": self.signal_datetime,
            "signal_open": self.signal_open,
            "signal_high": self.signal_high,
            "signal_low": self.signal_low,
            "signal_close": self.signal_close,
            "signal_volume": self.signal_volume,
            "volatility_increase_pct": list(self.volatility_increase_pct),
            "volume_increase_pct": list(self.volume_increase_pct),
        }

    def to_signal_event(self) -> SignalEvent:
        return SignalEvent(
            symbol=self.symbol,
            timeframe=self.timeframe,
            pattern=self.pattern,
            direction=self.direction,
            signal_candle=Candle(
                timestamp=self.signal_timestamp,
                datetime=self.signal_datetime,
                open=self.signal_open,
                high=self.signal_high,
                low=self.signal_low,
                close=self.signal_close,
                volume=self.signal_volume,
                symbol=self.symbol,
                timeframe=self.timeframe,
            ),
            volatility_increase_pct=self.volatility_increase_pct,
            volume_increase_pct=self.volume_increase_pct,
        )


def _coerce_pair(payload: Sequence[object]) -> tuple[float, float]:
    if len(payload) != 2:
        raise ValueError("expected a pair of values")
    first, second = payload
    return (float(first), float(second))


def load_saved_signal_records(path: Path) -> list[SavedSignalRecord]:
    """Load saved signals from a JSON file."""

    if not path.exists():
        return []

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"expected a JSON list in {path}")
    return [SavedSignalRecord.from_dict(item) for item in payload]


def save_saved_signal_records(path: Path, records: Iterable[SavedSignalRecord]) -> None:
    """Persist saved signals as a sorted JSON array."""

    payload = [
        record.to_dict()
        for record in sorted(
            records,
            key=lambda current: (
                current.signal_timestamp,
                current.symbol,
                current.timeframe,
                current.pattern,
                current.direction,
            ),
        )
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )


def merge_saved_signal_records(
    existing: Iterable[SavedSignalRecord],
    new_records: Iterable[SavedSignalRecord],
) -> list[SavedSignalRecord]:
    """Merge saved signals while keeping only the first occurrence of each key."""

    merged: list[SavedSignalRecord] = []
    seen: set[str] = set()

    for record in [*existing, *new_records]:
        if record.key in seen:
            continue
        seen.add(record.key)
        merged.append(record)
    return merged


def build_signal_events_from_saved_records(
    records: Iterable[SavedSignalRecord],
    *,
    patterns: Sequence[str] | None = None,
    directions: Sequence[Direction] | None = None,
    symbols: Sequence[str] | None = None,
    timeframes: Sequence[str] | None = None,
) -> list[SignalEvent]:
    """Convert saved signals into de-duplicated backtest events."""

    allowed_patterns = set(patterns) if patterns is not None else None
    allowed_directions = set(directions) if directions is not None else None
    allowed_symbols = set(symbols) if symbols is not None else None
    allowed_timeframes = set(timeframes) if timeframes is not None else None

    events: list[SignalEvent] = []
    seen: set[str] = set()

    for record in sorted(
        records,
        key=lambda current: (
            current.signal_timestamp,
            current.symbol,
            current.timeframe,
            current.pattern,
            current.direction,
        ),
    ):
        if allowed_patterns is not None and record.pattern not in allowed_patterns:
            continue
        if allowed_directions is not None and record.direction not in allowed_directions:
            continue
        if allowed_symbols is not None and record.symbol not in allowed_symbols:
            continue
        if allowed_timeframes is not None and record.timeframe not in allowed_timeframes:
            continue
        if record.key in seen:
            continue

        seen.add(record.key)
        events.append(record.to_signal_event())
    return events
