# Task: Enable signal metric filtering by default and document release

## Status

Done

Owner: Tomasso / Codex

Updated: 2026-10-02

## Context

The operator reports excessive live notifications and requests volume and
volatility filtering, plus instructions for releasing the pending changes.

## Problem

The existing filter is disabled by default. Updating code alone does not
override an existing production environment value of 0.

## Goal

Enable the existing 10% gate for both metrics against both reference candles
by default, and document publishing to main, server update, and verification.

## Non-goals

Changing patterns, reference candles, thresholds, scheduling, or backtests;
deploying to a server without its connection details; automated releases.

## Current understanding

The live bot and manual historical CLI share the environment parser.
Explicit false values remain supported; missing/blank configuration enables
filtering. Historical CLI flags continue to override environment settings.
The server updater preserves the external environment file and SQLite data.

## Acceptance criteria

- [x] Missing/blank configuration and the example environment enable filtering.
- [x] Explicit false settings and manual CLI overrides still work.
- [x] Delivery requires both metrics to pass both comparisons at 10% inclusive.
- [x] Release instructions cover existing environment overrides and verification.
- [x] Focused tests and the full offline test suite pass.

## Implementation notes

Reuse signal_metrics_pass; no changes to metric calculations or architecture.
Pending Tasks 007–009 remain in the worktree and must be included in the release.

## Test plan

Test configuration defaults, explicit overrides, all four threshold comparisons,
and the live main-to-Telegram path with fake market/Telegram clients. Check
historical CLI defaults and overrides. Run python3 -m pytest, CLI --help,
bash -n deploy/update-server.sh, and git diff --check.

## Handoff

Implemented in src/signals_bot.py and .env.example. Updated manual CLI help,
README, and docs/server-deployment.md. Configuration, delivery threshold, live
scan dispatch, and historical CLI regression coverage is in
tests/test_signals_bot.py and tests/test_historical_signals.py.

Validation: initial focused suite passed (77 tests); full python3 -m pytest -q
passed (264 tests, including the additional reverse CLI override case).
CLI --help, bash -n deploy/update-server.sh, and git diff --check passed.
No live requests, commits, pushes, or production changes were performed.

Release remains local with Tasks 007–009. Publish the complete changes to main,
set SIGNAL_METRIC_FILTER_ENABLED=1 in the existing server environment, run the
updater, and verify the deployed SHA and next scheduled scan. Existing explicit
0 values still disable the filter. Manual historical CLI now also defaults to
filtering; --no-metric-filter keeps all patterns available for inspection.
