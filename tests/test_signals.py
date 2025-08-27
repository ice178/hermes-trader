from hermes_trading.candles import Candle, CandleBatch
from hermes_trading.liquidity import Level
from hermes_trading.signals import PriceActionSignal


def test_price_action_signal_detects_patterns_on_levels():
    candles = [
        Candle(0, 105, 106, 99, 100),  # bearish candle
        Candle(1, 99, 108, 98, 107),  # bullish engulfing
        Candle(2, 95, 97, 85, 96),  # pin bar
    ]
    candles.extend(Candle(i, 100, 101, 99, 100) for i in range(3, 10))
    batch = CandleBatch(list(candles))
    levels = [
        # Levels must precede the candles they validate
        Level(price=98, type="low", timestamp=0),
        Level(price=85, type="low", timestamp=1),
    ]
    signal = PriceActionSignal()
    results = signal.evaluate(batch, levels)
    assert any("bullish_engulfing" in r for r in results)
    assert any("pin_bar" in r for r in results)


def test_price_action_signal_requires_level():
    candles = [
        Candle(0, 105, 106, 99, 100),
        Candle(1, 99, 108, 98, 107),
        Candle(2, 95, 97, 85, 96),
    ]
    candles.extend(Candle(i, 100, 101, 99, 100) for i in range(3, 10))
    batch = CandleBatch(list(candles))
    signal = PriceActionSignal()
    results = signal.evaluate(batch, [])
    assert results == []


def test_price_action_signal_ignores_level_with_same_timestamp():
    candles = [
        Candle(0, 105, 106, 99, 100),
        Candle(1, 99, 108, 98, 107),
        Candle(2, 95, 97, 85, 96),
    ]
    candles.extend(Candle(i, 100, 101, 99, 100) for i in range(3, 10))
    batch = CandleBatch(list(candles))
    levels = [
        Level(price=98, type="low", timestamp=1),
        Level(price=85, type="low", timestamp=2),
    ]
    signal = PriceActionSignal()
    results = signal.evaluate(batch, levels)
    assert results == []
