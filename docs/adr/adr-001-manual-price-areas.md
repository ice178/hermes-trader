# ADR-001: Persistent manual price areas and a Telegram listener

## Status

Accepted

## Context

The scheduled scanner exits after each scan. Operators need responsive commands
and persistent point levels/zones without changing automatic liquidity levels.

## Decision

Run a separate foreground long-polling listener under systemd. Share a SQLite
database outside the checkout with the scanner; use WAL and short transactions.
Store canonical decimal prices as text to preserve exact identity. Keep manual
areas distinct from calculated liquidity levels. Source timeframe is metadata.

Commit command mutations, processed-update identity, cursor, and pending replies
together. Claim each reply durably before sending it. Do not retry ambiguous
delivery failures: sendMessage offers no idempotency key. This prevents repeated
replies but can lose a reply after a crash/timeout; operators can query /levels.
Explicit Telegram rate-limit rejections can be retried after retry_after.

Expose constituent candles on SignalMatch. If two- and three-candle engulfing
both match, preserve the existing single signal and retain the three-candle
span for manual-area intersection. Existing filters/metrics remain unchanged.

## Consequences

Two independently supervised processes share local persistent state. Backups
must use SQLite's backup API (or stop both processes); plain copying a live WAL
database is unsafe. Database failure must not suppress market signals.
One token must have only one polling consumer; the local lock complements
Telegram conflict detection but cannot coordinate separate hosts.

## Alternatives considered

- Poll on each scheduled scan: commands would wait outside trading hours.
- Merge polling and scheduling: unnecessarily changes the scanner lifecycle.
- Retry every send: creates duplicate replies after ambiguous timeouts.

## Related tasks

- [Task 007](../../tasks/done/task-007.md)
