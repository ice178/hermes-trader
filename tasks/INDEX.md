# Task Index

Every meaningful task should be linked from this file. Name task files `task-NNN.md`, assigning the next unused three-digit number (`task-001.md`, `task-002.md`, and so on). Add a row when creating a task, update it when status or ownership changes, and fix the relative link when moving the file. Use `YYYY-MM-DD` for dates and `Unassigned` when there is no owner.

## Active

| Task | Status | Owner | Updated | Notes |
|---|---|---|---|---|

## Backlog

| Task | Status | Owner | Updated | Notes |
|---|---|---|---|---|
| [Task 004: Deploy production bot from GitHub Actions](backlog/task-004.md) | Backlog | Tomasso / Codex | 2026-08-03 | Manual Run workflow button with restricted SSH deployment |

## Done

| Task | Status | Owner | Updated | Notes |
|---|---|---|---|---|
| [Task 001: Prepare the Telegram signal bot for server deployment](done/task-001.md) | Done | Tomasso / Codex | 2026-08-02 | Deployed on Ubuntu with systemd service and timer |
| [Task 002: Process only newly closed candles](done/task-002.md) | Done | Tomasso / Codex | 2026-08-02 | Stateless fresh-close processing deployed; no sent-signal cache |
| [Task 003: Add Madrid trading hours and signal context to notifications](done/task-003.md) | Done | Tomasso / Codex | 2026-08-03 | Released on Ubuntu with optional metric filter and candle close time |
| [Task 005: Simplify Telegram signal notifications](done/task-005.md) | Done | Tomasso / Codex | 2026-08-05 | Compact per-signal messages with conditional positive metric context |
| [Task 006: Add a manual server update script](done/task-006.md) | Done | Tomasso / Codex | 2026-08-05 | One-command safe update from origin/main on the production server |
