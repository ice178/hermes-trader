from hermes_trading.signals_bot_backtest_analysis import (
    analyze_backtest_result,
    extract_variant_summaries,
    select_variant_trades,
)


def test_extract_variant_summaries_falls_back_to_take_only_payload() -> None:
    payload = {
        "config": {"stop_multiple": 0.5},
        "take_variant_summaries": [
            {
                "take_multiple": 0.25,
                "summary": {
                    "total_trades_opened": 10,
                    "win_rate": 60.0,
                    "total_pnl_r": 1.0,
                },
            }
        ],
    }

    variants = extract_variant_summaries(payload)

    assert variants == [
        {
            "take_multiple": 0.25,
            "stop_multiple": 0.5,
            "summary": {
                "total_trades_opened": 10,
                "win_rate": 60.0,
                "total_pnl_r": 1.0,
            },
        }
    ]


def test_analyze_backtest_result_ranks_variants_and_builds_filter_candidates() -> None:
    payload = {
        "config": {
            "take_multiple": 0.25,
            "stop_multiple": 1.0,
        },
        "summary": {
            "total_trades_opened": 4,
            "losses": 2,
        },
        "variant_summaries": [
            {
                "take_multiple": 0.25,
                "stop_multiple": 1.0,
                "summary": {
                    "total_trades_opened": 4,
                    "win_rate": 50.0,
                    "total_pnl_r": -1.0,
                    "total_pnl_signal_r": -1.0,
                    "average_pnl_r": -0.25,
                    "profit_factor": 0.7,
                    "max_equity_drawdown_r": 2.0,
                    "average_win_r": 0.25,
                    "average_loss_r": -1.0,
                },
            },
            {
                "take_multiple": 0.5,
                "stop_multiple": 0.25,
                "summary": {
                    "total_trades_opened": 4,
                    "win_rate": 50.0,
                    "total_pnl_r": 2.0,
                    "total_pnl_signal_r": 0.5,
                    "average_pnl_r": 0.5,
                    "profit_factor": 1.8,
                    "max_equity_drawdown_r": 1.0,
                    "average_win_r": 2.0,
                    "average_loss_r": -1.0,
                },
            },
            {
                "take_multiple": 1.0,
                "stop_multiple": 1.0,
                "summary": {
                    "total_trades_opened": 4,
                    "win_rate": 25.0,
                    "total_pnl_r": 0.5,
                    "total_pnl_signal_r": 0.5,
                    "average_pnl_r": 0.125,
                    "profit_factor": 1.1,
                    "max_equity_drawdown_r": 1.5,
                    "average_win_r": 1.0,
                    "average_loss_r": -0.2,
                },
            },
        ],
        "trades": [
            {
                "pattern": "pin_bar",
                "signal_timeframe": "15m",
                "direction": "long",
                "context_higher_timeframe_bias": "bearish",
                "context_volatility_regime": "expanded",
                "context_range_position_pct": 80.0,
                "context_atr_pct": 1.2,
                "context_signal_range_to_atr_ratio": 1.5,
                "context_distance_to_recent_high_pct": 0.2,
                "context_distance_to_recent_low_pct": 1.3,
                "signal_hour": 10,
                "signal_weekday_name": "friday",
                "signal_range_pct": 1.0,
                "risk_pct_from_entry": 0.5,
                "signal_volatility_increase_max_pct": 20.0,
                "signal_volume_increase_max_pct": 30.0,
                "pnl_r": -1.0,
            },
            {
                "pattern": "pin_bar",
                "signal_timeframe": "15m",
                "direction": "long",
                "context_higher_timeframe_bias": "bearish",
                "context_volatility_regime": "expanded",
                "context_range_position_pct": 85.0,
                "context_atr_pct": 1.3,
                "context_signal_range_to_atr_ratio": 1.7,
                "context_distance_to_recent_high_pct": 0.1,
                "context_distance_to_recent_low_pct": 1.5,
                "signal_hour": 10,
                "signal_weekday_name": "friday",
                "signal_range_pct": 1.2,
                "risk_pct_from_entry": 0.6,
                "signal_volatility_increase_max_pct": 22.0,
                "signal_volume_increase_max_pct": 32.0,
                "pnl_r": -0.5,
            },
            {
                "pattern": "inside_bar",
                "signal_timeframe": "1h",
                "direction": "short",
                "context_higher_timeframe_bias": "bullish",
                "context_volatility_regime": "normal",
                "context_range_position_pct": 35.0,
                "context_atr_pct": 0.8,
                "context_signal_range_to_atr_ratio": 0.9,
                "context_distance_to_recent_high_pct": 2.5,
                "context_distance_to_recent_low_pct": 0.4,
                "signal_hour": 14,
                "signal_weekday_name": "saturday",
                "signal_range_pct": 3.0,
                "risk_pct_from_entry": 1.5,
                "signal_volatility_increase_max_pct": 50.0,
                "signal_volume_increase_max_pct": 60.0,
                "pnl_r": 1.5,
            },
            {
                "pattern": "inside_bar",
                "signal_timeframe": "1h",
                "direction": "short",
                "context_higher_timeframe_bias": "bullish",
                "context_volatility_regime": "normal",
                "context_range_position_pct": 30.0,
                "context_atr_pct": 0.9,
                "context_signal_range_to_atr_ratio": 0.8,
                "context_distance_to_recent_high_pct": 2.8,
                "context_distance_to_recent_low_pct": 0.3,
                "signal_hour": 14,
                "signal_weekday_name": "saturday",
                "signal_range_pct": 4.0,
                "risk_pct_from_entry": 2.0,
                "signal_volatility_increase_max_pct": 55.0,
                "signal_volume_increase_max_pct": 65.0,
                "pnl_r": 1.0,
            },
        ],
    }

    analysis = analyze_backtest_result(
        payload,
        top_n=3,
        bucket_count=2,
        min_group_trades=2,
    )

    assert analysis["primary_variant"] == {
        "take_multiple": 0.25,
        "stop_multiple": 1.0,
    }
    assert analysis["top_variants_by_total_pnl"][0]["take_multiple"] == 0.5
    assert analysis["top_variants_by_total_pnl"][0]["stop_multiple"] == 0.25
    assert analysis["top_variants_by_profit_factor"][0]["take_multiple"] == 0.5
    assert analysis["grouped_stats"]["by_level_weight"][0]["group"] == "none"
    assert analysis["grouped_stats"]["by_level_type"][0]["group"] == "none"
    assert analysis["grouped_stats"]["by_higher_timeframe_bias"][0]["group"] == "bearish"
    assert analysis["grouped_stats"]["by_volatility_regime"][0]["group"] == "expanded"

    hour_candidates = analysis["candidate_filters"]["by_hour"]
    assert len(hour_candidates) == 1
    assert hour_candidates[0]["group"] == "10"
    assert hour_candidates[0]["loss_rate"] == 100.0

    weekday_candidates = analysis["candidate_filters"]["by_weekday"]
    assert len(weekday_candidates) == 1
    assert weekday_candidates[0]["group"] == "friday"

    bias_candidates = analysis["candidate_filters"]["by_higher_timeframe_bias"]
    assert len(bias_candidates) == 1
    assert bias_candidates[0]["group"] == "bearish"


def test_select_variant_trades_reads_variant_trades_from_grid_export() -> None:
    payload = {
        "config": {
            "take_multiple": 1.0,
            "stop_multiple": 1.0,
        },
        "trades": [{"id": "primary"}],
        "variant_trades": {
            "take=1.25|stop=0.75": [{"id": "variant"}],
        },
    }

    trades = select_variant_trades(
        payload,
        take_multiple=1.25,
        stop_multiple=0.75,
    )

    assert trades == [{"id": "variant"}]
