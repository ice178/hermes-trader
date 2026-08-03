from pathlib import Path


def test_signal_bot_timer_uses_madrid_trading_window() -> None:
    timer_path = (
        Path(__file__).resolve().parents[1]
        / "deploy"
        / "systemd"
        / "hermes-signals-bot.timer"
    )
    on_calendar = [
        line
        for line in timer_path.read_text(encoding="utf-8").splitlines()
        if line.startswith("OnCalendar=")
    ]

    assert on_calendar == [
        "OnCalendar=*-*-* 08..22:01,16,31,46:00 Europe/Madrid",
        "OnCalendar=*-*-* 23:01:00 Europe/Madrid",
    ]
    assert "Persistent=no" in timer_path.read_text(encoding="utf-8")
