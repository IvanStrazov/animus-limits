# Changelog

## 0.2.2 — 2026-11-17
- Skill: Russian trigger phrases; no longer shares "where did my tokens go" with the built-in usage skill — this one is per task, across sessions.

## 0.2.1 — 2026-11-17
- `set` says when it replaces an existing limit (one limit per key).
- A `%` limit line now reads "N% of all your spend; this key is M% of it".
- Skill: a key that is also a project name counts the whole project; no hooks or settings changes unless asked. Same inside-a-journal rule as animus-journal.

## 0.2.0 — 2026-11-17
- `report` shows token totals and output tokens next to $ (overall and per row).
- `check --at P` warns from P% instead of 80%.
- A limit with nothing attributed says so and explains how spend reaches a task (a journal entry with that first tag).

## 0.1.2 — 2026-11-17
- Skill: when a task is already most of the spend, say a % limit would be OVER from day one and ask about `$`; never switch the limit type or value on your own.
- Skill: Windows interpreter from ecosystem.json.

## 0.1.1 — 2026-11-17
- Skill: a `%` limit is a share of your own spend, not of the plan limit — use `$` for a budget; there is no background warning.
- Skill: how sessions map to journal tasks (entry during the session or ≤ 30 min after); `estimate` looks back 60 days.

## 0.1.0 — 2026-11-17
- First release, part of the Animus ecosystem.
