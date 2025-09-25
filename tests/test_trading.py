from hermes_trading.candles import Candle
from hermes_trading.liquidity import Level
from hermes_trading.trading import open_trade, update_trades


def _cndl(ts: int, open_: float, high: float, low: float, close: float) -> Candle:
    return Candle(
        timestamp=ts,
        datetime=f"2020-01-01T00:00:{ts:02d}Z",
        open=open_,
        high=high,
        low=low,
        close=close,
    )


def _lvl(price: float, type_: str, ts: int) -> Level:
    return Level(
        price=price,
        type=type_,
        timestamp=ts,
        datetime="2020-01-01T00:00:00Z",
        confirmed_timestamp=ts,
        confirmed_datetime="2020-01-01T00:00:01Z",
    )


def test_trade_hits_take() -> None:
    c0 = _cndl(0, 1.0, 1.5, 0.5, 1.2)
    level = _lvl(price=0.5, type_="low", ts=0)
    trade = open_trade(c0, "pin_bar", level, "TEST/USDT", "long")
    c1 = _cndl(1, 1.2, trade.take + 0.1, trade.stop + 0.1, trade.take + 0.05)
    update_trades([trade], c1)
    assert trade.result == "take"


def test_trade_hits_stop() -> None:
    c0 = _cndl(0, 1.0, 1.5, 0.5, 1.2)
    level = _lvl(price=0.5, type_="low", ts=0)
    trade = open_trade(c0, "pin_bar", level, "TEST/USDT", "long")
    c1 = _cndl(1, 1.2, trade.take - 0.1, trade.stop - 0.1, trade.stop - 0.05)
    update_trades([trade], c1)
    assert trade.result == "stop"


def test_trade_hits_take_for_short() -> None:
    c0 = _cndl(0, 1.0, 1.5, 0.5, 1.4)
    level = _lvl(price=1.45, type_="high", ts=0)
    trade = open_trade(c0, "pin_bar", level, "TEST/USDT", "short")
    c1 = _cndl(1, 1.3, trade.stop - 0.1, trade.take - 0.1, trade.take - 0.05)
    update_trades([trade], c1)
    assert trade.result == "take"


def test_trade_hits_stop_for_short() -> None:
    c0 = _cndl(0, 1.0, 1.3, 0.5, 1.2)
    level = _lvl(price=1.25, type_="high", ts=0)
    trade = open_trade(c0, "pin_bar", level, "TEST/USDT", "short")
    c1 = _cndl(1, 1.2, trade.stop + 0.1, trade.take + 0.1, trade.stop + 0.05)
    update_trades([trade], c1)
    assert trade.result == "stop"
