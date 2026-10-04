---
name: handoff
description: End-of-session handoff for TURN-Mapper. Writes the SESSION_LOG entry, updates commands and decisions, and commits docs. Use when the user says to wrap up, stop, hand off, or end the session.
disable-model-invocation: true
---

# Session handoff

1. Run `git status` and `git log --oneline -10` to see what actually changed this session.
2. Run `pytest -q` and `ruff check .` and capture the real output.
3. Prepend an entry to `docs/SESSION_LOG.md` (newest on top) using its template:
   - Goal, Changed (files/modules), **Verified** (exact commands + real results — paste numbers, not expectations), Not verified / unknown, Broken or risky, Decisions / ADRs proposed, **one** Next step.
4. If a command became real, update the "Commands" section of `CLAUDE.md`.
5. If a decision was made, add/update the ADR in `docs/DECISIONS.md` (Proposed unless the human accepted it).
6. If the current step in `docs/MASTER_PLAN.md` is done, mark it done with the date.
7. Commit docs on the current branch: `docs: session handoff <date>`.
8. Show the user the new log entry.
