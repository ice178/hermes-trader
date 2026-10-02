# Task: Test current manual levels with Barcelona-local historical scans

## Status

Done

Owner: Tomasso / Codex

Updated: 2026-09-25

## Context and goal

The user wants to test whether an added level matches patterns in a manual scan
and prefers entering times in Barcelona local time. Task 008 defaulted to UTC
and did not apply manual levels to historical signals.

Add explicit --check-levels using the active records from LEVELS_DB_PATH at scan
start. Label this as testing current levels against historical candles, without
claiming the levels existed at the historical signal time. Make Europe/Madrid
the default timezone for manual input; retain explicit offsets and --timezone UTC.

## Non-goals

- No production schedule changes or exchange/Telegram calls during development.
- No historical level-state reconstruction, trading, or automatic area deletion.
- Do not alter date interpretation in the separate backtest runner.

## Acceptance criteria

- [x] Manual naive dates/times default to Europe/Madrid; --timezone can override.
- [x] Explicit ISO offsets and Z are honored; date-only end includes the full
  local day, including 23/25-hour DST days.
- [x] Missing or ambiguous local DST times require an explicit offset.
- [x] --check-levels requires an existing compatible LEVELS_DB_PATH and reads
  matching-market active areas before network calls; it never creates a database.
- [x] Terminal output lists tested areas, per-pattern matches/no match, and a
  summary count, using the existing side/symbol/exchange/full-pattern matcher.
- [x] Optional Telegram messages include the same matches and clearly identify
  the current-level test; splitting and HTML escaping preserve all annotations.
- [x] Checking areas does not filter out patterns or mutate area/update state.
- [x] Tests cover timezones/DST, exact level/zone matches, nonmatches, failed
  database reads and opt-in delivery. Full regression suite passes.
- [x] README and operator guide contain a copyable local test command.

## Implementation plan

1. Parse manual dates with ZoneInfo and round-trip validation for DST gaps/folds.
2. Add --timezone and --check-levels; read active areas into a scan-start snapshot.
3. Reuse matching_areas and factor annotation message formatting from the live
   sender so both paths share safe HTML/chunk handling.
4. Add offline integration tests, update docs, run pytest and CLI --help.

## Risks and test plan

The test uses today's active areas, so it is an operational check, not a
historical backtest of the operator's level choices. Unavailable history remains
reported by the manual scanner. Use fake candles/clients and temporary SQLite;
verify unchanged records after a test. Exercise both DST transitions and the
existing live notification regression tests. Run python3 -m pytest.

## Review and validation

Changed the manual date parser in `historical_signals.py`, CLI in
`src/scan_signals.py`, and shared annotation formatting in `src/signals_bot.py`.
Added timezone/DST, area snapshot, nonmutation, database failure and Telegram
annotation tests in `tests/test_historical_signals.py`. Updated README and
`docs/manual-levels.md` with local test commands and matching semantics.

- Focused historical/live notification tests: 68 passed.
- Final `python3 -m pytest -q`: 254 passed.
- `python3 src/scan_signals.py --help` and `git diff --check`: passed.
- No live exchange/Telegram requests or production configuration changes.

## Handoff

Done locally. Load the same environment as the listener and run
`python3 src/scan_signals.py` with date bounds and `--check-levels`.
Naive times now default to Europe/Madrid; `--timezone UTC` restores UTC input.
The test reads current active areas and never changes them. Historical area
state is not reconstructed. Earlier Task 007/008 changes remain in the worktree;
no commit, push, or deployment was performed.
