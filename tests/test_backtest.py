from hermes_trading.backtest.models import SignalEvent, StrategyConfig
from hermes_trading.backtest.signals_bot_adapter import build_signal_events
from hermes_trading.backtest.simulator import simulate_candles
from hermes_trading.candles import Candle


def _cndl(
    ts: int,
    open_: float,
    high: float,
    low: float,
    close: float,
    *,
    volume: float = 100.0,
    symbol: str = "TEST/USDT",
    timeframe: str = "15m",
) -> Candle:
    return Candle(
        timestamp=ts,
        datetime=f"2020-01-01T00:00:{ts:02d}Z",
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        symbol=symbol,
        timeframe=timeframe,
    )


def _signal_event(
    candle: Candle,
    *,
    pattern: str = "pin_bar",
    direction: str = "long",
) -> SignalEvent:
    return SignalEvent(
        symbol=candle.symbol or "TEST/USDT",
        timeframe=candle.timeframe or "15m",
        pattern=pattern,
        direction=direction,
        signal_candle=candle,
        volatility_increase_pct=(25.0, 25.0),
        volume_increase_pct=(25.0, 25.0),
    )


def test_build_signal_events_uses_signals_bot_filtering() -> None:
    candles = [
        _cndl(0, 100, 101, 99, 100, volume=90),
        _cndl(1, 102, 103, 99, 100, volume=100),
        _cndl(2, 101, 102, 98, 100, volume=110),
        _cndl(3, 95, 97, 85, 96, volume=200),
    ]

    strategy = StrategyConfig(patterns=("pin_bar",))
    events = build_signal_events(candles, strategy)

    assert len(events) == 1
    assert events[0].pattern == "pin_bar"
    assert events[0].direction == "long"
    assert events[0].signal_candle.timestamp == 3


def test_simulate_candles_tracks_r_steps_and_timing() -> None:
    candles = [
        _cndl(0, 95, 101, 90, 100, volume=200),
        _cndl(1, 101, 104, 100, 103),
        _cndl(2, 103, 107, 102, 106),
        _cndl(3, 106, 106, 100, 101),
    ]

    trades = simulate_candles(
        candles,
        [_signal_event(candles[0])],
        StrategyConfig(),
    )

    assert len(trades) == 1
    trade = trades[0]
    assert trade.entry_price == 101
    assert trade.stop_price == 90
    assert trade.best_take_step_r == 0.5
    assert trade.time_to_best_take_step_bars == 1
    assert trade.time_to_best_take_step_ms == 1
    assert trade.r_step_hit_times["0.25R"]["bars"] == 0
    assert trade.r_step_hit_times["0.50R"]["bars"] == 1
    assert trade.mae_abs == 1
    assert trade.mfe_abs == 6
    assert trade.exit_reason == "end_of_data"
    assert trade.result == "breakeven"


def test_simulate_candles_logs_intrabar_conflict_and_closes_by_stop() -> None:
    candles = [
        _cndl(0, 95, 101, 90, 100, volume=200),
        _cndl(1, 101, 104, 89, 91),
        _cndl(2, 91, 92, 88, 89),
    ]

    trades = simulate_candles(
        candles,
        [_signal_event(candles[0])],
        StrategyConfig(),
    )

    assert len(trades) == 1
    trade = trades[0]
    assert trade.exit_reason == "stop_loss"
    assert trade.result == "loss"
    assert trade.pnl_r == -1
    assert trade.best_take_step_r == 0.0
    assert trade.r_step_hit_times == {}
    assert trade.intrabar_conflict_count == 1
    assert trade.intrabar_conflict_timestamps == [1]


def test_simulate_candles_logs_internal_same_and_opposite_signals() -> None:
    candles = [
        _cndl(0, 95, 101, 90, 100, volume=200),
        _cndl(1, 101, 102, 100, 101),
        _cndl(2, 101, 103, 100, 102),
        _cndl(3, 102, 103, 100, 102),
    ]

    events = [
        _signal_event(candles[0], direction="long"),
        _signal_event(candles[2], direction="long"),
        _signal_event(candles[3], direction="short"),
    ]

    trades = simulate_candles(candles, events, StrategyConfig())

    assert len(trades) == 1
    trade = trades[0]
    assert trade.same_direction_signal_count == 1
    assert trade.opposite_direction_signal_count == 1
    assert trade.same_direction_signal_timestamps == [2]
    assert trade.opposite_direction_signal_timestamps == [3]
