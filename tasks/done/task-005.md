# Task: Simplify Telegram signal notifications

## Status

Done

Owner: Tomasso / Codex

Updated: 2026-08-05

## Context

Signal notifications currently contain a separate `Signals found` message and
five metric-related lines: the metric-filter mode, an elevated YES/NO line for
each metric, and a percentage-comparison line for each metric. This makes a
notification unnecessarily long, especially when neither metric is elevated.

## Problem

The notification should emphasize the trading signal itself. Volume and
volatility are useful only as positive supporting context. Negative statuses and
the configured filtering mode do not need to occupy message space.

## Goal

Make each Telegram notification shorter:

- do not send the standalone `Signals found: N` message;
- remove the `Signal N/total` header from individual notifications without
  replacing it with another header;
- never show a `Metric filter` line;
- never show `Elevated volatility: YES/NO` or `Elevated volume: YES/NO` lines;
- show the existing `Volatility vs ...` percentage line only when volatility is
  at least 10% above both reference candles;
- show the existing `Volume vs ...` percentage line only when volume is at
  least 10% above both reference candles;
- omit the entire metric section when neither metric passes.

## Non-goals

- Changing `SIGNAL_METRIC_FILTER_ENABLED` behavior.
- Changing the 10% threshold or its comparison against both reference candles.
- Changing pattern detection, candle freshness, market sessions, scheduling, or
  backtests.
- Combining multiple signals into one Telegram message.

## Current understanding

- `src/signals_bot.py` sends one preliminary `Signals found` message before the
  individual signal messages.
- `format_signal_message()` always renders all metric-related lines.
- `metric_increase_passes()` already contains the correct per-metric threshold
  rule and should remain the single source of truth.
- `should_send_signal()` controls whether a signal is delivered when the
  configurable filter is enabled. Presentation changes must not alter this.

## Intended message format

When both metrics pass:

```text
Symbol: XRP/USDT
Timeframe: 1h
Pattern: Pin Bar
Direction: LONG
Open price: 1.0683
Candle close: 2026-08-03T11:00:00+02:00
Market session: London
Volatility vs previous 2 candles: +20.4% / +73.5%
Volume vs previous 2 candles: +64.1% / +36.9%
```

When only volatility passes, include the volatility line and omit the volume
line. When only volume passes, do the reverse. When neither passes, the message
ends after `Market session`.

Individual messages begin directly with `Symbol`. Signal counts do not appear
anywhere in the Telegram output.

## Open questions

- [x] Remove the entire `Signal N/total` header; do not replace it with `Signal`.

## Acceptance criteria

- [x] A scan sends no standalone signal-count summary.
- [x] Individual notifications contain no signal header or count and begin with
  `Symbol`.
- [x] Each detected signal still produces its own Telegram message.
- [x] `Metric filter` never appears in a signal notification.
- [x] Elevated YES/NO status lines never appear in a signal notification.
- [x] The volatility comparison appears only when volatility passes against
  both reference candles.
- [x] The volume comparison appears only when volume passes against both
  reference candles.
- [x] No blank lines or empty metric section remain when metrics are omitted.
- [x] `SIGNAL_METRIC_FILTER_ENABLED=0` still sends signals regardless of metric
  status.
- [x] `SIGNAL_METRIC_FILTER_ENABLED=1` still sends only signals for which both
  metrics pass.
- [x] Existing candle-close time and market-session formatting remain unchanged.
- [x] Tests cover all four pass/fail combinations for volume and volatility.
- [x] The full test suite passes.

## Implementation notes

Likely files:

- `src/signals_bot.py`
- `tests/test_signals_bot.py`

Remove the preliminary `client.send_text()` call that reports
`Signals found`. Remove the `Signal N/total` header and simplify formatter
arguments that are no longer needed. Preserve the existing deduplication.

Build optional metric lines independently and append only the passing ones.
Reuse `metric_increase_passes()` rather than duplicating the threshold rule.
Remove presentation-only helpers that become unused, such as
`metric_filter_label()` or `metric_status()`, but preserve filtering helpers
used by delivery logic.

## Test plan

- Parameterize message-format tests for:
  - volatility pass / volume pass;
  - volatility pass / volume fail;
  - volatility fail / volume pass;
  - volatility fail / volume fail.
- Assert presence of each percentage line only in its passing cases.
- Assert absence of `Metric filter`, `Elevated volatility`, and
  `Elevated volume` in every case.
- Test the bot send path with multiple results and assert that the number of
  Telegram calls equals the number of individual signals, with no extra summary
  call.
- Retain tests for the environment switch and filtered delivery behavior.
- Run `python3 -m pytest`.

## Agent instructions

Keep this change presentation-only. Do not reinterpret the metric threshold or
remove the optional production filter. Do not make live Telegram or exchange
requests during tests.

## Review notes

Removed the standalone count message and per-message signal header. The
formatter now appends volatility and volume comparisons independently only
when `metric_increase_passes()` accepts the corresponding pair. Delivery
filtering remains in `should_send_signal()` and is unchanged.

Verification on 2026-08-05:

- `python3 -m pytest tests/test_signals_bot.py`: 18 passed.
- `python3 -m pytest`: 114 passed.
- `git diff --check`: passed.

## Handoff

Done. No live Telegram or exchange requests were made. The remaining
deployment step is outside this task and is tracked separately.
