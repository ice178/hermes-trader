from hermes_trading.candles import Candle, CandleBatch
from hermes_trading.liquidity import Level
from hermes_trading.signals import PriceActionSignal, SignalMatch


def _cndl(
    idx: int,
    open_: float,
    high: float,
    low: float,
    close: float,
    *,
    volume: float = 100.0,
) -> Candle:
    return Candle(
        timestamp=idx,
        datetime=f"2020-01-01T00:00:{idx:02d}Z",
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def _lvl(price: float, type_: str, ts: int, *, confirmed: int | None = None) -> Level:
    return Level(
        price=price,
        type=type_,
        timestamp=ts,
        datetime="2020-01-01T00:00:00Z",
        confirmed_timestamp=confirmed if confirmed is not None else ts,
        confirmed_datetime="2020-01-01T00:00:01Z",
    )


def test_price_action_signal_detects_buy_pin_bar_on_low_level() -> None:
    candles = [
        _cndl(0, 100, 101, 99, 100),
        _cndl(1, 100, 101, 99, 100),
        _cndl(2, 95, 97, 85, 96),
    ]
    candles.extend(_cndl(i, 100, 101, 99, 100) for i in range(3, 10))
    batch = CandleBatch(list(candles))
    levels = [_lvl(price=85, type_="low", ts=0, confirmed=1)]

    signal = PriceActionSignal()
    results = signal.evaluate(batch, levels)

    assert any(
        match.pattern == "pin_bar" and match.direction == "long"
        for match in results
    )


def test_price_action_signal_detects_buy_engulfing_on_low_level() -> None:
    candles = [
        _cndl(0, 100, 101, 99, 100),
        _cndl(1, 105, 106, 99, 100),
        _cndl(2, 99, 108, 98, 107),
    ]
    candles.extend(_cndl(i, 100, 101, 99, 100) for i in range(3, 10))
    batch = CandleBatch(list(candles))
    levels = [_lvl(price=99, type_="low", ts=0, confirmed=1)]

    signal = PriceActionSignal()
    results = signal.evaluate(batch, levels)

    assert any(
        isinstance(match, SignalMatch)
        and match.pattern == "buy_engulfing"
        and match.direction == "long"
        for match in results
    )


def test_price_action_signal_detects_sell_engulfing_on_high_level() -> None:
    candles = [
        _cndl(0, 100, 101, 99, 100),
        _cndl(1, 100, 106, 99, 105),
        _cndl(2, 106, 107, 98, 99),
    ]
    candles.extend(_cndl(i, 100, 101, 99, 100) for i in range(3, 10))
    batch = CandleBatch(list(candles))
    levels = [_lvl(price=106, type_="high", ts=0, confirmed=1)]

    signal = PriceActionSignal()
    results = signal.evaluate(batch, levels)

    assert any(
        match.pattern == "sell_engulfing" and match.direction == "short"
        for match in results
    )


def test_price_action_signal_detects_two_candle_buy_engulfing_once() -> None:
    candles = [
        _cndl(0, 100, 101, 99, 100),
        _cndl(1, 110, 111, 105, 106),
        _cndl(2, 105, 106, 99, 100),
        _cndl(3, 99, 112, 98, 111),
    ]
    batch = CandleBatch(list(candles))
    levels = [_lvl(price=100, type_="low", ts=0, confirmed=1)]

    signal = PriceActionSignal()
    results = signal.evaluate(batch, levels)

    engulfing_matches = [
        match
        for match in results
        if match.pattern == "buy_engulfing" and match.direction == "long"
    ]

    assert len(engulfing_matches) == 1


def test_price_action_signal_detects_two_candle_sell_engulfing_once() -> None:
    candles = [
        _cndl(0, 100, 101, 99, 100),
        _cndl(1, 100, 105, 99, 104),
        _cndl(2, 105, 111, 104, 110),
        _cndl(3, 111, 112, 98, 99),
    ]
    batch = CandleBatch(list(candles))
    levels = [_lvl(price=110, type_="high", ts=0, confirmed=1)]

    signal = PriceActionSignal()
    results = signal.evaluate(batch, levels)

    engulfing_matches = [
        match
        for match in results
        if match.pattern == "sell_engulfing" and match.direction == "short"
    ]

    assert len(engulfing_matches) == 1


def test_price_action_signal_detects_sell_pin_bar_on_high_level() -> None:
    candles = [
        _cndl(0, 100, 101, 99, 100),
        _cndl(1, 110, 112, 105, 106),
        _cndl(2, 115, 120, 112, 114),
    ]
    candles.extend(_cndl(i, 100, 101, 99, 100) for i in range(3, 10))
    batch = CandleBatch(list(candles))
    levels = [_lvl(price=118, type_="high", ts=0, confirmed=1)]

    signal = PriceActionSignal()
    results = signal.evaluate(batch, levels)

    assert any(
        match.pattern == "pin_bar" and match.direction == "short"
        for match in results
    )


def test_price_action_signal_detects_inside_bar_long_on_low_level() -> None:
    candles = [
        _cndl(0, 100, 101, 99, 100),
        _cndl(1, 100, 101, 99, 100),
        _cndl(2, 110, 111, 99, 100),
        _cndl(3, 100.5, 110.5, 99.5, 109.5),
    ]
    batch = CandleBatch(list(candles))
    levels = [_lvl(price=100, type_="low", ts=0, confirmed=1)]

    signal = PriceActionSignal()
    results = signal.evaluate(batch, levels)

    assert any(
        match.pattern == "inside_bar" and match.direction == "long"
        for match in results
    )


def test_price_action_signal_detects_inside_bar_short_on_high_level() -> None:
    candles = [
        _cndl(0, 100, 101, 99, 100),
        _cndl(1, 100, 101, 99, 100),
        _cndl(2, 100, 111, 99, 110),
        _cndl(3, 109.5, 110.5, 99.5, 100.5),
    ]
    batch = CandleBatch(list(candles))
    levels = [_lvl(price=110, type_="high", ts=0, confirmed=1)]

    signal = PriceActionSignal()
    results = signal.evaluate(batch, levels)

    assert any(
        match.pattern == "inside_bar" and match.direction == "short"
        for match in results
    )


def test_price_action_signal_rejects_inside_bar_with_small_body() -> None:
    candles = [
        _cndl(0, 100, 101, 99, 100),
        _cndl(1, 100, 101, 99, 100),
        _cndl(2, 110, 111, 99, 100),
        _cndl(3, 102, 108, 101, 108),
    ]
    batch = CandleBatch(list(candles))
    levels = [_lvl(price=100, type_="low", ts=0, confirmed=1)]

    signal = PriceActionSignal()
    results = signal.evaluate(batch, levels)

    assert not any(match.pattern == "inside_bar" for match in results)


def test_price_action_signal_detects_railway_tracks_long() -> None:
    candles = [
        *(_cndl(i, 100, 101, 99, 100) for i in range(8)),
        _cndl(8, 110, 112, 98, 100),
        _cndl(9, 101, 112, 99, 111),
    ]
    batch = CandleBatch(list(candles))
    levels = [_lvl(price=100, type_="low", ts=7, confirmed=8)]

    signal = PriceActionSignal()
    results = signal.evaluate(batch, levels)

    assert any(
        match.pattern == "railway_tracks" and match.direction == "long"
        for match in results
    )


def test_price_action_signal_detects_railway_tracks_short() -> None:
    candles = [
        *(_cndl(i, 100, 101, 99, 100) for i in range(8)),
        _cndl(8, 90, 102, 88, 100),
        _cndl(9, 101, 103, 90, 91),
    ]
    batch = CandleBatch(list(candles))
    levels = [_lvl(price=102, type_="high", ts=7, confirmed=8)]

    signal = PriceActionSignal()
    results = signal.evaluate(batch, levels)

    assert any(
        match.pattern == "railway_tracks" and match.direction == "short"
        for match in results
    )


def test_price_action_signal_requires_level() -> None:
    candles = [
        _cndl(0, 105, 106, 99, 100),
        _cndl(1, 99, 108, 98, 107),
        _cndl(2, 95, 97, 85, 96),
    ]
    candles.extend(_cndl(i, 100, 101, 99, 100) for i in range(3, 10))
    batch = CandleBatch(list(candles))

    signal = PriceActionSignal()
    results = signal.evaluate(batch, [])

    assert results == []


def test_price_action_signal_ignores_level_with_same_timestamp() -> None:
    candles = [
        _cndl(0, 105, 106, 99, 100),
        _cndl(1, 99, 108, 98, 107),
        _cndl(2, 95, 97, 85, 96),
    ]
    candles.extend(_cndl(i, 100, 101, 99, 100) for i in range(3, 10))
    batch = CandleBatch(list(candles))
    levels = [
        _lvl(price=98, type_="low", ts=1, confirmed=3),
        _lvl(price=85, type_="low", ts=2, confirmed=3),
    ]

    signal = PriceActionSignal()
    results = signal.evaluate(batch, levels)

    assert results == []
