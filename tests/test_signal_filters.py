from hermes_trading.candles import Candle, CandleBatch
from hermes_trading.liquidity import Level
from hermes_trading.signal_filters import (
    build_filtered_signal,
    filtered_latest_matches,
    metric_candle,
    reference_candles,
)
from hermes_trading.signals import PriceActionSignal


def _cndl(
    ts: int,
    open_: float,
    high: float,
    low: float,
    close: float,
    *,
    volume: float,
) -> Candle:
    return Candle(
        timestamp=ts,
        datetime=f"2020-01-01T00:00:{ts:02d}Z",
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        symbol="TEST/USDT",
        timeframe="15m",
    )


def test_filtered_latest_matches_detects_buy_engulfing() -> None:
    batch = CandleBatch(
        [
            _cndl(0, 100, 103, 99, 101, volume=90),
            _cndl(1, 102, 106, 101, 104, volume=100),
            _cndl(2, 110, 111, 104, 105, volume=110),
            _cndl(3, 104, 118, 103, 117, volume=200),
        ]
    )

    results = filtered_latest_matches(
        batch,
        patterns=("buy_engulfing",),
        directions=("long",),
        min_metric_increase_pct=10,
    )

    assert len(results) == 1
    assert results[0].match.pattern == "buy_engulfing"
    assert results[0].match.direction == "long"


def test_inside_bar_filter_uses_mother_candle_for_metrics() -> None:
    batch = CandleBatch(
        [
            _cndl(0, 100, 103, 99, 101, volume=100),
            _cndl(1, 102, 106, 101, 104, volume=110),
            _cndl(2, 110, 112, 100, 100, volume=200),
            _cndl(3, 100.5, 109.9, 100.4, 109.5, volume=90),
        ]
    )

    detector = PriceActionSignal()
    matches = detector.evaluate_without_levels(batch)
    inside_match = next(match for match in matches if match.pattern == "inside_bar")

    measured = metric_candle(inside_match, batch)
    references = reference_candles(inside_match, batch)
    filtered = build_filtered_signal(
        inside_match,
        batch,
        min_metric_increase_pct=50,
    )

    assert measured is not None
    assert measured.timestamp == 2
    assert references is not None
    assert [candle.timestamp for candle in references] == [0, 1]
    assert filtered is not None
    assert filtered.match.pattern == "inside_bar"
    assert min(filtered.volume_increase_pct) > 50
    assert min(filtered.volatility_increase_pct) > 50


def test_filtered_latest_matches_respects_levels_when_provided() -> None:
    batch = CandleBatch(
        [
            _cndl(0, 100, 103, 99, 101, volume=90),
            _cndl(1, 102, 106, 101, 104, volume=100),
            _cndl(2, 110, 111, 104, 105, volume=110),
            _cndl(3, 104, 118, 103, 117, volume=200),
        ]
    )
    levels = [
        Level(
            price=103.5,
            type="low",
            timestamp=-10,
            datetime="2019-12-31T23:59:50Z",
            weight=1.0,
            confirmed_timestamp=-5,
            confirmed_datetime="2019-12-31T23:59:55Z",
        )
    ]

    results = filtered_latest_matches(
        batch,
        levels=levels,
        patterns=("buy_engulfing",),
        directions=("long",),
        min_metric_increase_pct=10,
    )

    assert len(results) == 1
    assert results[0].match.level is not None
    assert results[0].match.level.weight == 1.0
