# Task: Prepare the Telegram signal bot for server deployment

## Status

Review

Owner: Tomasso / Codex

Updated: 2026-07-31

## Context

The Telegram signal bot currently runs locally through a macOS LaunchAgent. It needs a reproducible and secure deployment path for a hosted server.

## Problem

Runtime configuration and deployment steps are not documented consistently. At least one Telegram token is hardcoded in a tracked helper, and there is no safe environment example or server runbook.

## Goal

Make the bot safe and straightforward to configure, install, run, inspect, restart, and update on a server without committing credentials.

## Non-goals

- Choosing or provisioning a hosting provider.
- Changing trading or signal behavior.
- Adding containers or deployment platforms unless the existing projects clearly justify them.
- Automating CI/CD.

## Current understanding

- The bot entry point is `src/signals_bot.py`.
- Telegram configuration was intended to load from environment variables, but an early return bypassed that logic.
- Telegram credentials were hardcoded in two tracked modules and exist in Git history; the old token must be revoked independently.
- The previous local schedule used macOS `launchd` and ran four times per hour.
- `/Users/tomasso/develop/ice-budget` uses useful `systemd` conventions, but its CI/CD, release symlinks, and VPS hardening process are unnecessary for this lightweight deployment.
- The bot is a one-shot scanner, so a `systemd` timer is a better fit than a permanently restarting service.
- Task 002 changes the production scan to stateless fresh-candle processing, so the server requires no writable runtime-state directory.

## Investigation and decision

Use a minimal `systemd` oneshot service with a timer that preserves the previous 15-minute schedule. Let `systemd` load a root-controlled environment file. Local shells load `.env` explicitly; Python entry points read process environment only. Run as a dedicated unprivileged user and use journald for logs.

Strategy settings such as symbols, timeframes, and signal thresholds remain code-owned in this task; moving them would change strategy behavior and broaden deployment configuration unnecessarily.

## Implementation plan

1. Remove hardcoded Telegram values and restore real environment validation.
2. Add a safe `.env.example` and ignore local configuration and runtime output.
3. Keep deployment configuration compatible with the stateless production loop from task 002.
4. Add a hardened oneshot service and 15-minute timer.
5. Document installation, secrets, state migration, verification, updates, rollback, and removal.
6. Add focused configuration tests and run the full suite.

## Open questions

- [ ] Confirm the server operating system and whether `systemd` is available.
- [x] Confirm that task 002 removes the need for sent-signal state on the server.
- [x] Preserve the previous schedule at minutes 01, 16, 31, and 46 of every hour.

## Acceptance criteria

- [x] No active Telegram credential is hardcoded in tracked source.
- [x] Local `.env` files are ignored and a safe `.env.example` documents required variables.
- [x] The application receives runtime configuration through process environment without a dotenv dependency.
- [x] A server deployment guide covers install, configuration, initial verification, scheduled operation, logs, updates, restart, and rollback.
- [x] Stateless runtime behavior and secret-file permissions are documented.
- [x] Relevant focused tests and the full test suite pass, or failures are documented.

## Implementation notes

Implemented with existing environment-loading code and standard server facilities. The Linux/`systemd` assumption must be confirmed before applying the runbook to the actual host.

## Test plan

- Verify secret files are ignored and the example contains placeholders only.
- Test configuration failure when required environment variables are missing.
- Run focused Telegram/configuration tests.
- Run `python3 -m pytest`.
- Validate deployment commands and service configuration statically; do not contact Telegram or an exchange with live credentials.

## Agent instructions

Inspect the current runtime path and the reference deployment without exposing secrets. Keep deployment lightweight, avoid application behavior changes, and document all server assumptions.

## Review notes

- Current working tree contains no value matching the Telegram token format.
- Existing user change adding `XRP/USDT` to `src/signals_bot.py` was preserved.
- The old token remains recoverable from Git history and must be revoked; source cleanup alone does not invalidate it.
- The service and timer were reviewed statically on macOS, not executed on the target Linux host.
- No live Telegram message or exchange request was made during verification.

## Handoff

Implementation is ready for review with the stateless production loop from task 002. Confirm that the target host uses `systemd`, revoke the historical token, create the protected server environment file, then follow `docs/server-deployment.md`.
