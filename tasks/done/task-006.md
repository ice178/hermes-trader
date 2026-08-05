# Task: Add a manual server update script

## Status

Done

Owner: Tomasso / Codex

Updated: 2026-08-05

## Context

Production runs from `/opt/hermes-trading/app` under `systemd`. Updating it
currently requires a sequence of manual Git, virtualenv, unit installation,
and timer commands.

## Problem

Running the commands individually is easy to do incompletely and can leave
stale code, dependencies, units, or timer state.

## Goal

Provide one repository-owned shell script that an operator can run with
`sudo` on the server to safely update production from `origin/main`.

## Non-goals

- Replacing the planned GitHub Actions deployment in task-004.
- Running a live signal scan during deployment.
- Changing secrets or application behavior.
- Automatically rolling back a failed dependency or systemd update.

## Current understanding

- The runtime user is `hermes` and the app path is
  `/opt/hermes-trading/app`.
- Secrets live outside Git at
  `/etc/hermes-trading/hermes-signals-bot.env`.
- A partial deployment must not restart the timer.

## Open questions

- [x] Update only `main` using a fast-forward operation.
- [x] Do not run a live scan by default.
- [x] Leave the timer stopped after a partial deployment and report recovery
  context.

## Acceptance criteria

- [x] The script requires root and validates the expected server layout.
- [x] It rejects tracked local changes and divergent Git history.
- [x] It fetches and validates `origin/main` before stopping production.
- [x] It updates the worktree as `hermes` using fast-forward only.
- [x] It creates the venv when missing and refreshes runtime dependencies.
- [x] It installs and validates both systemd units.
- [x] It never overwrites the external environment file.
- [x] It does not run the live signal service during deployment.
- [x] It starts the timer only after all update checks succeed.
- [x] Documentation explains first use, normal use, and failure behavior.
- [x] Automated tests and shell syntax validation pass.

## Implementation notes

The script runs from a temporary copy so a Git update cannot change the file
while Bash is executing it. Fixed production paths keep the privileged scope
explicit. Deployment failure after production is stopped deliberately leaves
the timer stopped rather than running a partial release.

## Test plan

- Run `bash -n deploy/update-server.sh`.
- Add focused deployment configuration tests for the script safeguards.
- Run `python3 -m pytest tests/test_deployment_config.py`.
- Run `python3 -m pytest`.

## Agent instructions

Do not make live Telegram, exchange, SSH, Git fetch, or systemd calls while
testing locally.

## Review notes

Added `deploy/update-server.sh` with strict Bash behavior, root and layout
validation, clean fast-forward Git updates as `hermes`, virtualenv dependency
checks, installation and verification of both systemd units, and timer startup
only after success. The script executes from a temporary copy so updating its
worktree source cannot interrupt the current deployment.

Verification on 2026-08-05:

- `bash -n deploy/update-server.sh`: passed.
- `python3 -m pytest tests/test_deployment_config.py`: 3 passed.
- `python3 -m pytest`: 116 passed.
- `git diff --check`: passed.

`shellcheck` was not installed in the local environment. No server, systemd,
SSH, Telegram, exchange, or remote Git action was executed.

## Handoff

Done. After the change is committed and pushed, bootstrap the script once with
the documented manual fast-forward pull. Subsequent releases use the script
directly with `sudo`.
