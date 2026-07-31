import argparse
from datetime import datetime, timezone

from hermes_trading.candles import Candle
from hermes_trading.liquidity import Level, LiquidityLevels
from hermes_trading.signal_filters import FilteredSignal
from hermes_trading.signals import SignalMatch
from hermes_trading.signals_bot_backtest import (
    DetectedSignal,
    SignalBotBacktestConfig,
    build_config,
    build_entry_context,
    build_signal_market_context,
    build_summary,
    collect_filtered_signals,
    format_variant_key,
    find_entry_candle_index,
    normalize_date_range,
    normalize_stop_multiples,
    normalize_take_multiples,
    signal_available_timestamp,
    signal_passes_context_filters,
    simulate_trade,
)
from hermes_trading.time_utils import MADRID_TIMEZONE, madrid_datetime_from_timestamp_ms, timeframe_to_milliseconds

BASE_TIMESTAMP = int(
    datetime(2026, 4, 10, 0, 0, tzinfo=MADRID_TIMEZONE)
    .astimezone(timezone.utc)
    .timestamp()
    * 1000
)


def _candle(
    ts: int,
    open_: float,
    high: float,
    low: float,
    close: float,
    *,
    timeframe: str = "15m",
    volume: float = 100.0,
) -> Candle:
    timestamp = BASE_TIMESTAMP + (ts * timeframe_to_milliseconds(timeframe))
    return Candle(
        timestamp=timestamp,
        datetime=madrid_datetime_from_timestamp_ms(timestamp),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        symbol="BTC/USDT",
        timeframe=timeframe,
    )


def _detected_signal(
    candle: Candle,
    *,
    candle_index: int,
    pattern: str = "pin_bar",
    direction: str = "long",
) -> DetectedSignal:
    return DetectedSignal(
        filtered_signal=FilteredSignal(
            match=SignalMatch(
                pattern=pattern,
                direction=direction,
                candle=candle,
                level=None,
            ),
            volatility_increase_pct=(20.0, 20.0),
            volume_increase_pct=(20.0, 20.0),
        ),
        candle_index=candle_index,
    )


def _config(**overrides: object) -> SignalBotBacktestConfig:
    base = dict(
        exchange="binance",
        symbols=("BTC/USDT",),
        timeframes=("15m",),
        date_from="2026-04-06",
        date_to="2026-04-12",
        fetch_limit=1000,
        patterns=("pin_bar",),
        min_metric_increase_pct=10.0,
        use_levels=False,
        min_level_weight=0.0,
        exclude_hours=(),
        allowed_higher_timeframe_biases=(),
        allowed_volatility_regimes=(),
        min_distance_to_recent_low_pct=None,
        min_distance_to_recent_high_pct=None,
        execution_timeframe=None,
        take_multiple=1.0,
        take_multiples=(1.0,),
        stop_multiple=1.0,
        stop_multiples=(1.0,),
        save_all_variant_trades=False,
        output_file="out.json",
        normalized_date_from_madrid="2026-04-06T00:00:00+02:00",
        normalized_date_to_madrid="2026-04-12T23:59:59.999999+02:00",
        normalized_date_from_utc="2026-04-05T22:00:00+00:00",
        normalized_date_to_utc="2026-04-12T21:59:59.999999+00:00",
    )
    base.update(overrides)
    return SignalBotBacktestConfig(**base)


def test_normalize_date_range_uses_madrid_calendar_bounds() -> None:
    start_dt, end_dt = normalize_date_range("2026-04-06", "2026-04-12")

    assert start_dt.isoformat() == "2026-04-06T00:00:00+02:00"
    assert end_dt.isoformat() == "2026-04-12T23:59:59.999999+02:00"


def test_normalize_take_multiples_keeps_primary_first_and_dedupes() -> None:
    primary, take_multiples = normalize_take_multiples(1.0, [0.25, 0.5, 1.0, 0.75])

    assert primary == 1.0
    assert take_multiples == (1.0, 0.25, 0.5, 0.75)


def test_normalize_take_multiples_merges_compare_range() -> None:
    primary, take_multiples = normalize_take_multiples(1.0, compare_take_range=(0.25, 0.75, 0.25))

    assert primary == 1.0
    assert take_multiples == (1.0, 0.25, 0.5, 0.75)


def test_normalize_stop_multiples_keeps_primary_first_and_dedupes() -> None:
    primary, stop_multiples = normalize_stop_multiples(1.0, [0.25, 0.5, 1.0])

    assert primary == 1.0
    assert stop_multiples == (1.0, 0.25, 0.5)


def test_build_config_normalizes_context_filters() -> None:
    config = build_config(
        argparse.Namespace(
            exchange="binance",
            symbols=["BTC/USDT"],
            timeframes=["15m"],
            date_from="2026-04-06",
            date_to="2026-04-12",
            fetch_limit=1000,
            patterns=["pin_bar"],
            min_metric_increase_pct=10.0,
            use_levels=False,
            min_level_weight=0.0,
            exclude_hours=[13, 19, 13],
            allowed_higher_timeframe_biases=["Bearish", "Neutral"],
            allowed_volatility_regimes=["Expanded"],
            min_distance_to_recent_low_pct=0.25,
            min_distance_to_recent_high_pct=0.5,
            execution_timeframe=None,
            take_multiple=1.0,
            compare_take_multiples=None,
            compare_take_range=None,
            stop_multiple=1.0,
            compare_stop_multiples=None,
            compare_stop_range=None,
            save_all_variant_trades=False,
            output_file="out.json",
        )
    )

    assert config.exclude_hours == (13, 19)
    assert config.allowed_higher_timeframe_biases == ("bearish", "neutral")
    assert config.allowed_volatility_regimes == ("expanded",)
    assert config.min_distance_to_recent_low_pct == 0.25
    assert config.min_distance_to_recent_high_pct == 0.5


def test_format_variant_key_uses_stable_take_and_stop_representation() -> None:
    assert format_variant_key(1.5, 0.5) == "take=1.5|stop=0.5"


def test_signal_available_timestamp_uses_source_timeframe_close() -> None:
    signal_candle = _candle(0, 95, 103, 90, 100, timeframe="15m")

    assert signal_available_timestamp(_detected_signal(signal_candle, candle_index=0)) == (
        signal_candle.timestamp + timeframe_to_milliseconds("15m")
    )


def test_find_entry_candle_index_returns_first_candle_after_signal_close() -> None:
    execution_candles = [
        _candle(0, 99, 100, 98, 99, timeframe="5m"),
        _candle(1, 100, 101, 99, 100, timeframe="5m"),
        _candle(2, 101, 102, 100, 101, timeframe="5m"),
        _candle(3, 102, 103, 101, 102, timeframe="5m"),
    ]
    signal_available_at = execution_candles[2].timestamp

    assert find_entry_candle_index(execution_candles, signal_available_at) == 2


def test_collect_filtered_signals_can_use_levels() -> None:
    candles = [
        _candle(0, 100, 103, 99, 101, volume=90),
        _candle(1, 102, 106, 101, 104, volume=100),
        _candle(2, 110, 111, 104, 105, volume=110),
        _candle(3, 104, 118, 103, 117, volume=200),
    ]
    levels_state = LiquidityLevels()
    levels_state.levels = [
        Level(
            price=103.5,
            type="low",
            timestamp=candles[0].timestamp,
            datetime=candles[0].datetime,
            weight=1.0,
            confirmed_timestamp=candles[1].timestamp,
            confirmed_datetime=candles[1].datetime,
            active=True,
        )
    ]

    results = collect_filtered_signals(
        candles,
        patterns=("buy_engulfing",),
        min_metric_increase_pct=10,
        use_levels=True,
        levels_state=levels_state,
    )

    assert len(results) == 1
    assert results[0].filtered_signal.match.level is not None
    assert results[0].filtered_signal.match.level.weight == 1.0


def test_signal_passes_context_filters_respects_hour_bias_regime_and_distance() -> None:
    candles = [
        _candle(0, 100, 102, 99, 101),
        _candle(1, 101, 103, 100, 102),
        _candle(2, 102, 104, 101, 103),
        _candle(3, 103, 105, 102, 104),
        _candle(4, 104, 106, 103, 105),
        _candle(5, 105, 107, 104, 106),
        _candle(6, 106, 108, 105, 107),
        _candle(7, 107, 109, 106, 108),
        _candle(8, 108, 110, 107, 109),
        _candle(9, 109, 111, 108, 110),
        _candle(10, 110, 112, 109, 111),
        _candle(11, 111, 113, 110, 112),
        _candle(12, 112, 114, 111, 113),
        _candle(13, 113, 115, 112, 114),
        _candle(14, 114, 116, 113, 115),
        _candle(15, 115, 123, 114, 122),
    ]
    detected_long = _detected_signal(candles[15], candle_index=15, direction="long")
    detected_short = _detected_signal(candles[15], candle_index=15, direction="short")
    context = build_signal_market_context(
        candles,
        15,
        range_lookback=4,
        recent_lookback=4,
        atr_period=4,
        bias_fast_period=2,
        bias_slow_period=3,
    )
    signal_hour = datetime.fromisoformat(candles[15].datetime).hour

    assert signal_passes_context_filters(
        detected_long,
        context,
        _config(
            allowed_higher_timeframe_biases=("bullish",),
            allowed_volatility_regimes=("expanded",),
            min_distance_to_recent_low_pct=9.0,
        ),
    )
    assert not signal_passes_context_filters(
        detected_long,
        context,
        _config(exclude_hours=(signal_hour,)),
    )
    assert not signal_passes_context_filters(
        detected_long,
        context,
        _config(allowed_higher_timeframe_biases=("bearish",)),
    )
    assert not signal_passes_context_filters(
        detected_long,
        context,
        _config(allowed_volatility_regimes=("normal",)),
    )
    assert not signal_passes_context_filters(
        detected_long,
        context,
        _config(min_distance_to_recent_low_pct=10.0),
    )
    assert not signal_passes_context_filters(
        detected_short,
        context,
        _config(min_distance_to_recent_high_pct=5.0),
    )


def test_build_entry_context_uses_execution_timeframe_open() -> None:
    signal_candle = _candle(0, 95, 103, 90, 100, timeframe="15m")
    execution_candles = [
        _candle(0, 99, 100, 98, 99, timeframe="5m"),
        _candle(1, 100, 101, 99, 100, timeframe="5m"),
        _candle(2, 101, 102, 100, 101, timeframe="5m"),
        _candle(3, 102, 103, 101, 102, timeframe="5m"),
    ]

    entry = build_entry_context(
        _detected_signal(signal_candle, candle_index=0),
        [signal_candle],
        execution_candles=execution_candles,
        execution_timeframe="5m",
    )

    assert entry is not None
    assert entry.entry_price == 102
    assert entry.entry_timestamp == execution_candles[3].timestamp
    assert entry.execution_timeframe == "5m"
    assert entry.entry_source == "execution_timeframe_open"
    assert entry.signal_to_entry_minutes == 0.0


def test_build_entry_context_returns_none_when_no_execution_candle_exists() -> None:
    signal_candle = _candle(0, 95, 103, 90, 100, timeframe="15m")
    execution_candles = [
        _candle(0, 99, 100, 98, 99, timeframe="5m"),
        _candle(1, 100, 101, 99, 100, timeframe="5m"),
    ]

    entry = build_entry_context(
        _detected_signal(signal_candle, candle_index=0),
        [signal_candle],
        execution_candles=execution_candles,
        execution_timeframe="5m",
    )

    assert entry is None


def test_simulate_trade_long_hits_take_profit_same_timeframe_mode() -> None:
    signal_candle = _candle(0, 95, 103, 90, 100)
    candles = [
        signal_candle,
        _candle(1, 100, 110, 97, 109),
    ]

    trade = simulate_trade(
        _detected_signal(signal_candle, candle_index=0, direction="long"),
        candles,
    )

    assert trade is not None
    assert trade.signal_timeframe == "15m"
    assert trade.execution_timeframe == "15m"
    assert trade.is_suitable is None
    assert trade.comment is None
    assert trade.mistake_reason is None
    assert trade.entry_source == "signal_close"
    assert trade.entry_timestamp == signal_candle.timestamp + timeframe_to_milliseconds("15m")
    assert trade.entry_datetime == madrid_datetime_from_timestamp_ms(trade.entry_timestamp)
    assert trade.signal_to_entry_minutes == 0.0
    assert trade.signal_hour == 0
    assert trade.signal_weekday == 4
    assert trade.signal_weekday_name == "friday"
    assert trade.signal_range_abs == 13
    assert trade.signal_range_pct == 13.0
    assert trade.signal_body_abs == 5
    assert trade.signal_body_pct_of_range == (5 / 13) * 100
    assert trade.signal_upper_wick_abs == 3
    assert trade.signal_lower_wick_abs == 5
    assert trade.level_price is None
    assert trade.level_type is None
    assert trade.level_weight is None
    assert trade.level_to_entry_abs is None
    assert trade.exit_reason == "take_profit"
    assert trade.result == "win"
    assert trade.entry_price == 100
    assert trade.stop_price == 90
    assert trade.take_price == 110
    assert trade.signal_risk_per_unit == 10
    assert trade.exit_price == 110
    assert trade.closed_at == candles[1].datetime
    assert trade.stop_multiple == 1.0
    assert trade.rr_ratio == 1.0
    assert trade.risk_pct_from_entry == 10.0
    assert trade.signal_risk_pct_from_entry == 10.0
    assert trade.pnl_r == 1.0
    assert trade.pnl_signal_r == 1.0
    assert trade.max_drawdown_abs == 3
    assert trade.max_profit_abs == 10
    assert trade.max_drawdown_signal_r == 0.3
    assert trade.max_profit_signal_r == 1.0
    assert trade.bars_in_trade == 1
    assert trade.duration_minutes == 0.0


def test_simulate_trade_respects_custom_take_multiple() -> None:
    signal_candle = _candle(0, 95, 103, 90, 100)
    candles = [
        signal_candle,
        _candle(1, 100, 105, 97, 104),
    ]

    trade = simulate_trade(
        _detected_signal(signal_candle, candle_index=0, direction="long"),
        candles,
        take_multiple=0.5,
    )

    assert trade is not None
    assert trade.take_multiple == 0.5
    assert trade.stop_multiple == 1.0
    assert trade.rr_ratio == 0.5
    assert trade.take_price == 105
    assert trade.exit_reason == "take_profit"
    assert trade.exit_price == 105
    assert trade.pnl_r == 0.5


def test_simulate_trade_respects_custom_stop_multiple() -> None:
    signal_candle = _candle(0, 95, 103, 90, 100)
    candles = [
        signal_candle,
        _candle(1, 100, 106, 97, 104),
    ]

    trade = simulate_trade(
        _detected_signal(signal_candle, candle_index=0, direction="long"),
        candles,
        take_multiple=0.5,
        stop_multiple=0.5,
    )

    assert trade is not None
    assert trade.stop_multiple == 0.5
    assert trade.stop_price == 95
    assert trade.take_price == 105
    assert trade.signal_risk_per_unit == 10
    assert trade.risk_per_unit == 5
    assert trade.rr_ratio == 1.0
    assert trade.risk_pct_from_entry == 5.0
    assert trade.signal_risk_pct_from_entry == 10.0
    assert trade.exit_reason == "take_profit"
    assert trade.pnl_r == 1.0
    assert trade.pnl_signal_r == 0.5


def test_simulate_trade_persists_level_metadata() -> None:
    signal_candle = _candle(0, 95, 103, 90, 100)
    candles = [
        signal_candle,
        _candle(1, 100, 110, 97, 109),
    ]
    level = Level(
        price=95.0,
        type="low",
        timestamp=signal_candle.timestamp - timeframe_to_milliseconds("15m"),
        datetime=madrid_datetime_from_timestamp_ms(
            signal_candle.timestamp - timeframe_to_milliseconds("15m")
        ),
        weight=1.0,
        confirmed_timestamp=signal_candle.timestamp - 1,
        confirmed_datetime=madrid_datetime_from_timestamp_ms(signal_candle.timestamp - 1),
        active=True,
    )
    detected_signal = DetectedSignal(
        filtered_signal=FilteredSignal(
            match=SignalMatch(
                pattern="pin_bar",
                direction="long",
                candle=signal_candle,
                level=level,
            ),
            volatility_increase_pct=(20.0, 20.0),
            volume_increase_pct=(20.0, 20.0),
        ),
        candle_index=0,
    )

    trade = simulate_trade(detected_signal, candles)

    assert trade is not None
    assert trade.level_price == 95.0
    assert trade.level_type == "low"
    assert trade.level_weight == 1.0
    assert trade.level_timestamp == level.timestamp
    assert trade.level_datetime == level.datetime
    assert trade.level_confirmed_timestamp == level.confirmed_timestamp
    assert trade.level_confirmed_datetime == level.confirmed_datetime
    assert trade.level_to_entry_abs == 5.0
    assert trade.level_to_entry_pct == 5.0


def test_simulate_trade_persists_market_context() -> None:
    candles = [
        _candle(0, 100, 102, 99, 101),
        _candle(1, 101, 103, 100, 102),
        _candle(2, 102, 104, 101, 103),
        _candle(3, 103, 105, 102, 104),
        _candle(4, 104, 106, 103, 105),
        _candle(5, 105, 107, 104, 106),
        _candle(6, 106, 108, 105, 107),
        _candle(7, 107, 109, 106, 108),
        _candle(8, 108, 110, 107, 109),
        _candle(9, 109, 111, 108, 110),
        _candle(10, 110, 112, 109, 111),
        _candle(11, 111, 113, 110, 112),
        _candle(12, 112, 114, 111, 113),
        _candle(13, 113, 115, 112, 114),
        _candle(14, 114, 116, 113, 115),
        _candle(15, 115, 123, 114, 122),
        _candle(16, 122, 130, 121, 129),
    ]

    context = build_signal_market_context(
        candles,
        15,
        range_lookback=4,
        recent_lookback=4,
        atr_period=4,
        bias_fast_period=2,
        bias_slow_period=3,
    )
    trade = simulate_trade(
        _detected_signal(candles[15], candle_index=15, direction="long"),
        candles,
        market_context=context,
    )

    assert trade is not None
    assert trade.context_higher_timeframe == "1h"
    assert trade.context_higher_timeframe_bias == "bullish"
    assert trade.context_range_lookback == 4
    assert trade.context_range_high == 123
    assert trade.context_range_low == 111
    assert trade.context_recent_lookback == 4
    assert trade.context_recent_high == 116
    assert trade.context_recent_low == 110
    assert trade.context_distance_to_recent_high_abs == 6
    assert trade.context_distance_to_recent_low_abs == 12
    assert trade.context_atr_period == 4
    assert trade.context_atr_abs == 4.5
    assert trade.context_signal_range_to_atr_ratio == 2.0
    assert trade.context_volatility_regime == "expanded"


def test_simulate_trade_execution_timeframe_uses_first_5m_candle_after_signal_close() -> None:
    signal_candle = _candle(0, 95, 103, 90, 100, timeframe="15m")
    source_candles = [
        signal_candle,
        _candle(1, 100, 104, 96, 101, timeframe="15m"),
    ]
    execution_candles = [
        _candle(0, 99, 100, 98, 99, timeframe="5m"),
        _candle(1, 100, 101, 99, 100, timeframe="5m"),
        _candle(2, 101, 102, 100, 101, timeframe="5m"),
        _candle(3, 102, 113, 101, 112, timeframe="5m"),
    ]

    trade = simulate_trade(
        _detected_signal(signal_candle, candle_index=0, direction="long"),
        source_candles,
        execution_candles=execution_candles,
        execution_timeframe="5m",
    )

    assert trade is not None
    assert trade.signal_timeframe == "15m"
    assert trade.execution_timeframe == "5m"
    assert trade.entry_source == "execution_timeframe_open"
    assert trade.entry_timestamp == execution_candles[3].timestamp
    assert trade.entry_datetime == execution_candles[3].datetime
    assert trade.entry_price == 102
    assert trade.signal_to_entry_minutes == 0.0
    assert trade.stop_price == 90
    assert trade.take_price == 114
    assert trade.signal_risk_per_unit == 12
    assert trade.exit_reason == "end_of_data"
    assert trade.result == "win"
    assert trade.max_drawdown_abs == 1
    assert trade.max_profit_abs == 11


def test_simulate_trade_short_hits_stop_loss() -> None:
    signal_candle = _candle(0, 105, 110, 99, 100)
    candles = [
        signal_candle,
        _candle(1, 100, 110, 98, 109),
    ]

    trade = simulate_trade(
        _detected_signal(signal_candle, candle_index=0, direction="short"),
        candles,
    )

    assert trade is not None
    assert trade.exit_reason == "stop_loss"
    assert trade.result == "loss"
    assert trade.entry_price == 100
    assert trade.stop_price == 110
    assert trade.take_price == 90
    assert trade.exit_price == 110
    assert trade.pnl_r == -1.0
    assert trade.max_drawdown_abs == 10
    assert trade.max_profit_abs == 2


def test_simulate_trade_short_hits_take_profit() -> None:
    signal_candle = _candle(0, 105, 110, 99, 100)
    candles = [
        signal_candle,
        _candle(1, 100, 102, 90, 91),
    ]

    trade = simulate_trade(
        _detected_signal(signal_candle, candle_index=0, direction="short"),
        candles,
    )

    assert trade is not None
    assert trade.exit_reason == "take_profit"
    assert trade.result == "win"
    assert trade.exit_price == 90
    assert trade.pnl_r == 1.0
    assert trade.max_drawdown_abs == 2
    assert trade.max_profit_abs == 10


def test_simulate_trade_marks_intrabar_conflict_stop_first() -> None:
    signal_candle = _candle(0, 95, 103, 90, 100)
    candles = [
        signal_candle,
        _candle(1, 100, 110, 90, 105),
    ]

    trade = simulate_trade(
        _detected_signal(signal_candle, candle_index=0, direction="long"),
        candles,
    )

    assert trade is not None
    assert trade.exit_reason == "stop_loss"
    assert trade.result == "loss"
    assert trade.intrabar_conflict is True
    assert trade.intrabar_conflict_reason == "stop_and_take_hit_same_candle"
    assert trade.exit_price == 90


def test_simulate_trade_closes_at_end_of_data_and_tracks_excursions() -> None:
    signal_candle = _candle(0, 95, 103, 90, 100)
    candles = [
        signal_candle,
        _candle(1, 100, 108, 95, 104),
    ]

    trade = simulate_trade(
        _detected_signal(signal_candle, candle_index=0, direction="long"),
        candles,
    )

    assert trade is not None
    assert trade.exit_reason == "end_of_data"
    assert trade.result == "win"
    assert trade.exit_price == 104
    assert trade.closed_at == candles[1].datetime
    assert trade.pnl_r == 0.4
    assert trade.max_drawdown_abs == 5
    assert trade.max_profit_abs == 8
    assert trade.max_drawdown_r == 0.5
    assert trade.max_profit_r == 0.8


def test_simulate_trade_skips_invalid_risk() -> None:
    signal_candle = _candle(0, 100, 105, 100, 100)
    candles = [signal_candle, _candle(1, 100, 105, 95, 101)]

    trade = simulate_trade(
        _detected_signal(signal_candle, candle_index=0, direction="long"),
        candles,
    )

    assert trade is None


def test_build_summary_aggregates_trade_counts() -> None:
    signal_candle = _candle(0, 95, 103, 90, 100)
    winning_trade = simulate_trade(
        _detected_signal(signal_candle, candle_index=0, direction="long"),
        [signal_candle, _candle(1, 100, 110, 97, 109)],
    )
    losing_trade = simulate_trade(
        _detected_signal(signal_candle, candle_index=0, direction="long"),
        [signal_candle, _candle(1, 100, 102, 90, 91)],
    )

    assert winning_trade is not None
    assert losing_trade is not None

    summary = build_summary(
        total_signals=4,
        trades=[winning_trade, losing_trade],
        skipped_invalid_risk=1,
        skipped_missing_entry_candle=1,
    )

    assert summary.total_signals == 4
    assert summary.total_trades_opened == 2
    assert summary.skipped_invalid_risk == 1
    assert summary.skipped_missing_entry_candle == 1
    assert summary.wins == 1
    assert summary.losses == 1
    assert summary.breakevens == 0
    assert summary.win_rate == 50.0
    assert summary.total_pnl_signal_r == 0.0
    assert summary.average_pnl_signal_r == 0.0
    assert summary.average_win_r == 1.0
    assert summary.average_loss_r == -1.0
    assert summary.profit_factor == 1.0
    assert summary.max_equity_drawdown_r == 1.0
    assert summary.counts_by_pattern == {"pin_bar": 2}
    assert summary.counts_by_symbol == {"BTC/USDT": 2}
    assert summary.counts_by_timeframe == {"15m": 2}
    assert summary.counts_by_level_weight == {"none": 2}
    assert summary.counts_by_level_type == {"none": 2}
