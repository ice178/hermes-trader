from hermes_trading.connectors import BinanceConnector, BingXConnector


def test_binance_connector_instantiates():
    connector = BinanceConnector()
    assert connector.client is not None


def test_bingx_connector_instantiates():
    connector = BingXConnector()
    assert connector.client is not None
