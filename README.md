# animus-limits

[![tests](https://github.com/IvanStrazov/animus-limits/actions/workflows/test.yml/badge.svg)](https://github.com/IvanStrazov/animus-limits/actions/workflows/test.yml)
[![version](https://img.shields.io/badge/version-0.1.0-blue)](CHANGELOG.md)
[![license: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
![dependencies: none](https://img.shields.io/badge/dependencies-none-brightgreen)
![python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)

**Where did my plan limit go? Spend per task, limits per task, and an estimate before the next big one.**

> **Part of Animus** — small, local, token-frugal plugins that let Claude Code remember you and your work. Each works alone; together they share context through `~/.claude/ecosystem.json`.
>
> | Plugin | What it does |
> |---|---|
> | [animus-journal](https://github.com/IvanStrazov/animus-journal) | Project journal on a hard token budget: what was done, decided, next |
> | [animus-portrait](https://github.com/IvanStrazov/animus-portrait) | A compact portrait of you, built from your own sessions |
> | [animus-brief](https://github.com/IvanStrazov/animus-brief) | One status brief across all your projects |
> | [animus-limits](https://github.com/IvanStrazov/animus-limits) | Token spend per task, per-task limits, cost estimates |
> | [animus-relay](https://github.com/IvanStrazov/animus-relay) | Hand work over to a fresh session without losing the thread |
> | [animus-review](https://github.com/IvanStrazov/animus-review) | Send work to another model for review, triage the answer |
>
> The name nods to the memory machine from Assassin's Creed and to the Latin *animus*, "mind". Not affiliated with Ubisoft.

## Install

```
/plugin marketplace add IvanStrazov/animus-limits
/plugin install animus-limits@animus-limits
```

Then say `/limits`. Requires Python 3.9+ on `PATH` (`python3` or `python`); works on macOS, Linux and Windows (Git Bash).

## What you get

- **Spend by task** — `/limits` or "where did my tokens go": a table by [animus-journal](https://github.com/IvanStrazov/animus-journal) task (the first tag of the entry written after the work), or by project, day, model.
- **Limits** — "invest-bot ≤ 30% of my week" or "≤ $40 a week"; `check` warns at 80%.
- **Estimate** — before a big task: median and max cost of past sessions of that task, model mix, share of a week, and one concrete way to make it cheaper.

Most usage trackers count tokens per session or per model. animus-limits attributes them to **the work you did**, because every journal entry marks where a piece of work ended.

## How cost is counted

From the `usage` of every model response in `~/.claude/projects/**.jsonl` (subagents included, duplicates removed), in **API-equivalent USD**: list prices per model family, cache writes ×1.25 (5 min) or ×2 (1 h), cache reads ×0.1. It is the closest local proxy for how fast plan limits drain; exact plan accounting is not public. Prices live at the top of `scripts/limits.py`.

Work in a session that never got a journal entry shows as `(no journal) <project>`.

## Token budget

No hooks. The script reads transcripts itself; only its table (≈ 10–15 lines) enters the context.

## Commands

```
limits.py report [--days 7] [--by task|project|day|model] [--top 12]
limits.py set invest-bot 30% [--days 7]     # or '$40'
limits.py unset invest-bot
limits.py check [--verbose]
limits.py estimate invest-bot
```
Config: `~/.claude/animus/limits.json`.

## Privacy

Everything stays on your machine: plain Markdown and JSON files, no network, no database, one stdlib Python script.

## License

MIT
