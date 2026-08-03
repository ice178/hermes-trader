# Task: Add Madrid trading hours and signal context to notifications

## Status

Review

Owner: Tomasso / Codex

Updated: 2026-08-03

## Context

The deployed Telegram signal bot currently runs every 15 minutes around the clock. Production signals are discarded unless both volatility and volume exceed the configured threshold relative to two reference candles. Notifications show the percentage comparisons but do not identify the active market session.

## Problem

The desired production behavior is:

- run from `08:01` through a final `23:01` launch in `Europe/Madrid`;
- notify for valid price-action patterns regardless of volume or volatility increase by default, with an optional production filter;
- retain volume and volatility as descriptive notification context;
- identify the active market session or overlapping sessions;
- allow production to switch between metric filtering and informational-only
  metrics through environment configuration;
- show the signal candle close time rather than its opening timestamp.

The repository has no existing market-session classifier. `market_context.py` covers higher-timeframe bias, ranges, ATR, and volatility regime only.

## Goal

Limit scheduled production runs to the agreed Madrid-time window and enrich every production signal notification with clear volume, volatility, and market-session status without changing pattern detection.

## Non-goals

- Changing price-action pattern definitions.
- Adding a persistent signal cache.
- Changing the 15-minute scan cadence within the allowed hours.
- Redesigning the broader backtest engine unless explicitly requested.

## Current understanding

- The deployed `systemd` timer currently runs at minutes `01`, `16`, `31`, and `46` every hour.
- `build_filtered_signal()` returns `None` when either metric pair fails the 10% threshold, so production never sends those pattern matches.
- Notifications already include both percentage comparisons against the relevant two reference candles.
- Signal availability is tied to the closing time of the final pattern candle; this is the natural timestamp for session classification.
- Europe/Madrid and major financial centers require DST-aware timezone handling.

## Open questions

- [x] Run at `08:01`, then `:01`, `:16`, `:31`, and `:46` through 22:46, with one final run at `23:01` Madrid time.
- [x] Remove the volume/volatility gate only from the live Telegram bot; preserve existing backtest and export filtering.
- [x] Classify by signal candle close time using Tokyo 09:00–18:00, London 08:00–17:00, and New York 08:00–17:00 in each session's local IANA timezone. Do not include Sydney.
- [x] “Volume/volatility present” keeps the existing rule: at least 10% above both reference candles.
- [x] Default to informational-only metrics; allow the metric gate to be enabled through environment configuration.
- [x] Label metric mode clearly in every signal notification.
- [x] Display the signal candle close timestamp in Madrid time.

## Acceptance criteria

- [x] The systemd schedule is explicitly evaluated in `Europe/Madrid` and follows DST changes.
- [x] No production run is scheduled outside the agreed daily window.
- [x] A valid price-action pattern can produce a notification even when volume or volatility does not pass the descriptive threshold.
- [x] Notifications retain the percentage comparisons and show a clear yes/no status for volume and volatility.
- [x] Notifications show one active market session, all overlapping sessions, or an explicit no-session label.
- [x] Session classification is deterministic and covered at starts, ends, overlaps, and DST boundaries.
- [x] Existing price-action and fresh-candle behavior remains unchanged.
- [x] Deployment documentation explains how to install and reload the updated timer.
- [x] The full test suite passes.
- [x] Environment configuration selects filtered or informational-only live behavior without changing backtests.
- [x] Each notification states whether the metric filter is enabled or metrics are informational only.
- [x] Each notification labels and displays the final pattern candle close time in Madrid time.
- [x] Configuration modes and close-time formatting are covered by tests.

## Implementation notes

Likely relevant files:

- `deploy/systemd/hermes-signals-bot.timer`
- `src/signals_bot.py`
- `src/hermes_trading/signal_filters.py`
- a focused market-session module rather than adding unrelated behavior to `market_context.py`
- notification, timer, and session tests
- `docs/server-deployment.md`

Prefer IANA timezones and timezone-aware datetimes. Preserve the existing filtered APIs for backtests unless the user explicitly expands scope. Consider separating metric calculation from metric-based acceptance so production can enrich an unfiltered pattern without duplicating calculations.

## Test plan

- Verify the systemd calendar expression for the agreed first and final Madrid runs.
- Test session starts, exclusive ends, overlaps, no-session periods, and summer/winter DST behavior.
- Test notifications for all four combinations of volume/volatility yes/no.
- Verify a below-threshold pattern is now sent by the production path.
- Confirm backtest filtering remains unchanged if it is outside scope.
- Run `python3 -m pytest`.

## Agent instructions

Keep production and backtest filtering behavior separate. Do not make live Telegram or exchange requests during tests.

## Review notes

`SIGNAL_METRIC_FILTER_ENABLED=0` keeps metrics informational; truthy values
enable the existing 10%-against-both-references gate for both volatility and
volume. Notifications explicitly distinguish these modes and now show `Candle
close` in Madrid time. Backtest filtering remains unchanged. `python3 -m
pytest`: 113 passed.

## Handoff

Before deployment, set `SIGNAL_METRIC_FILTER_ENABLED` in
`/etc/hermes-trading/hermes-signals-bot.env`, pull the updated code, and perform
one manual service run when a real Telegram notification is acceptable. No live
Telegram or exchange request was made during implementation.
