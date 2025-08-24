from hermes_trading.candles import Candle, CandleBatch
from hermes_trading.signals import PriceActionSignal


def test_price_action_signal_detects_patterns():
    candles = [
        Candle(0, 105, 106, 99, 100),  # bearish candle
        Candle(1, 99, 108, 98, 107),  # bullish engulfing
        Candle(2, 95, 97, 85, 96),  # pin bar
    ]
    candles.extend(Candle(i, 100, 101, 99, 100) for i in range(3, 10))
    batch = CandleBatch(list(candles))
    signal = PriceActionSignal()
    results = signal.evaluate(batch)
    assert any("bullish_engulfing" in r for r in results)
    assert any("pin_bar" in r for r in results)
