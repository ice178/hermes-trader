# Architecture Decision Records

Architecture Decision Records (ADRs) capture decisions that have a lasting effect on the structure, interfaces, dependencies, data handling, or operation of Hermes Trading. Use a task file for routine implementation choices; create an ADR when future contributors will need to know why an architectural choice was made.

## Creating an ADR

1. Copy `adr-template.md` to the next available number, for example `adr-001-signal-interface.md`.
2. Keep it concise and set the status to `Proposed` while discussion is open.
3. Change the status to `Accepted` when the decision is adopted.
4. Do not rewrite accepted history. If a decision changes, add a new ADR, mark the old one `Superseded`, and cross-link both records.
5. Link related task files and link the ADR from those tasks.

ADR numbers are sequential and never reused. Git history records authorship and dates, so add extra metadata only when it is useful.
