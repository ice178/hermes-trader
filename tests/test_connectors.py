from hermes_trading.connectors import BinanceConnector, BingXConnector
from unittest.mock import patch


def test_binance_connector_instantiates():
    connector = BinanceConnector()
    assert connector.client is not None


def test_binance_get_klines_returns_ten_candles():
    connector = BinanceConnector()
    dummy = [[i, 1, 2, 0, 1, 0] for i in range(10)]
    with patch.object(connector.client, "fetch_ohlcv", return_value=dummy):
        batch = connector.get_klines("BTC/USDT", "1m")
    assert len(batch.candles) == 10


def test_bingx_connector_instantiates():
    connector = BingXConnector()
    assert connector.client is not None


def test_bingx_get_klines_returns_ten_candles():
    connector = BingXConnector()
    dummy = [[i, 1, 2, 0, 1, 0] for i in range(10)]
    with patch.object(connector.client, "fetch_ohlcv", return_value=dummy):
        batch = connector.get_klines("BTC/USDT", "1m")
    assert len(batch.candles) == 10
