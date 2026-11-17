---
name: limits
description: Token spend broken down by journal task, project, day and model across sessions, plus per-task budgets for Claude Code (limits like "invest-bot ≤ 30% of my week") and a cost estimate before a big task. Prefer this over a generic usage breakdown whenever the question is per task or project, spans sessions, or is about a budget. Use on /limits, "how much did X cost", "which task ate my limit", "set a limit", before a task the user says is big or expensive, or in Russian — «сколько сожрала задача», «куда ушёл лимит», «сколько стоил X», «поставь лимит», «во сколько обойдётся».
---

# Limits

All numbers come from one script: `L` = `python3 "<plugin root>/scripts/limits.py"`, where the plugin root is two levels above this skill's base directory. Use `python` if `python3` is missing. On Windows, `python3`/`python` may be Microsoft Store stubs: then use the interpreter and script path from this plugin's `cmd` in `~/.claude/ecosystem.json` (or a start-of-session line), and write paths with forward slashes so a trailing `\` does not eat the closing quote. The script reads transcripts itself; never read transcripts or journals yourself for this.

Unit: API-equivalent USD with prompt caching — a proxy for how fast plan limits drain, not a bill. Say so once when you first show numbers.

## Where it went
`L report` (last 7 days by journal task, with $ and token columns) · `--by project|day|model` · `--days N` · `--top N`. Token totals include cache reads, which cost ~10% of fresh input: `$` is the better measure of how fast the limit drains. Never compute or estimate token numbers yourself.
Tasks come from animus-journal entries: a session's responses go to the first tag of the entry written during it or within 30 min after its last response. "(no journal) X" is work in project X with no such entry (for example, recorded a day later) — say so, don't invent a rule.
Show the table as is, then one or two lines of takeaways (the biggest item, anything surprising). No long commentary.

## Limits
`L set <task-or-project> 30%` or `L set <key> '$40'` (fixed), window `--days N` (default 7). `L unset <key>`. One limit per key: a new `set` replaces the old one (the script says so). A key that is both a task tag and a project name counts the whole project; use the task tag alone (e.g. `landing-copy`) if that is meant.
A `%` limit is relative: the share of *your own* total spend in the window, not of the plan limit (the plan limit is unknown to the script). If the task is most of what you do, it stays "over" however little you spend. When the user means "of my plan" or a budget, use `$`, and say which one you set. If the task is already most of the spend (a % limit would be OVER from day one), say so and ask whether they want `$` instead, proposing a number; never switch the limit type or value on your own.
`L check` prints only limits at ≥ 80% (`--at 50` for another threshold, `--verbose` for all). A line saying "nothing attributed to it yet" means no journal entry with that first tag covers the spend — explain that, don't guess at other causes. Run it whenever this skill is used, and mention any line it prints. There is no background warning: limits are checked only when this skill or `/brief` runs — say so if the user asks to be warned, and suggest running `/brief` at the start of the day. Don't create hooks or edit settings to make it automatic unless the user explicitly asks for that.

## Before an expensive task
When the user starts something big, or asks what it will cost: `L estimate <task words>` — median/max of past sessions of that task over the last 60 days (`--days N`), model mix, share of a week. With no past sessions, give a rough range from similar tasks and label it a guess.
Then give one concrete suggestion only if it would save a lot: e.g. use Sonnet for mechanical steps, lower effort, split the task, or run it after the limit resets. Do not lecture; the user decides.
