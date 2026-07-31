from hermes_trading.backtest.policy_analysis import (
    ExitPolicy,
    ExitLeg,
    TradeExitObservation,
    evaluate_policy_pnl,
    parse_exit_policy,
    summarize_exit_policy,
)


def test_parse_exit_policy_adds_actual_remainder_for_scale_out() -> None:
    policy = parse_exit_policy("scale:0.5@1")

    assert policy == ExitPolicy(
        name="scale:0.5@1,0.5@actual",
        legs=(ExitLeg(0.5, 1.0), ExitLeg(0.5, None)),
    )


def test_evaluate_policy_pnl_uses_target_when_step_is_hit() -> None:
    trade = TradeExitObservation(pnl_r=-1.0, best_take_step_r=2.25)
    policy = parse_exit_policy("fixed:2")

    assert evaluate_policy_pnl(trade, policy) == 2.0


def test_summarize_exit_policy_handles_scale_out() -> None:
    trades = [
        TradeExitObservation(pnl_r=-1.0, best_take_step_r=2.5),
        TradeExitObservation(pnl_r=-1.0, best_take_step_r=1.25),
        TradeExitObservation(pnl_r=0.4, best_take_step_r=0.25),
    ]

    summary = summarize_exit_policy(
        trades,
        parse_exit_policy("scale:0.5@1,0.5@2"),
    )

    assert summary.win_trades == 2
    assert summary.loss_trades == 0
    assert summary.breakeven_trades == 1
    assert round(summary.total_pnl_r, 6) == 1.9
    assert round(summary.average_pnl_r, 6) == round(1.9 / 3, 6)
