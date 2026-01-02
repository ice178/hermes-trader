from __future__ import annotations

from datetime import datetime, timezone

from hermes_trading.candles import Candle
from hermes_trading.execution import (
    build_base_trade_plan,
    compute_mfe_mae,
    create_execution_state,
    update_execution_state,
)
from hermes_trading.features import EntryFeatures
from hermes_trading.filters import apply_pin_bar_sell_filters
from hermes_trading.idea import Idea, generate_idea_id, round_level_price
from hermes_trading.trade_store import TradeStore


def _candle(ts: int, open_: float, high: float, low: float, close: float) -> Candle:
    return Candle(
        timestamp=ts,
        datetime=datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat(),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=0.0,
    )


def test_idea_id_is_stable() -> None:
    candle = _candle(1_700_000_000_000, 100, 110, 90, 105)
    rounded = round_level_price(101.2345, tick_size=None, decimals=2)
    idea = Idea(
        symbol="BTC/USDT",
        timeframe="1h",
        pattern="pin_bar",
        side="short",
        signal_candle_time=candle.datetime,
        level_price=101.2345,
        level_weight=1.0,
        level_timestamp=candle.timestamp - 3600_000,
        candle=candle,
        rounded_level_price=rounded,
    )
    assert generate_idea_id(idea) == generate_idea_id(idea)


def test_trade_store_dedup(tmp_path) -> None:
    store = TradeStore(tmp_path / "trades.json")
    record = {"idea_id": "abc", "execution_variant": "BASE_RR1"}
    assert store.add_record(record)
    assert not store.add_record(record)


def test_compute_mfe_mae_long_and_short() -> None:
    candles = [
        _candle(1_000, 100, 102, 99, 101),
        _candle(2_000, 101, 104, 98, 100),
        _candle(3_000, 100, 108, 95, 107),
        _candle(4_000, 107, 111, 96, 109),
    ]

    long_metrics = compute_mfe_mae(
        candles=candles,
        open_index=1,
        close_index=3,
        entry_price=100,
        risk=10,
        side="long",
    )

    assert long_metrics["mfe_price"] == 111
    assert long_metrics["mae_price"] == 95
    assert long_metrics["mfe_R"] == 1.1
    assert long_metrics["mae_R"] == 0.5
    assert long_metrics["time_to_0_5R_bars"] == 1

    short_metrics = compute_mfe_mae(
        candles=candles,
        open_index=1,
        close_index=3,
        entry_price=100,
        risk=10,
        side="short",
    )

    assert short_metrics["mfe_price"] == 95
    assert short_metrics["mae_price"] == 111
    assert short_metrics["mfe_R"] == 0.5
    assert short_metrics["mae_R"] == 1.1
    assert short_metrics["time_to_0_5R_bars"] == 1


def test_pin_bar_sell_filters_pass_and_fail() -> None:
    features = EntryFeatures(
        atr14=5.0,
        ema200=120.0,
        ema200_side="below",
        sl_in_atr=1.0,
        tp_in_atr=1.0,
        distance_to_level_atr=0.1,
        hour_utc=12,
        session="europe",
        candle_range=10,
        body_size=1.0,
        upper_wick=3.0,
        lower_wick=0.5,
        wick_ratio=3.0,
        close_location=0.2,
        touched_level=True,
        reclaimed_level=True,
        sweep_size_atr=0.1,
    )
    config = {
        "enabled": True,
        "use_ema200": True,
        "min_sl_atr": 0.8,
        "wick_body_ratio": 2.0,
        "close_location_max": 0.33,
        "max_distance_atr": 0.2,
        "use_sweep_filter": False,
        "min_sweep_atr": 0.05,
    }

    passed, reasons = apply_pin_bar_sell_filters(
        features,
        config=config,
        missing_indicator_policy="skip",
    )
    assert passed
    assert reasons == []

    failing = EntryFeatures(
        atr14=5.0,
        ema200=120.0,
        ema200_side="above",
        sl_in_atr=0.4,
        tp_in_atr=1.0,
        distance_to_level_atr=0.5,
        hour_utc=12,
        session="europe",
        candle_range=10,
        body_size=1.0,
        upper_wick=1.0,
        lower_wick=0.5,
        wick_ratio=1.0,
        close_location=0.6,
        touched_level=False,
        reclaimed_level=False,
        sweep_size_atr=0.01,
    )

    passed, reasons = apply_pin_bar_sell_filters(
        failing,
        config={**config, "use_sweep_filter": True},
        missing_indicator_policy="skip",
    )
    assert not passed
    assert "ema200_not_below" in reasons
    assert "sl_below_min_atr" in reasons
    assert "upper_wick_too_small" in reasons
    assert "close_location_too_high" in reasons
    assert "level_not_touched" in reasons
    assert "level_not_reclaimed" in reasons
    assert "distance_to_level_too_far" in reasons
    assert "sweep_too_small" in reasons


def test_rr1_be_time_stop_and_breakeven() -> None:
    entry_candle = _candle(1_000, 95, 105, 90, 100)
    idea = Idea(
        symbol="BTC/USDT",
        timeframe="1h",
        pattern="pin_bar",
        side="long",
        signal_candle_time=entry_candle.datetime,
        level_price=100.0,
        level_weight=1.0,
        level_timestamp=0,
        candle=entry_candle,
        rounded_level_price=100.0,
    )
    plan = build_base_trade_plan(idea)

    time_stop_state = create_execution_state(
        idea,
        "idea-1",
        plan,
        "RR1_BE_TS",
        execution_params={"time_stop_bars": 2, "be_trigger_R": 0.5, "be_offset_R": 0.0},
    )

    candles = [
        entry_candle,
        _candle(2_000, 100, 102, 98, 99),
        _candle(3_000, 99, 102, 97, 98),
    ]

    for idx, candle in enumerate(candles):
        update_execution_state(
            time_stop_state,
            candle,
            idx,
            execution_params={"time_stop_bars": 2, "be_trigger_R": 0.5, "be_offset_R": 0.0},
        )

    assert time_stop_state.exit_reason == "time_stop"

    be_state = create_execution_state(
        idea,
        "idea-2",
        plan,
        "RR1_BE_TS",
        execution_params={"time_stop_bars": 6, "be_trigger_R": 0.5, "be_offset_R": 0.0},
    )

    be_candles = [
        entry_candle,
        _candle(2_000, 100, 106, 99, 105),
        _candle(3_000, 105, 106, 99, 100),
    ]

    for idx, candle in enumerate(be_candles):
        update_execution_state(
            be_state,
            candle,
            idx,
            execution_params={"time_stop_bars": 6, "be_trigger_R": 0.5, "be_offset_R": 0.0},
        )

    assert be_state.exit_reason == "breakeven"
    assert be_state.realized_r == 0.0
