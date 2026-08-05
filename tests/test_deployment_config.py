from pathlib import Path
import subprocess


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_signal_bot_timer_uses_madrid_trading_window() -> None:
    timer_path = (
        REPOSITORY_ROOT / "deploy" / "systemd" / "hermes-signals-bot.timer"
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


def test_server_update_script_has_valid_bash_syntax() -> None:
    script_path = REPOSITORY_ROOT / "deploy" / "update-server.sh"

    result = subprocess.run(
        ["bash", "-n", str(script_path)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_server_update_script_enforces_safe_deployment_order() -> None:
    script_path = REPOSITORY_ROOT / "deploy" / "update-server.sh"
    script = script_path.read_text(encoding="utf-8")

    assert "set -Eeuo pipefail" in script
    assert 'readonly APP_DIR="/opt/hermes-trading/app"' in script
    assert (
        'readonly ENV_FILE="/etc/hermes-trading/hermes-signals-bot.env"' in script
    )
    assert "status --porcelain --untracked-files=no" in script
    assert "merge-base --is-ancestor main origin/main" in script
    assert "merge --ff-only origin/main" in script
    assert 'readonly SYSTEMD_ANALYZE="/usr/bin/systemd-analyze"' in script
    assert '"${SYSTEMD_ANALYZE}" verify' in script
    assert "pip check" in script
    assert "systemctl start hermes-signals-bot.service" not in script

    fetch_position = script.index('fetch --prune origin main')
    stop_position = script.index('"${SYSTEMCTL}" stop "${TIMER_NAME}"')
    enable_position = script.index('"${SYSTEMCTL}" enable --now "${TIMER_NAME}"')
    verify_position = script.index('"${SYSTEMD_ANALYZE}" verify')

    assert fetch_position < stop_position < verify_position < enable_position
