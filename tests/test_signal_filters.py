from hermes_trading.candles import Candle, CandleBatch
from hermes_trading.liquidity import Level
from hermes_trading.signal_filters import (
    build_filtered_signal,
    build_signal_metrics,
    filtered_latest_matches,
    latest_fresh_batch,
    metric_increase_passes,
    metric_candle,
    reference_candles,
)
from hermes_trading.signals import PriceActionSignal, SignalMatch


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


def test_latest_fresh_batch_keeps_only_final_context() -> None:
    timeframe_ms = 15 * 60 * 1000
    candles = [
        _cndl(index * timeframe_ms, 100, 103, 99, 101, volume=100)
        for index in range(6)
    ]
    latest_close = candles[-1].timestamp + timeframe_ms

    batch = latest_fresh_batch(
        candles,
        "15m",
        now_ms=latest_close + 60_000,
        freshness_ms=timeframe_ms,
    )

    assert batch is not None
    assert [candle.timestamp for candle in batch.candles] == [
        candle.timestamp for candle in candles[-4:]
    ]


def test_latest_fresh_batch_skips_expired_latest_candle() -> None:
    timeframe_ms = 30 * 60 * 1000
    candles = [
        _cndl(index * timeframe_ms, 100, 103, 99, 101, volume=100)
        for index in range(4)
    ]
    latest_close = candles[-1].timestamp + timeframe_ms

    assert (
        latest_fresh_batch(
            candles,
            "30m",
            now_ms=latest_close + 15 * 60 * 1000,
            freshness_ms=15 * 60 * 1000,
        )
        is None
    )


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


def test_signal_metrics_are_available_when_filter_threshold_fails() -> None:
    batch = CandleBatch(
        [
            _cndl(0, 100, 110, 100, 105, volume=100),
            _cndl(1, 100, 110, 100, 105, volume=100),
            _cndl(2, 100, 110, 100, 105, volume=100),
            _cndl(3, 100, 105, 100, 101, volume=90),
        ]
    )
    match = SignalMatch(
        pattern="pin_bar",
        direction="long",
        candle=batch.candles[-1],
        level=None,
    )

    measured = build_signal_metrics(match, batch)
    filtered = build_filtered_signal(match, batch)

    assert measured is not None
    assert measured.volatility_increase_pct == (-50.0, -50.0)
    assert measured.volume_increase_pct == (-10.0, -10.0)
    assert filtered is None


def test_metric_increase_threshold_must_pass_against_both_references() -> None:
    assert metric_increase_passes((10.0, 10.0))
    assert not metric_increase_passes((10.0, 9.9))
