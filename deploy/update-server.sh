#!/usr/bin/env bash
set -Eeuo pipefail

readonly APP_DIR="/opt/hermes-trading/app"
readonly RUNTIME_USER="hermes"
readonly ENV_FILE="/etc/hermes-trading/hermes-signals-bot.env"
readonly SERVICE_NAME="hermes-signals-bot.service"
readonly TIMER_NAME="hermes-signals-bot.timer"
readonly SYSTEMD_DIR="/etc/systemd/system"

readonly GIT="/usr/bin/git"
readonly INSTALL="/usr/bin/install"
readonly PYTHON="/usr/bin/python3"
readonly SUDO="/usr/bin/sudo"
readonly SYSTEMCTL="/usr/bin/systemctl"
readonly SYSTEMD_ANALYZE="/usr/bin/systemd-analyze"

usage() {
    echo "Usage: sudo ${APP_DIR}/deploy/update-server.sh"
}

fail() {
    echo "Error: $*" >&2
    exit 1
}

as_runtime_user() {
    "${SUDO}" -u "${RUNTIME_USER}" -- "$@"
}

if (( $# != 0 )); then
    usage >&2
    exit 2
fi

if (( EUID != 0 )); then
    fail "run this script as root with sudo"
fi

# Continue from a temporary copy so updating the Git worktree cannot modify the
# script while Bash is still reading it.
if [[ "${HERMES_UPDATE_BOOTSTRAPPED:-0}" != "1" ]]; then
    temporary_script="$(/usr/bin/mktemp /tmp/hermes-update-server.XXXXXX)"
    "${INSTALL}" -o root -g root -m 0700 "${BASH_SOURCE[0]}" "${temporary_script}"
    if HERMES_UPDATE_BOOTSTRAPPED=1 "${temporary_script}"; then
        exit_code=0
    else
        exit_code=$?
    fi
    /usr/bin/rm -f "${temporary_script}"
    exit "${exit_code}"
fi

for command_path in \
    "${GIT}" \
    "${INSTALL}" \
    "${PYTHON}" \
    "${SUDO}" \
    "${SYSTEMCTL}" \
    "${SYSTEMD_ANALYZE}"; do
    [[ -x "${command_path}" ]] || fail "required command not found: ${command_path}"
done

/usr/bin/id "${RUNTIME_USER}" >/dev/null 2>&1 \
    || fail "runtime user does not exist: ${RUNTIME_USER}"
[[ -d "${APP_DIR}/.git" ]] || fail "expected Git worktree at ${APP_DIR}"
[[ -f "${ENV_FILE}" ]] || fail "runtime environment file is missing: ${ENV_FILE}"
[[ -f "${APP_DIR}/deploy/systemd/${SERVICE_NAME}" ]] \
    || fail "repository service unit is missing"
[[ -f "${APP_DIR}/deploy/systemd/${TIMER_NAME}" ]] \
    || fail "repository timer unit is missing"

if [[ -n "$(as_runtime_user "${GIT}" -C "${APP_DIR}" status --porcelain --untracked-files=no)" ]]; then
    fail "tracked files contain local changes; commit or restore them before deploying"
fi

echo "Fetching origin/main..."
as_runtime_user "${GIT}" -C "${APP_DIR}" fetch --prune origin main
as_runtime_user "${GIT}" -C "${APP_DIR}" show-ref --verify --quiet refs/heads/main \
    || fail "local main branch does not exist"
as_runtime_user "${GIT}" -C "${APP_DIR}" show-ref --verify --quiet refs/remotes/origin/main \
    || fail "origin/main was not fetched"
as_runtime_user "${GIT}" -C "${APP_DIR}" merge-base --is-ancestor main origin/main \
    || fail "local main has diverged from origin/main"
as_runtime_user "${GIT}" -C "${APP_DIR}" merge-base --is-ancestor HEAD origin/main \
    || fail "the deployed commit is not an ancestor of origin/main"

previous_commit="$(as_runtime_user "${GIT}" -C "${APP_DIR}" rev-parse HEAD)"
deployment_started=0

deployment_failed() {
    exit_code=$?
    echo "Deployment failed with exit code ${exit_code}." >&2
    if (( deployment_started == 1 )); then
        echo "${TIMER_NAME} remains stopped to avoid running a partial deployment." >&2
        echo "Previous commit: ${previous_commit}" >&2
    fi
    exit "${exit_code}"
}
trap deployment_failed ERR

echo "Stopping the timer and any running scan..."
"${SYSTEMCTL}" stop "${TIMER_NAME}"
deployment_started=1
"${SYSTEMCTL}" stop "${SERVICE_NAME}"

echo "Updating the worktree to origin/main..."
as_runtime_user "${GIT}" -C "${APP_DIR}" checkout main
as_runtime_user "${GIT}" -C "${APP_DIR}" merge --ff-only origin/main

if [[ ! -x "${APP_DIR}/.venv/bin/python" ]]; then
    echo "Creating the virtual environment..."
    as_runtime_user "${PYTHON}" -m venv "${APP_DIR}/.venv"
fi

echo "Installing application dependencies..."
as_runtime_user "${APP_DIR}/.venv/bin/python" -m pip install --editable "${APP_DIR}"
as_runtime_user "${APP_DIR}/.venv/bin/python" -m pip check
as_runtime_user "${APP_DIR}/.venv/bin/python" -c "import hermes_trading"

echo "Installing and validating systemd units..."
"${INSTALL}" -o root -g root -m 0644 \
    "${APP_DIR}/deploy/systemd/${SERVICE_NAME}" \
    "${SYSTEMD_DIR}/${SERVICE_NAME}"
"${INSTALL}" -o root -g root -m 0644 \
    "${APP_DIR}/deploy/systemd/${TIMER_NAME}" \
    "${SYSTEMD_DIR}/${TIMER_NAME}"
"${SYSTEMCTL}" daemon-reload
"${SYSTEMD_ANALYZE}" verify \
    "${SYSTEMD_DIR}/${SERVICE_NAME}" \
    "${SYSTEMD_DIR}/${TIMER_NAME}"

echo "Enabling the production schedule..."
"${SYSTEMCTL}" enable --now "${TIMER_NAME}"
"${SYSTEMCTL}" is-active --quiet "${TIMER_NAME}"
deployment_started=0

deployed_commit="$(as_runtime_user "${GIT}" -C "${APP_DIR}" rev-parse HEAD)"
echo "Deployment completed successfully."
echo "Previous commit: ${previous_commit}"
echo "Deployed commit: ${deployed_commit}"
"${SYSTEMCTL}" list-timers --no-pager "${TIMER_NAME}"
