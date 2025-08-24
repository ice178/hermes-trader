from hermes_trading.signals import PriceActionSignal


def test_price_action_signal_stub_returns_false():
    signal = PriceActionSignal(pattern="pin_bar")
    assert signal.evaluate([1.0, 2.0, 3.0]) is False
