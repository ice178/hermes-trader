# Tasks

This folder is the shared, local record of meaningful development work. It gives a human or terminal-based AI agent enough context to discover, investigate, plan, implement, review, test, and hand work off without requiring a separate tracker.

## When to create a task

Create a task file for work that spans multiple files or sessions, needs investigation or review, changes behavior, or benefits from explicit acceptance criteria. Small typo fixes and routine one-line maintenance do not need one.

Copy `templates/task.md` into the appropriate state folder and name it `task-NNN.md`, using the next available three-digit number. Start with `task-001.md`; never reuse a number, including after a task moves to `done/`. Keep the human-readable task name in the file heading and `INDEX.md`. Add a relative link to `INDEX.md` immediately.

Use the supporting templates when they add value:

- `investigation.md` for uncertain behavior or solution discovery;
- `implementation-plan.md` before a broad or risky change;
- `review.md` when reviewing a substantial or agent-generated diff;
- `handoff.md` when work will continue in another session or with another person.

These may be standalone files or sections copied into the main task. Prefer one useful task file over a collection of mostly empty documents.

## Workflow

1. Put understood but unstarted work in `backlog/` with status `Backlog`.
2. Move a task to `active/` when investigation or implementation begins and set its status to `Active`, `Blocked`, or `Review` as appropriate.
3. Keep context, decisions, acceptance criteria, test results, and the next step current after meaningful progress.
4. Move completed and verified work to `done/`, set its status to `Done`, and update its link and row in `INDEX.md`.

Moving means changing the file location with `git mv` when it is tracked. There is no automation: the task file and `INDEX.md` are the source of truth.

## Guidance for AI agents

Before coding, read the repository `README.md`, `AGENTS.md`, `INDEX.md`, and the relevant task. Confirm that the problem, non-goals, acceptance criteria, and test plan are specific enough. For broad or ambiguous work, investigate and propose a plan before implementation.

During work, make focused changes and update the task when understanding, scope, status, risks, or test evidence changes. Before handing off, record what changed, commands and tests run, failures or untested areas, and the next recommended action. Do not mark a task done until its acceptance criteria are satisfied or explicitly waived.

## What belongs here

Store durable working context: the problem, intended outcome, constraints, discoveries, decisions, risks, acceptance criteria, review notes, test evidence, and handoff state.

Do not store secrets, API keys, personal data, raw logs, generated backtest output, large data, full command transcripts, or documentation that belongs in `README.md` or `docs/`. Put durable architectural decisions in `docs/adr/` and link them from the task.

Keep this lightweight. Update facts that help the next decision; do not maintain diaries, duplicate Git history, or fill every optional section when it has no value.
