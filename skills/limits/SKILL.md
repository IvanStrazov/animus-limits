---
name: limits
description: Token spend per task and per-task limits for Claude Code — where the plan limit went (by journal task, project, day, model), limits like "invest-bot ≤ 30% of my week", and a cost estimate before a big task. Use on /limits, "where did my tokens go", "how much did X cost", "set a limit", or before starting a task the user says is big or expensive.
---

# Limits

All numbers come from one script: `L` = `python3 "<plugin root>/scripts/limits.py"`, where the plugin root is two levels above this skill's base directory. Use `python` if `python3` is missing (Windows). The script reads transcripts itself; never read transcripts or journals yourself for this.

Unit: API-equivalent USD with prompt caching — a proxy for how fast plan limits drain, not a bill. Say so once when you first show numbers.

## Where it went
`L report` (last 7 days by journal task) · `--by project|day|model` · `--days N` · `--top N`.
Tasks come from animus-journal entries (the first tag of the entry written after the work). "(no journal) X" is work in project X that never got a journal entry.
Show the table as is, then one or two lines of takeaways (the biggest item, anything surprising). No long commentary.

## Limits
`L set <task-or-project> 30%` (share of your total spend) or `L set <key> '$40'` (fixed), window `--days N` (default 7). `L unset <key>`.
`L check` prints only limits at ≥ 80% (`--verbose` for all). Run it whenever this skill is used, and mention any line it prints.

## Before an expensive task
When the user starts something big, or asks what it will cost: `L estimate <task words>` — median/max of past sessions of that task, model mix, share of a week.
Then give one concrete suggestion only if it would save a lot: e.g. use Sonnet for mechanical steps, lower effort, split the task, or run it after the limit resets. Do not lecture; the user decides.
