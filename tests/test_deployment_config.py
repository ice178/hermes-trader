from pathlib import Path
import json
import os
import subprocess
import sys

import pytest


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


def test_listener_unit_supervises_daemon_and_allows_shared_state() -> None:
    unit_dir = REPOSITORY_ROOT / "deploy" / "systemd"
    listener = (unit_dir / "hermes-levels-bot.service").read_text()
    scanner = (unit_dir / "hermes-signals-bot.service").read_text()
    assert "Type=simple" in listener
    assert "src/levels_bot.py" in listener
    assert "Restart=on-failure" in listener
    assert "RestartPreventExitStatus=78" in listener
    assert "TimeoutStopSec=60" in listener
    for unit in (listener, scanner):
        assert "StateDirectory=hermes-trading" in unit
        assert "StateDirectoryMode=0700" in unit
        assert "ProtectSystem=strict" in unit
        assert "User=hermes" in unit


def test_update_stops_listener_before_checkout_and_restarts_after_validation() -> None:
    script = (REPOSITORY_ROOT / "deploy" / "update-server.sh").read_text()
    stop = script.index('"${SYSTEMCTL}" stop "${LISTENER_NAME}"', script.index('trap deployment_failed ERR'))
    checkout = script.index('checkout main')
    verify = script.index('"${SYSTEMD_ANALYZE}" verify "${SYSTEMD_DIR}/${LISTENER_NAME}"')
    start = script.index('"${SYSTEMCTL}" start "${LISTENER_NAME}"')
    assert stop < checkout < verify < start
    assert 'enable --now "${LISTENER_NAME}"' not in script


@pytest.mark.parametrize("listener_enabled,fail_at", [
    (True, ""), (False, ""), (True, "verify"), (True, "timer"),
])
def test_update_lifecycle_with_simulated_system_commands(tmp_path, listener_enabled, fail_at):
    """Execute a redirected copy; never invoke real sudo, Git, or systemd."""
    app = tmp_path / "app"
    units = app / "deploy" / "systemd"
    units.mkdir(parents=True)
    (app / ".git").mkdir()
    (app / ".venv" / "bin").mkdir(parents=True)
    systemd = tmp_path / "systemd"
    systemd.mkdir()
    env_file = tmp_path / "runtime.env"
    env_file.write_text("unchanged")
    for name in ("hermes-signals-bot.service", "hermes-signals-bot.timer", "hermes-levels-bot.service"):
        (units / name).write_text("test unit")
    log = tmp_path / "commands.jsonl"
    stub = tmp_path / "stub"
    stub.write_text(f"#!{sys.executable}\n" + '''
import json, os, pathlib, shutil, sys
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ["TEST_COMMAND_LOG"], "a") as output:
    output.write(json.dumps([name, *args]) + "\\n")
if name == "sudo":
    os.execv(args[3], args[3:])
if name == "git" and "rev-parse" in args:
    print("a" * 40)
if name == "install":
    shutil.copyfile(args[-2], args[-1])
if name == "systemctl":
    listener = args[-1] == "hermes-levels-bot.service"
    if listener and args[0] in ("is-enabled", "is-active"):
        sys.exit(0 if os.environ["TEST_LISTENER_ENABLED"] == "1" else 1)
    if args[0] == "enable" and os.environ["TEST_FAIL_AT"] == "timer":
        sys.exit(1)
if name == "systemd-analyze" and os.environ["TEST_FAIL_AT"] == "verify":
    sys.exit(1)
''')
    stub.chmod(0o700)
    commands = tmp_path / "bin"
    commands.mkdir()
    names = ("git", "install", "python3", "sudo", "systemctl", "systemd-analyze", "id")
    for name in names:
        (commands / name).symlink_to(stub)
    (app / ".venv" / "bin" / "python").symlink_to(stub)
    script = (REPOSITORY_ROOT / "deploy" / "update-server.sh").read_text()
    script = script.replace('/opt/hermes-trading/app', str(app))
    script = script.replace('/etc/hermes-trading/hermes-signals-bot.env', str(env_file))
    script = script.replace('/etc/systemd/system', str(systemd))
    for name in names:
        script = script.replace(f'/usr/bin/{name}', str(commands / name))
    script = script.replace('if (( EUID != 0 )); then', 'if false; then')
    redirected = tmp_path / "update.sh"
    redirected.write_text(script)
    result = subprocess.run(["bash", str(redirected)], capture_output=True, text=True, env={
        **os.environ, "HERMES_UPDATE_BOOTSTRAPPED": "1", "TEST_COMMAND_LOG": str(log),
        "TEST_LISTENER_ENABLED": "1" if listener_enabled else "0", "TEST_FAIL_AT": fail_at,
    })
    assert (result.returncode == 0) is (not fail_at), result.stderr
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    stops = [call for call in calls if call[:2] == ["systemctl", "stop"]]
    listener_stop = ["systemctl", "stop", "hermes-levels-bot.service"]
    listener_start = ["systemctl", "start", "hermes-levels-bot.service"]
    assert (listener_stop in stops) is listener_enabled
    if listener_enabled and fail_at != "verify":
        assert calls.index(listener_stop) < calls.index(listener_start)
    if fail_at:
        assert calls[-1] == listener_stop
    elif not listener_enabled:
        assert listener_start not in calls
    assert env_file.read_text() == "unchanged"
