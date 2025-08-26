from hermes_trading.candles import Candle
from hermes_trading.liquidity import Level
from hermes_trading.trading import open_trade, update_trades


def test_trade_hits_take():
    c0 = Candle(0, 1.0, 1.5, 0.5, 1.2)
    level = Level(price=0.5, type="low", timestamp=0)
    trade = open_trade(c0, "pin_bar", level)
    c1 = Candle(1, 1.2, trade.take + 0.1, trade.stop + 0.1, trade.take + 0.05)
    update_trades([trade], c1)
    assert trade.result == "take"


def test_trade_hits_stop():
    c0 = Candle(0, 1.0, 1.5, 0.5, 1.2)
    level = Level(price=0.5, type="low", timestamp=0)
    trade = open_trade(c0, "pin_bar", level)
    c1 = Candle(1, 1.2, trade.take - 0.1, trade.stop - 0.1, trade.stop - 0.05)
    update_trades([trade], c1)
    assert trade.result == "stop"
