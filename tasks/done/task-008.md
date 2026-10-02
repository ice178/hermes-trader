# Task: Scan historical patterns manually over a date range

## Status

Done

Owner: Tomasso / Codex

Updated: 2026-09-25

## Context and problem

The user requested a manual signal search with start/end date parameters.
The backtest runner already accepts dates but also simulates trades and uses
different default pattern/metric filters. The live scanner only evaluates the
latest freshly closed candle. The file scanner accepts a recent candle count.

## Goal

Add a standalone manual scan command using the live detector and metric rules,
with required --date-from/--date-to and configurable market/timeframes. Print
results by default; send historical notifications only with --send-telegram.

## Confirmed scope

- Implement a date-range scan independent of the production timer.
- The user confirmed: keep scheduled scans alongside the separate manual command.
  No production scheduling or systemd changes are needed.
- Do not simulate trades or apply current manual price areas to historical
  signals (there is no historical area snapshot/lifecycle reconstruction).
- No live exchange/Telegram calls or production deployment during implementation.

## Acceptance criteria

- [x] Both dates are required and validated before any network request.
- [x] Date-only --date-to includes the whole day; naive input is UTC, explicit
  ISO timezone offsets are honored. Datetime bounds are start-inclusive/end-exclusive.
- [x] The date range selects final-candle close times, not opening times.
- [x] Prior context is fetched so patterns at the start boundary are detectable.
- [x] Every eligible historical closed candle is evaluated, without the live
  freshness limit. Future/open candles and gaps in required context are excluded.
- [x] All live pattern types and the optional metric filter are supported.
- [x] Paginated loading and overlapping candles do not duplicate results.
- [x] Terminal-only runs require no Telegram credentials; delivery is opt-in
  and historical messages are clearly labeled.
- [x] CLI usage, limitations, and scheduler behavior are documented.
- [x] Focused tests and the complete suite pass without live external requests.

## Implementation plan

1. Reuse the existing historical loader/date parser and common signal helpers.
2. Add a pure historical window evaluator and a loader wrapper with warmup.
3. Add src/scan_signals.py CLI with dates, exchange, symbols, timeframes,
   fetch size, metric-filter overrides and optional Telegram delivery.
4. Validate dates/timeframes before connector construction, and distinguish
   missing market data from a successful scan with zero matches.
5. Add tests for boundaries, timezones, warmup, gaps, open candles, pagination,
   metric filtering, defaults and optional delivery; document example commands.
6. Resolve the scheduling question, update status/handoff, run regressions.

## Test plan

Use synthetic OHLCV and fake connectors/Telegram clients. Run focused historical
scan tests, CLI --help, then python3 -m pytest. Do not fetch real candles or send
messages. Check git diff --check.

## Risks

Exchanges may limit historical depth or return incomplete data. Explain the
loaded candle count; do not claim zero patterns when no usable in-range candles
were returned. Repeated explicit Telegram scans can send repeated historical
messages. Date-only interpretation is UTC even though notifications display Madrid.

## Review and validation

Implemented `src/hermes_trading/historical_signals.py` for historical window
selection and `src/scan_signals.py` for the manual CLI. Added usage and date
semantics to README and 27 offline tests in `tests/test_historical_signals.py`.
Existing Task 007 changes remain in the worktree; this task did not modify
production scheduling, systemd units, or the existing backtest behavior.

Checks:

- Focused initial historical tests: 23 passed; four additional cases cover
  railway tracks, inside bars and both engulfing directions.
- Final `python3 -m pytest -q`: 235 passed.
- `python3 src/scan_signals.py --help`: passed without network access.
- `git diff --check`: passed.
- Tests use fake connectors/Telegram clients; no real scans or messages sent.

## Handoff

Done locally. Use `python3 src/scan_signals.py --date-from YYYY-MM-DD
--date-to YYYY-MM-DD` plus optional exchange/symbol/timeframe flags. Terminal
output is the default; `--send-telegram` explicitly enables labeled historical
notifications. The user confirmed that the existing schedule should remain.

The exchange may restrict history or supply incomplete data; the CLI reports
loaded/evaluated counts and warns on missing context. Current manual areas are
not applied retroactively. No deployment, commit, or push was performed.

## Follow-up

[Task 009](task-009.md) changes manual input defaults to Europe/Madrid and adds
explicit testing of current areas with --check-levels. The original Task 008
UTC/no-area behavior above records the initial implementation.
