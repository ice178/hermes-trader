"""Shared helpers for signal filtering used by bot and backtests."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

from .candles import Candle, CandleBatch
from .liquidity import Level
from .signals import PriceActionSignal, SignalMatch
from .time_utils import is_candle_freshly_closed

DEFAULT_MIN_METRIC_INCREASE_PCT = 10.0


def latest_fresh_batch(
    candles: Sequence[Candle],
    timeframe: str,
    *,
    now_ms: int,
    freshness_ms: int,
    context_size: int = 4,
) -> CandleBatch | None:
    """Return the latest contextual batch when its final candle just closed."""

    if context_size <= 0:
        raise ValueError("context_size must be positive")
    if len(candles) < context_size:
        return None
    latest_candle = candles[-1]
    if not is_candle_freshly_closed(
        latest_candle.timestamp,
        timeframe,
        freshness_ms=freshness_ms,
        now_ms=now_ms,
    ):
        return None
    return CandleBatch(list(candles[-context_size:]))


@dataclass(frozen=True)
class FilteredSignal:
    """Signal enriched with volatility and volume deltas."""

    match: SignalMatch
    volatility_increase_pct: tuple[float, float]
    volume_increase_pct: tuple[float, float]


def candle_volatility(candle: Candle) -> float:
    return candle.high - candle.low


def percentage_increase(pattern_value: float, reference_value: float) -> float:
    if reference_value == 0:
        return 0.0 if pattern_value == 0 else math.inf
    return ((pattern_value - reference_value) / reference_value) * 100.0


def build_increase_pair(
    pattern_value: float,
    first_reference: float,
    second_reference: float,
) -> tuple[float, float]:
    return (
        percentage_increase(pattern_value, first_reference),
        percentage_increase(pattern_value, second_reference),
    )


def latest_matches(
    signal: PriceActionSignal,
    batch: CandleBatch,
    *,
    levels: Sequence[Level] | None = None,
    patterns: Iterable[str] | None = None,
    directions: Iterable[str] | None = None,
) -> list[SignalMatch]:
    latest_timestamp = batch.candles[-1].timestamp
    allowed_patterns = set(patterns) if patterns is not None else None
    allowed_directions = set(directions) if directions is not None else None

    evaluated_matches = (
        signal.evaluate(batch, list(levels))
        if levels is not None
        else signal.evaluate_without_levels(batch)
    )

    results: list[SignalMatch] = []
    for match in evaluated_matches:
        if match.candle.timestamp != latest_timestamp:
            continue
        if allowed_patterns is not None and match.pattern not in allowed_patterns:
            continue
        if allowed_directions is not None and match.direction not in allowed_directions:
            continue
        results.append(match)
    return results


def match_index(match: SignalMatch, batch: CandleBatch) -> int | None:
    return next(
        (idx for idx, candle in enumerate(batch.candles) if candle.timestamp == match.candle.timestamp),
        None,
    )


def metric_candle(match: SignalMatch, batch: CandleBatch) -> Candle | None:
    current_match_index = match_index(match, batch)
    if current_match_index is None:
        return None

    if match.pattern == "inside_bar":
        if current_match_index < 1:
            return None
        return batch.candles[current_match_index - 1]

    return batch.candles[current_match_index]


def reference_candles(match: SignalMatch, batch: CandleBatch) -> list[Candle] | None:
    current_match_index = match_index(match, batch)
    if current_match_index is None:
        return None

    if match.pattern in {"pin_bar", "buy_engulfing", "sell_engulfing"}:
        if current_match_index < 2:
            return None
        return batch.candles[current_match_index - 2:current_match_index]

    if match.pattern == "railway_tracks":
        first_pattern_index = current_match_index - 1
        if first_pattern_index < 2:
            return None
        return batch.candles[first_pattern_index - 2:first_pattern_index]

    if match.pattern == "inside_bar":
        mother_index = current_match_index - 1
        if mother_index < 2:
            return None
        return batch.candles[mother_index - 2:mother_index]

    return None


def build_filtered_signal(
    match: SignalMatch,
    batch: CandleBatch,
    *,
    min_metric_increase_pct: float = DEFAULT_MIN_METRIC_INCREASE_PCT,
) -> FilteredSignal | None:
    measured_signal = build_signal_metrics(match, batch)
    if measured_signal is None:
        return None

    if not signal_metrics_pass(
        measured_signal,
        min_metric_increase_pct=min_metric_increase_pct,
    ):
        return None

    return measured_signal


def build_signal_metrics(
    match: SignalMatch,
    batch: CandleBatch,
) -> FilteredSignal | None:
    """Enrich a match with metrics without using them as acceptance gates."""

    measured_candle = metric_candle(match, batch)
    if measured_candle is None:
        return None

    references = reference_candles(match, batch)
    if references is None or len(references) != 2:
        return None

    first_reference, second_reference = references

    volatility_increase_pct = build_increase_pair(
        candle_volatility(measured_candle),
        candle_volatility(first_reference),
        candle_volatility(second_reference),
    )
    volume_increase_pct = build_increase_pair(
        measured_candle.volume,
        first_reference.volume,
        second_reference.volume,
    )

    return FilteredSignal(
        match=match,
        volatility_increase_pct=volatility_increase_pct,
        volume_increase_pct=volume_increase_pct,
    )


def metric_increase_passes(
    values: tuple[float, float],
    *,
    min_metric_increase_pct: float = DEFAULT_MIN_METRIC_INCREASE_PCT,
) -> bool:
    """Return whether a metric exceeds the threshold against both references."""

    return min(values) >= min_metric_increase_pct


def signal_metrics_pass(
    signal: FilteredSignal,
    *,
    min_metric_increase_pct: float = DEFAULT_MIN_METRIC_INCREASE_PCT,
) -> bool:
    """Return whether both volatility and volume pass against both references."""

    return metric_increase_passes(
        signal.volatility_increase_pct,
        min_metric_increase_pct=min_metric_increase_pct,
    ) and metric_increase_passes(
        signal.volume_increase_pct,
        min_metric_increase_pct=min_metric_increase_pct,
    )


def filtered_latest_matches(
    batch: CandleBatch,
    *,
    signal: PriceActionSignal | None = None,
    levels: Sequence[Level] | None = None,
    patterns: Sequence[str] | None = None,
    directions: Sequence[str] | None = None,
    min_metric_increase_pct: float = DEFAULT_MIN_METRIC_INCREASE_PCT,
) -> list[FilteredSignal]:
    detector = signal or PriceActionSignal()
    return [
        filtered
        for filtered in (
            build_filtered_signal(
                match,
                batch,
                min_metric_increase_pct=min_metric_increase_pct,
            )
            for match in latest_matches(
                detector,
                batch,
                levels=levels,
                patterns=patterns,
                directions=directions,
            )
        )
        if filtered is not None
    ]
