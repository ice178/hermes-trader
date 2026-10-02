# Task: Manage manual price levels and zones through Telegram

## Status

Done

Owner: Tomasso / Codex

Updated: 2026-10-02

## Context

The live Telegram bot currently performs a scheduled, one-way scan: it detects
price-action patterns and sends notifications. It does not read Telegram
updates, process commands, or persist user-managed state.

The repository already has a `Level` model and level-aware signal evaluation
for calculated liquidity levels. The live bot intentionally detects patterns
without levels, however, and the new manually entered levels have a different
lifecycle: an operator creates, lists, and removes them through Telegram, and
they persist across bot runs and deployments.

The operator wants to know when an otherwise valid pattern occurs at a manually
marked price level or intersects a marked price zone such as an imbalance.
Manual price areas are contextual metadata for a signal; they must not become
an additional requirement for sending the signal.

## Problem

There is no way to:

- submit an exchange, ticker, direction, source timeframe, and one or more price
  levels to the bot;
- submit a price zone, for example an imbalance bounded by two prices;
- persist active and logically deleted levels/zones;
- list all active levels/zones or those for one ticker;
- logically delete a level or zone through Telegram;
- associate a detected pattern with an active manual point level or zone;
- receive and safely process Telegram user input.

## Goal

Add a small Telegram command interface and SQLite-backed manual price-area
store. An authorized operator can add, list, and remove point levels and price
zones. During every live signal scan, the bot loads active price areas for the
signal's exchange and ticker and marks the notification when the complete
pattern intersects one or more compatible areas.

Example operator flow (final command names and exact grammar may be refined
before implementation):

```text
/levels_add BTC/USDT bingx buy 4h level 65000 65500 66000 | Weekly support
/levels_add BTC/USDT bingx sell 1d day_high 67000 | Previous day high
/zone_add ETH/USDT bingx buy 1h imbalance 3150 3200 | Bullish imbalance
/levels
/levels BTC/USDT
/level_delete BTC/USDT bingx 65000
/zone_delete ETH/USDT bingx 3150 3200
```

The separator and exact grammar are illustrative, but the production grammar
must remain unambiguous when a free-form comment follows several prices.

Example responses:

```text
Added 3 levels: BTC/USDT, bingx, buy, source 4h
#42 65000 level — Weekly support
#43 65500 level — Weekly support
#44 66000 level — Weekly support

BTC/USDT
#42 bingx buy 65000 level [source: 4h]
#45 bingx sell 67000 day_high [source: 1d]
#46 bingx buy 3150–3200 imbalance [source: 1h]
```

When a pattern touches an active level, its existing notification receives an
additional section such as:

```text
Level: #42 65000, buy, level (source: 4h)
```

If multiple active levels or zones match, list all of them in deterministic
price/ID order. If no price area matches, preserve the current notification
behavior.

## Functional requirements

### Commands and authorization

- Read Telegram updates and react to supported bot commands.
- Authorize command senders by Telegram user ID inside the bot. Keep an explicit
  configured allowlist (proposed `TELEGRAM_ALLOWED_USER_IDS`) and reject or
  ignore every other sender. `TELEGRAM_CHAT_ID` remains the notification
  destination and is not sufficient authorization in a group chat.
- Support `/help` with syntax, supported exchanges, directions, timeframes,
  price-area kinds, and comment syntax.
- Support adding multiple point levels in one command. The command supplies one
  ticker, exchange, `buy`/`sell` direction, source timeframe, kind, one or more
  positive prices, and an optional comment shared by the created records.
- Create a multi-level command atomically: invalid input creates none of its
  levels. Existing duplicates may be skipped and reported without preventing
  the new unique levels from being created.
- Support adding one price zone using lower and upper bounds plus the same
  exchange, ticker, direction, source timeframe, kind, and optional comment.
- Support listing active point levels and zones across all tickers and for one
  ticker. Include stable ID, exchange, side, bounds, kind, source timeframe, and
  comment when present.
- Support deleting a point level by exchange, ticker, and exact price; support
  deleting a zone by exchange, ticker, and exact bounds. Deletion is logical:
  mark matching records `deleted`, set `deleted_at`, and retain them for future
  history. The delete command does not require side, kind, or source timeframe.
  If several active records match the market and exact price/bounds, delete all
  of them and make the count and full affected-record list prominent in the
  response.
- Return a clear confirmation or validation error for every authorized command.
- Treat Telegram updates idempotently so a restart cannot execute the same
  command twice. Persist the last processed update ID or use an equivalent
  durable mechanism.
- Define behavior for Telegram command suffixes (for example
  `/levels@hermes_bot`) and surrounding whitespace.

### Symbol and input validation

- Normalize symbols to the same canonical format used by the scanner, currently
  `BASE/QUOTE` in uppercase (for example `BTC/USDT`).
- Normalize and validate the exchange identifier. Reject an unsupported
  exchange/symbol pair rather than saving an entry that can never match a scan.
  The configured scanner universe should be the source of truth instead of a
  second hard-coded list.
- Parse prices without locale-dependent separators, require a finite positive
  value, and preserve enough precision for the exchange symbol.
- Require `buy` or `sell` on every level/zone. Internally map these values to the
  signal directions `long` and `short` without relying on the display label.
- Require and store the timeframe on which the operator identified the area.
  This `source_timeframe` is metadata: the area remains eligible for matching
  signals on every scanned timeframe.
- Accept and normalize this initial standard source-timeframe set independently
  from the current scanner configuration:
  `1m`, `3m`, `5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `6h`, `8h`, `12h`, `1d`,
  `3d`, `1w`, and `1M`. Treat obvious case aliases consistently while
  preserving the distinction between minute `m` and month `M`.
- Initially support these user-facing level kinds:
  - `day_high` — daily high;
  - `day_low` — daily low;
  - `level` — ordinary/manual level;
  - `mirror` — mirror level.
- Support at least `imbalance` as a zone kind. Point-level and zone kind
  vocabularies may overlap, but shape (`point` or `zone`) must be stored
  separately from semantic kind.
- Accept an optional free-form comment of at most 500 Unicode characters and
  safely escape it in Telegram HTML messages.
- Store kinds as stable machine-readable values and display friendly labels in
  responses. Adding new kinds later should not require a schema rewrite.

### Level-to-signal association

- Continue detecting and filtering signals exactly as today. A missing level
  must never suppress an otherwise valid notification.
- After a signal is accepted, query active manual price areas for its normalized
  exchange and symbol.
- Determine the full set of candles that constitutes the detected pattern. The
  pattern price interval is inclusive and includes wicks:

  ```text
  pattern_low  = min(candle.low for candle in pattern_candles)
  pattern_high = max(candle.high for candle in pattern_candles)
  ```

- A point level intersects when
  `pattern_low <= level_price <= pattern_high`.
- A price zone intersects when its inclusive interval overlaps the inclusive
  pattern interval: `pattern_high >= zone_low` and
  `pattern_low <= zone_high`.
- Only attach `buy` levels/zones to `long` signals and `sell` levels/zones to
  `short` signals.
- For the first version, a price area remains active after a match. Only an
  explicit delete action changes its status.
- A matched point level adds its ID, price, direction, kind, source timeframe,
  and optional comment to the Telegram message. A zone adds both bounds and the
  same metadata.
- The same active level may be reported by signals on different timeframes.
- Do not modify the existing automatic liquidity-level lifecycle unless an
  explicit design decision later unifies it with manual levels.
- If the level database is temporarily unavailable, report/log the failure but
  do not discard an already detected market signal. Define an operationally
  visible fallback for the notification path.

The match must use the actual constituent candles, not an approximation based
only on the final candle. The signal domain therefore needs to expose pattern
span/constituent-candle information for pin bars, railway tracks, inside bars,
and both two- and three-candle engulfing variants.

## Data model and persistence

Use SQLite for the first version. Model a point level as a price interval whose
lower and upper bounds are equal, so zones do not require an unrelated storage
system. Keep database access behind a repository or store interface so command
parsing, signal matching, and persistence can be tested independently.

Minimum `manual_price_areas` fields:

| Field | Purpose |
|---|---|
| `id` | Stable integer identifier used by list/remove commands |
| `exchange` | Canonical exchange identifier, for example `bingx` |
| `symbol` | Canonical scanner symbol, for example `BTC/USDT` |
| `shape` | `point` or `zone` |
| `lower_price` | Point price or inclusive zone lower bound |
| `upper_price` | Same as lower for a point; inclusive zone upper bound |
| `side` | `buy` or `sell` |
| `kind` | Stable semantic label such as `level` or `imbalance` |
| `source_timeframe` | Timeframe on which the operator marked the area |
| `comment` | Optional bounded operator note |
| `status` | `active` or `deleted` |
| `created_at` | UTC creation timestamp |
| `updated_at` | UTC last-change timestamp |
| `deleted_at` | UTC logical-deletion timestamp, nullable |

Also persist Telegram update-processing state (for example a single
`last_update_id`) so polling is restart-safe. Schema creation and future schema
changes must be explicit and repeatable; do not rely on an unversioned table
shape hidden inside application startup.

The database path must be configurable (proposed `LEVELS_DB_PATH`). Production
data must live outside the Git checkout, for example under
`/var/lib/hermes-trading/`, with ownership and permissions suitable for the
non-root runtime user. Deployments must not overwrite or delete it. Tests must
use a temporary database.

Recommended database constraints and indexes:

- check that both bounds are positive and `lower_price <= upper_price`;
- check that point bounds are equal and zone bounds form a non-empty interval;
- check that side, shape, and status are supported values;
- index active lookups by normalized `(exchange, symbol, side, status)`;
- prevent duplicate active areas with the same normalized exchange, symbol,
  side, shape, bounds, kind, and source timeframe. Areas at the same price but
  with different source timeframes are distinct. A different comment alone
  does not make a distinct area.
- allow the same natural key to be inserted again after its previous record was
  deleted; create a new row and new stable ID rather than reactivating or
  overwriting the old record.

Keep stable area IDs and soft-deleted rows because a later task should be able
to persist a separate event/history model connecting:

```text
manual price area → detected pattern → optional trade entry → trade outcome
```

That future history should use separate event/trade records rather than turning
the area's lifecycle status into a trade-result field.

## Runtime design constraints

The current systemd service is a scheduled oneshot scanner, so it cannot offer
responsive command handling by itself. Add a separate long-running Telegram
command-listener service using `getUpdates` long polling, while the existing
scheduled scanner remains responsible for outgoing signal notifications. Work
out its exact process lifecycle, retry/backoff, shutdown, update-offset, and
deployment behavior in an implementation plan before coding.

The command listener must run continuously and restart safely. Only one process
may consume `getUpdates` for a bot token. Webhook hosting is out of scope for
the first version.

Do not add a large Telegram framework unless its lifecycle and dependency cost
are justified. The existing `TelegramClient` can be extended with the minimal
Bot API methods if that remains clear and testable.

Concurrent access from the command listener and scheduled scanner must use
short transactions, connection timeouts, and SQLite WAL/busy handling as
appropriate. A partially handled command must not leave the update cursor ahead
of the database mutation it requested.

## Non-goals

- Automatically discovering or importing technical levels from market data.
- Editing a level in place; remove and re-add is sufficient initially.
- Automatically deleting a level after it is touched or crossed.
- Using levels to filter out pattern notifications.
- Adding per-user portfolios, roles, or multi-tenant chat support.
- Building Telegram inline keyboards or a conversational wizard.
- Adding a web UI or external database server.
- Applying manual levels to historical backtests in the first version.
- Reworking the existing automatic `LiquidityLevels` algorithm.
- Executing trading orders from Telegram commands.
- Persisting pattern-at-level events, trade entries, or trade outcomes in the
  first version. Preserve stable IDs and rows so that history can be added
  without redesigning price-area identity.

## Pre-implementation findings

- `src/signals_bot.py` detects live patterns without requiring levels and
  formats one Telegram message per accepted signal.
- `src/hermes_trading/telegram.py` only supports `sendMessage`; it has no update
  polling or command parser.
- `PriceActionSignal.evaluate_without_levels()` and the current signal-filter
  path should remain the source of pattern detection for this feature.
- `src/hermes_trading/liquidity.py` has an in-memory `Level` dataclass for
  calculated high/low liquidity levels. Its `type`, timestamps, confirmation,
  weight, and pruning semantics do not directly represent the requested manual
  level kinds and database lifecycle.
- A separate persisted manual price-area domain model is safer initially.
  Shared concepts can be unified later only if their semantics are explicit.
- The final pattern candle is available as `SignalMatch.candle`; multi-candle
  pattern bounds and constituent candles are not currently represented on
  `SignalMatch`, so the signal result contract must be extended without breaking
  existing filtering/backtest consumers.
- `Candle` identifies a symbol/timeframe but not its exchange. The live scan
  must carry exchange identity into level matching so same-symbol levels from
  different exchanges cannot be mixed.

## Confirmed decisions

- A point level matches when the inclusive high/low envelope of every candle in
  the pattern crosses the price. Candle wicks are included.
- A zone matches when that full inclusive pattern envelope intersects the zone.
- Every price area has a required `buy` or `sell` side, matched to long or short
  signals respectively.
- A match does not delete the price area. Lifecycle changes are manual for now.
- The source timeframe is required metadata, but the area applies to signals on
  all timeframes.
- Commands are authorized by configured Telegram user IDs in the bot.
- One command can add several point prices with shared metadata.
- Duplicate active areas are not created. Kind and source timeframe are part of
  duplicate identity; comment is not.
- Re-adding an area after deletion creates a new record with a new ID.
- A free-form comment is supported.
- Point deletion is available by exchange, ticker, and price and is a soft
  delete (`deleted` plus timestamp), not a physical row deletion. Direction is
  not required by the delete command; every exact active match is deleted and
  multiple affected records are highlighted in the response.
- The only first-version statuses are `active` and `deleted`.
- The standard source-timeframe set is accepted even when the scanner does not
  currently scan a submitted timeframe.
- The Telegram authorization configuration supports a list of user IDs.
- Commands are processed continuously by a dedicated runtime, whose operational
  details require a separate implementation design step.
- Price zones such as imbalances are included in the first implementation and
  are not encoded as an arbitrary collection of point levels.
- Pattern/trade/outcome history is a desired later extension, not part of the
  first implementation.

## First-version defaults

- `/levels` and `/levels <symbol>` show active records only. Deleted-history
  commands can be added later without changing soft-delete storage.
- Split a long listing across ordered Telegram messages at a transport-safe
  boundary. Repeat enough exchange/symbol context in each part and never split
  one record across messages.
- Limit comments to 500 Unicode characters.
- Exact point/zone intersection is used; no percentage, ATR, or tick tolerance
  is added beyond inclusive bounds.

## Acceptance criteria

- [x] An authorized operator can add several valid point levels with shared
  exchange, symbol, side, source timeframe, kind, and optional comment through
  one documented Telegram command and receives their stable IDs.
- [x] An authorized operator can add a valid price zone with inclusive bounds
  and receives its stable ID.
- [x] Invalid exchange/symbol pair, side, timeframe, price/bounds, kind, comment,
  argument count, and unknown commands return useful errors without partially
  changing the database.
- [x] Commands from Telegram user IDs outside the allowlist cannot read or
  mutate price areas.
- [x] `/levels` returns all active points and zones grouped by exchange/ticker in
  deterministic order; `/levels <symbol>` returns only that ticker's active
  records while preserving exchange identity.
- [x] Point deletion by exchange/ticker/price and zone deletion by
  exchange/ticker/bounds marks every exact active match `deleted`, confirms and
  highlights all affected records when there is more than one, and handles
  missing/already-deleted records safely. Side is not required for deletion.
- [x] Levels and Telegram update state survive process restarts and application
  deployments.
- [x] Re-delivery of the same Telegram update does not create, remove, or reply
  to a command twice.
- [x] A valid live signal is still sent when no manual price area exists.
- [x] A valid live signal whose complete wick-inclusive pattern envelope crosses
  a compatible point includes every matching active level's full metadata.
- [x] A valid live signal whose complete wick-inclusive pattern envelope
  overlaps a compatible zone includes every matching active zone and both
  bounds.
- [x] Areas with the opposite side, another exchange/symbol, or a non-active
  status are never attached to the signal.
- [x] Area source timeframe is displayed but does not restrict which signal
  timeframes can match it.
- [x] A price-area match annotates the signal but does not alter signal
  detection, metric filtering, deduplication, or the area's active status.
- [x] Pin bar, railway tracks, inside bar, and two-/three-candle engulfing
  matching all use their actual constituent candles, including wicks.
- [x] Repeating an add command does not create duplicate active areas; a mixed
  batch reports duplicates and creates each new unique point once.
- [x] Same-price areas with different source timeframes are stored as distinct
  records, while changing only the comment does not bypass duplicate checks.
- [x] Re-adding a previously deleted area creates a new record and new stable ID
  without overwriting or reactivating the deleted row.
- [x] A database read failure does not silently suppress an already accepted
  signal and is visible in logs or message fallback behavior.
- [x] The command listener has a documented production lifecycle, restarts
  safely, and does not conflict with another `getUpdates` consumer.
- [x] The production database path, directory ownership, backup expectation,
  and deployment preservation behavior are documented.
- [x] Existing tests continue to pass.

## Implementation notes

Implemented areas of change:

```text
src/hermes_trading/telegram.py          # receive updates / Bot API transport
src/hermes_trading/manual_levels.py     # point/zone domain and matching rules
src/hermes_trading/level_store.py       # SQLite persistence
src/hermes_trading/telegram_commands.py # parsing, authorization, responses
src/signals_bot.py                      # notification enrichment
src/levels_bot.py                       # optional long-running command entrypoint
deploy/systemd/                         # listener service and persistent path
docs/server-deployment.md               # configuration and operations
tests/                                  # unit and integration coverage
```

Keep Telegram transport, command parsing, authorization, SQLite operations, and
signal-level matching separate. Pass dependencies explicitly so tests do not
make network requests or use the production database.

Do not interpolate SQL strings from commands. Use parameterized statements and
bounded Telegram request timeouts. Avoid including the bot token or full
incoming updates in logs.

If a schema migration tool is introduced, justify it against the small schema.
A lightweight numbered migration mechanism is acceptable, but it must be
testable and safe on an existing database.

## Test plan

### Unit tests

- Parse each supported command, optional bot-name suffix, whitespace, and bad
  argument combinations.
- Normalize exchanges/symbols and validate scanner markets, side, source
  timeframe, point/zone bounds, kinds, and comments.
- Verify authorization before command execution.
- Verify point matching at exact pattern boundaries and verify zone overlap,
  containment, disjoint ranges, and wick-only intersection.
- Cover every pattern length and ensure all constituent candles participate.
- Verify side, exchange, symbol, and status filtering with multiple areas.
- Verify notification formatting with zero, one, and multiple matching points
  and zones, including safe comment escaping.

### SQLite integration tests

- Create/migrate a fresh temporary database.
- Add point batches and zones, list by market, list all, and soft-delete them by
  market and exact price/bounds.
- Verify constraints, deterministic ordering, duplicate behavior, persistence
  after reconnect, and concurrent reader/writer behavior relevant to the two
  bot processes.
- Verify Telegram update cursor and level mutation behave atomically enough to
  prevent duplicate command effects after simulated restart/failure.

### Bot integration tests

- Feed fake Telegram updates through the command handler and assert replies and
  database state without network access.
- Run the signal-notification path against a temporary database and fake
  Telegram client, asserting both unchanged messages and level annotations.
- Verify unauthorized updates, Telegram API errors, SQLite busy/unavailable
  errors, and graceful restart behavior.
- Verify any new systemd unit and environment configuration through deployment
  configuration tests.

### Regression

Run focused tests while iterating, then the complete suite:

```bash
python3 -m pytest tests/test_telegram.py tests/test_signals_bot.py
python3 -m pytest
```

## Agent instructions

Before implementation:

1. write an implementation plan because this change spans persistence,
   Telegram input, live signal formatting, and production runtime;
2. inspect the real systemd deployment configuration and decide how the
   long-running listener coexists with the scheduled scanner;
3. confirm the manual point/zone model will not accidentally change the
   existing automatic liquidity-level semantics;
4. update `.env.example` and deployment documentation without committing a real
   database or credentials.

Prefer a vertical first increment: SQLite store plus command parser and tests,
then polling runtime, then signal enrichment and deployment changes.

## Review notes

Implemented the full task, including signals, and verified locally. Production
activation is documented but has not been performed.

- Added `manual_levels.py`, `level_store.py`, `telegram_commands.py`,
  `levels_listener.py`, `scanner_config.py`, and `src/levels_bot.py`.
- Extended Telegram transport and SignalMatch constituent candles; integrated
  area annotations into the live scanner without changing its signal filters.
- Added the listener systemd unit, shared persistent directory, and deployment
  stop/restart handling. Updated env example, ignore rules, README, and server docs.
- Added [operator instructions](../../docs/manual-levels.md) and
  [ADR-001](../../docs/adr/adr-001-manual-price-areas.md).
- Added command/store, listener/transport, signal integration, and deployment
  tests. Deployment tests execute a redirected script with simulated commands,
  covering enabled/disabled listeners and failures during validation/restart.

Validation:

- Baseline `python3 -m pytest -q`: 116 passed.
- Focused command/pattern, listener/transport, and deployment tests passed.
- Final `python3 -m pytest -q`: 208 passed.
- `bash -n deploy/update-server.sh`, Python compileall for new runtime modules,
  and `git diff --check` passed.
- No live Telegram/exchange requests, production changes, or dependency installs.
- Native `systemd-analyze` is unavailable on this macOS host; Linux unit
  verification and live restart/command checks remain deployment steps.

The checklist is satisfied by implementation, local tests, and documentation;
production installation is not claimed. Ambiguous reply delivery can lose a
confirmation while retaining the committed command, as documented below.

## Implementation plan

1. Share the live scanner's market universe with command validation. Introduce
   a separate manual-area model with exact decimal prices; leave automatic
   liquidity semantics unchanged.
2. Add a versioned SQLite store with WAL, bounded busy waits, active-area unique
   constraints, soft deletion, and transactional update deduplication/outbox.
3. Add authorized command parsing, deterministic bounded replies, and Bot API
   polling with explicit destination chats, sanitized failures, and timeouts.
4. Run one foreground listener under systemd, with a local exclusive lock,
   interruptible backoff and SIGTERM handling. Keep the scanner's timer.
5. Expose actual constituent candles on SignalMatch, retaining one match per
   pattern/direction; use the longest detected engulfing span when both match.
   Enrich accepted notifications with all compatible active areas. On database
   failure send the original signal with a visible unavailable marker.
6. Add the listener unit and persistent state directory, preserve the database
   on update, and restart an already enabled listener after deployment. Document
   first installation, backup, shutdown, and rollback.
7. Test commands, authorization, precision, duplicates, atomic restart behavior,
   transport errors/backoff, signal spans/intersections, and deployment order;
   then run the full pytest suite. No live messages or deployment during tests.

Acceptance is the full checklist above. Production installation and a live
command smoke test remain an operator step after local verification.

Delivery limitation: SQLite mutations and update receipt are atomic; Telegram
sendMessage cannot participate in that transaction. Persist reply attempts
before network delivery to avoid duplicate replies after ambiguous timeouts or
crashes. A reply can be lost in that window; /levels recovers the current state.
This replaces an impossible exactly-once network-delivery guarantee with
exactly-once local effects and at-most-once ambiguous send attempts.

Risks: concurrent pollers (local lock and fatal Telegram conflict), database
contention (short transactions/WAL), and interrupted sends (durable attempt
state and visible logs). Rollback: stop/disable the listener, unset LEVELS_DB_PATH
for the scanner, retain the database and restore the prior application version.

## Handoff

Deployment readiness rechecked on 2026-10-02 with Tasks 008/009 present:
`python3 -m pytest -q` passed (254 tests), `bash -n deploy/update-server.sh`,
`git diff --check`, and `python3 src/scan_signals.py --help` passed.
The release changes remain uncommitted locally. Server access and the command
user allowlist are still needed to inspect production and activate the listener.
No production state was inspected or changed during this readiness check.

Implementation complete and locally verified. Next operator action: configure
`LEVELS_DB_PATH` and `TELEGRAM_ALLOWED_USER_IDS` in the existing server env file,
install/verify the units, enable the listener, and exercise /help, add, /levels,
restart, and delete according to `docs/manual-levels.md`. Use only one poller
per token. Preserve and back up SQLite outside the checkout. No live rollout,
commit, or push was performed during this task.
