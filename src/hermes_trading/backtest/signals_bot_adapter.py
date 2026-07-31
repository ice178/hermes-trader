"""Bridge between signals_bot signal logic and the backtest engine."""

from __future__ import annotations

from .models import SignalEvent, StrategyConfig
from ..candles import CandleBatch
from ..signal_filters import filtered_latest_matches


def build_signal_events(
    candles,
    strategy: StrategyConfig,
    *,
    symbol: str | None = None,
    timeframe: str | None = None,
) -> list[SignalEvent]:
    """Create filtered signal events from historical candles."""

    if len(candles) < 4:
        return []

    seen: set[tuple[str, str, str, int, str, str]] = set()
    events: list[SignalEvent] = []

    for idx in range(3, len(candles)):
        batch = CandleBatch(candles[idx - 3: idx + 1])
        for filtered in filtered_latest_matches(
            batch,
            patterns=strategy.patterns,
            directions=strategy.direction_filter,
            min_metric_increase_pct=strategy.min_metric_increase_pct,
        ):
            match = filtered.match
            event_symbol = match.candle.symbol or symbol or ""
            event_timeframe = match.candle.timeframe or timeframe or ""
            key = (
                event_symbol,
                event_timeframe,
                match.pattern,
                match.candle.timestamp,
                match.direction,
                match.candle.datetime,
            )
            if key in seen:
                continue

            seen.add(key)
            events.append(
                SignalEvent(
                    symbol=event_symbol,
                    timeframe=event_timeframe,
                    pattern=match.pattern,
                    direction=match.direction,
                    signal_candle=match.candle,
                    volatility_increase_pct=filtered.volatility_increase_pct,
                    volume_increase_pct=filtered.volume_increase_pct,
                )
            )

    events.sort(key=lambda event: event.signal_candle.timestamp)
    return events
