# Task: Process only newly closed candles

## Status

Backlog

Owner: Tomasso / Codex

Updated: 2026-07-31

## Context

The Telegram signal bot runs every 15 minutes for `15m`, `30m`, `1h`, and `4h` timeframes. It currently fetches 24 candles, removes the still-open candle, and evaluates every remaining historical window on every run. A list of previously sent signal keys prevents most duplicate messages.

## Problem

Repeatedly evaluating historical candles makes the sent-signal list responsible for normal scheduling correctness. It also obscures which candles are actually new, grows state indefinitely, and makes missed or delayed runs harder to reason about.

The bot already checks whether each candle interval has elapsed, but it does not track which closed candles have been processed for each exchange, symbol, and timeframe.

## Goal

Evaluate signals only for candles that closed since the last successful processing point, while retaining enough earlier candles as context for multi-candle patterns and metric filters. Correctly catch up after a delayed or missed run without sending duplicates.

## Non-goals

- Changing price-action pattern definitions.
- Changing symbols, timeframes, volume/volatility thresholds, or message formatting.
- Changing the server deployment mechanism from task 001.
- Reworking backtest behavior unless shared production logic requires a compatible adjustment.

## Current understanding

- `is_candle_closed()` treats a candle as closed when its opening timestamp plus timeframe duration is not later than `now`.
- CCXT OHLCV timestamps are treated as candle opening timestamps.
- `latest_matches()` returns only matches attached to the final candle in a supplied batch.
- Four candles currently provide the context used by supported multi-candle patterns and their two reference candles.
- At 17:31, the newly closed candidates are normally the `15m` candle from 17:15–17:30 and the `30m` candle from 17:00–17:30. Timeframe boundaries must be derived from exchange timestamps rather than Madrid wall-clock assumptions.
- A persistent watermark is still required for downtime, delayed timers, restarts, and manual runs.

## Proposed state model

Store the last successfully processed candle timestamp for each combination of:

```text
exchange | symbol | timeframe
```

On each run, fetch enough closed candles to include both unprocessed candles and pattern context. Process unprocessed candles in chronological order, then advance the watermark only when the intended processing outcome is safely recorded.

The implementation must define whether a Telegram failure prevents the watermark from advancing and how partial success is retried without duplicating already delivered messages.

## Open questions

- [ ] Should the sent-signal key set remain temporarily as an additional idempotency layer?
- [ ] How many missed candles should one run catch up, and what should happen when the fetch limit is insufficient?
- [ ] What is the exact commit rule when one candle produces multiple messages and only some sends succeed?
- [ ] Should malformed or missing state fail closed, create a backup, or start from the latest candle?
- [ ] Is four-candle context sufficient for every supported and planned pattern, or should it be derived explicitly?

## Acceptance criteria

- [ ] An open/in-progress candle is never evaluated for a production signal.
- [ ] Each newly closed candle is processed at most once during normal repeated runs.
- [ ] `15m`, `30m`, `1h`, and `4h` are processed only when their own new candles are available.
- [ ] Multi-candle patterns receive sufficient preceding closed-candle context.
- [ ] A delayed run processes all recoverable newly closed candles in chronological order.
- [ ] A repeated run with no new candle sends nothing and does not change state unnecessarily.
- [ ] Telegram send failures have explicit, tested retry and watermark semantics.
- [ ] Missing, old-format, and malformed state have documented and tested behavior.
- [ ] Existing `signals_bot_sent.json` data is migrated, preserved as a temporary compatibility layer, or retired with a documented one-time behavior.
- [ ] Unit tests cover timeframe boundaries, exact close timestamps, delayed runs, repeated runs, and multi-candle patterns.
- [ ] The full test suite passes.

## Implementation notes

Likely relevant files:

- `src/signals_bot.py`
- `src/hermes_trading/time_utils.py`
- `src/hermes_trading/signal_filters.py`
- `tests/test_time_utils.py`
- new focused production-loop/state tests
- `.env.example` and `docs/server-deployment.md` if the state path or migration instructions change

Prefer a small explicit state structure over a database. Write state atomically so an interrupted write cannot silently turn the next run into a full replay. Avoid using local timezone calculations for exchange candle boundaries.

## Test plan

- Use fixed UTC timestamps rather than the real clock.
- Parametrize close-boundary cases for all configured timeframes.
- Verify behavior one millisecond before, exactly at, and after candle close.
- Verify consecutive 15-minute runs select the expected subset of timeframes.
- Simulate downtime with multiple newly closed candles.
- Exercise two- and three-candle patterns with earlier context candles.
- Simulate Telegram failure during a multi-message result.
- Verify state reload, atomic replacement, malformed state, and legacy state handling.
- Run `python3 -m pytest`.

## Agent instructions

Investigate and document failure semantics before implementation. Do not remove the existing sent-signal guard until equivalent idempotency is demonstrated by tests. Keep signal detection and strategy thresholds unchanged. Do not make live Telegram or exchange calls during tests.

## Review notes

Pending.

## Handoff

Task defined from the production-loop review during task 001. Recommended next step: investigate state transition semantics and propose a migration-compatible implementation plan before editing code.
