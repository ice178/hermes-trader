# Task: Process only newly closed candles

## Status

Done

Owner: Tomasso / Codex

Updated: 2026-08-02

## Context

The Telegram signal bot runs every 15 minutes for `15m`, `30m`, `1h`, and `4h` timeframes. It currently fetches 24 candles, removes the still-open candle, evaluates every historical window, and stores sent-signal keys in JSON to suppress repeated messages.

## Problem

Repeated historical evaluation makes persistent sent-message state necessary during normal operation. The bot should instead decide whether a timeframe has a newly closed candle and evaluate only that candle, using earlier candles solely as pattern and metric context.

## Goal

Make the production scan stateless: process only the latest candle when it closed within the current 15-minute scan window, send any resulting signals, and write no sent-message cache or watermark.

## Non-goals

- Catching up signals missed during downtime longer than the freshness window.
- Guaranteeing deduplication when the bot is started manually more than once in the same scan window.
- Changing pattern definitions, symbols, timeframes, thresholds, or message formatting.
- Changing backtest behavior beyond shared helper compatibility.

## Current understanding

- `is_candle_closed()` already excludes an in-progress candle by comparing its opening timestamp plus timeframe duration with `now`.
- `latest_matches()` returns only matches attached to the final candle in a supplied batch.
- Four closed candles provide the context currently used by supported multi-candle patterns and their metric references.
- At 17:31, the latest `15m` and `30m` candles normally closed at 17:30 and are fresh. The latest `1h` candle closed at 17:00 and is no longer fresh.
- Freshness must be derived from exchange timestamps and timeframe durations, not Madrid wall-clock assumptions.

## Decision

For each symbol and timeframe:

1. Fetch and retain closed candles only.
2. Select the final four closed candles as the evaluation batch.
3. Compute the final candle close time from its opening timestamp and timeframe.
4. Evaluate only when its close age is at least zero and less than the 15-minute scan interval.
5. Do not load or save sent-signal state.

This intentionally favors simplicity over catch-up guarantees. The `systemd` timer is the normal single scheduler. A delayed run within 15 minutes still processes the close; a longer outage may miss it. Repeated manual runs inside one freshness window may duplicate a notification.

## Open questions

- [x] Persistent state is intentionally removed.
- [x] Missed closes older than 15 minutes are intentionally skipped.
- [x] Repeated manual runs in one freshness window may duplicate messages and are operationally discouraged.

## Acceptance criteria

- [x] An open/in-progress candle is never evaluated for a production signal.
- [x] Only the final fresh closed candle in each symbol/timeframe is evaluated.
- [x] At a `:01` run, applicable `15m`, `30m`, and `1h` closes are eligible; at `:16` only the new `15m` close is eligible.
- [x] `4h` eligibility follows exchange/UTC candle timestamps rather than local timezone arithmetic.
- [x] Multi-candle patterns retain sufficient preceding closed-candle context.
- [x] A candle exactly 15 minutes old is no longer fresh.
- [x] The production bot does not read or write `signals_bot_sent.json` or another deduplication state file.
- [x] Deployment configuration requires no writable runtime-state directory.
- [x] Tests cover before-close, exact-close, fresh, expired, and multi-timeframe cases.
- [x] The full test suite passes.

## Implementation notes

Likely relevant files:

- `src/signals_bot.py`
- `src/hermes_trading/time_utils.py`
- `tests/test_time_utils.py`
- focused production-loop selection tests
- `.env.example`, systemd units, `README.md`, and `docs/server-deployment.md`

Keep the freshness calculation pure and test it with fixed UTC millisecond timestamps. Preserve the existing user change that adds `XRP/USDT`. Do not delete the legacy local JSON file without explicit approval.

## Test plan

- Parametrize all configured timeframes with fixed opening, close, and current timestamps.
- Verify one millisecond before close, exact close, just after close, and exactly 15 minutes after close.
- Verify consecutive scheduled slots select the expected timeframes.
- Verify the detector receives only a final four-candle batch.
- Exercise a multi-candle pattern on the final fresh candle.
- Verify the production path performs no state-file writes.
- Run `python3 -m pytest`.

## Agent instructions

Implement the agreed stateless model. Do not add a cache, watermark, database, or migration. Do not alter strategy thresholds or pattern detection. Do not make live Telegram or exchange calls during tests.

## Review notes

- Production and deployment files contain no sent-state path, read, or write.
- The legacy local `src/signals_bot_sent.json` was not deleted and remains ignored by Git.
- A fresh candle is eligible from its exact close time until one millisecond before it becomes 15 minutes old.
- A run delayed by 15 minutes or more intentionally skips that close.
- Repeated direct runs during one freshness window can repeat a notification; the normal `systemd` timer runs once per slot.
- Existing pattern detection, filters, symbols, and message formatting are unchanged.
- No live Telegram or exchange requests were made.
- The user confirmed that the stateless bot operates on the deployed Ubuntu timer.

## Handoff

Completed and deployed with task 001. Final full suite: `82 passed`. The intentional operational tradeoff remains: an outage of 15 minutes or more may skip a signal, while repeated manual runs within one freshness window may duplicate one.
