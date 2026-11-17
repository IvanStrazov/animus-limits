#!/usr/bin/env python3
"""animus-limits: token spend per task, per-task limits and cost estimates for Claude Code.

Reads Claude Code transcripts (~/.claude/projects/**.jsonl, subagents included) and,
when present, animus-journal entries, and attributes every model response to the
journal task it led to (the first tag of the entry written after it in that session).

Cost unit: API-equivalent USD at list prices (PRICES below), with prompt caching:
cache writes x1.25 (5 min) or x2 (1 h), cache reads x0.1. It is the closest local
proxy for how fast plan limits drain; exact plan accounting is not public.

Commands:
  report [--days N] [--by task|project|day|model] [--top N]   spend table
  set KEY LIMIT [--days N]     limit for a task tag or project: "30%" of your total, or "$40"
  unset KEY
  check [--days N] [--at P]    limits at >= 80% (or P%), one line each (silent when all fine)
  estimate TERM...             past sessions of a task: median / max cost, models, requests
  where                        print the config path

Config: ~/.claude/animus/limits.json (override with ANIMUS_LIMITS_FILE).
Standard library only, Python 3.9+. No network.
"""
import argparse
import datetime as dt
import json
import os
import re
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

CLAUDE_DIR = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude").expanduser()
JOURNAL_GLOBAL = Path(os.environ.get("JOURNAL_GLOBAL_DIR") or Path.home() / "journal").expanduser()
CFG = Path(os.environ.get("ANIMUS_LIMITS_FILE") or CLAUDE_DIR / "animus" / "limits.json").expanduser()
ECO_FILE = Path(os.environ.get("CLAUDE_ECOSYSTEM_FILE") or CLAUDE_DIR / "ecosystem.json").expanduser()
SCRIPT = Path(__file__).resolve()
SELF = "animus-limits"
WARN_AT = 0.8

# USD per 1M tokens (input, output) by model family. Edit to match current list prices.
PRICES = {"opus": (5.0, 25.0), "fable": (5.0, 25.0), "sonnet": (3.0, 15.0), "haiku": (1.0, 5.0)}
DEFAULT_PRICE = (3.0, 15.0)
CACHE_WRITE_5M, CACHE_WRITE_1H, CACHE_READ = 1.25, 2.0, 0.1
NO_JOURNAL = "(no journal)"

for _s in (sys.stdin, sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass


# ---------- helpers ----------

def parse_ts(s):
    if not s:
        return None
    try:
        d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d if d.tzinfo else d.astimezone()
    except ValueError:
        return None


def family(model):
    m = (model or "").lower()
    return next((f for f in PRICES if f in m), "other")


def cost_of(model, u):
    pin, pout = PRICES.get(family(model), DEFAULT_PRICE)
    cc = u.get("cache_creation") or {}
    w1h = cc.get("ephemeral_1h_input_tokens")
    w5m = cc.get("ephemeral_5m_input_tokens")
    total_w = u.get("cache_creation_input_tokens") or 0
    if w1h is None and w5m is None:
        w5m, w1h = total_w, 0
    units = ((u.get("input_tokens") or 0)
             + (w5m or 0) * CACHE_WRITE_5M + (w1h or 0) * CACHE_WRITE_1H
             + (u.get("cache_read_input_tokens") or 0) * CACHE_READ) * pin \
        + (u.get("output_tokens") or 0) * pout
    return units / 1e6


def money(x):
    return f"${x:,.2f}" if x < 100 else f"${x:,.0f}"


_root_cache = {}


def _inside_journal(cwd):
    """A folder inside a journal (~/journal/... or <project>/.journal/...) belongs to that journal,
    so running a command from there never creates a nested .journal."""
    try:
        p = Path(cwd).resolve()
        g = JOURNAL_GLOBAL.resolve()
    except (OSError, RuntimeError):
        return None
    if p == g or g in p.parents:
        return JOURNAL_GLOBAL
    for q in (p, *p.parents):
        if q.name == ".journal":
            return q
    return None


def journal_dir(cwd):
    """Same rule as animus-journal: git root/.journal, or the global dir for projectless sessions."""
    _j = _inside_journal(cwd)
    if _j is not None:
        return _j
    if cwd in _root_cache:
        return _root_cache[cwd]
    p = Path(cwd)
    s = str(p).replace("\\", "/").lower()
    res = None
    if "scratch-workspaces" in s or not p.exists():
        res = JOURNAL_GLOBAL
    else:
        for base in (Path.home(), Path(tempfile.gettempdir())):
            try:
                if p.resolve() == base.resolve():
                    res = JOURNAL_GLOBAL
            except OSError:
                pass
    if res is None:
        try:
            top = subprocess.run(["git", "-C", str(p), "rev-parse", "--show-toplevel"],
                                 capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5).stdout.strip()
        except Exception:
            top = ""
        res = Path(top or p) / ".journal"
    _root_cache[cwd] = res
    return res


_entry_cache = {}
ENTRY_RE = re.compile(r"^## (\d{4}-\d{2}-\d{2} \d{2}:\d{2})\s+(.*?)\s+—\s+(.*)$")


def journal_entries(jdir):
    """[(aware datetime, first tag, title)] sorted by time."""
    key = str(jdir)
    if key in _entry_cache:
        return _entry_cache[key]
    out = []
    for log in sorted((jdir / "log").glob("*.md")) if (jdir / "log").is_dir() else []:
        for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
            m = ENTRY_RE.match(line)
            if not m:
                continue
            when = dt.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M").astimezone()
            tags = re.findall(r"#([^\s#]+)", m.group(2))
            out.append((when, tags[0] if tags else "untagged", m.group(3)))
    out.sort()
    _entry_cache[key] = out
    return out


def project_name(cwd):
    j = journal_dir(cwd)
    return "~/journal" if j == JOURNAL_GLOBAL else j.parent.name


# ---------- transcripts ----------

def transcript_files():
    root = CLAUDE_DIR / "projects"
    if not root.is_dir():
        return []
    return list(root.glob("*/*.jsonl")) + list(root.glob("*/*/subagents/*.jsonl"))


def responses(since=None):
    """One dict per model response: ts, session, cwd, model, cost. Deduplicated by message id."""
    seen, out, cwd_of = set(), [], {}
    for f in transcript_files():
        try:
            if since and dt.datetime.fromtimestamp(f.stat().st_mtime, dt.timezone.utc) < since:
                continue
            fh = open(f, encoding="utf-8", errors="replace")
        except OSError:
            continue
        sub = f.parent.name == "subagents"
        session = f.parent.parent.name if sub else f.stem
        with fh:
            for line in fh:
                if '"usage"' not in line and '"cwd"' not in line:
                    continue
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if d.get("cwd"):
                    cwd_of.setdefault(session, d["cwd"])
                if d.get("type") != "assistant":
                    continue
                msg = d.get("message") or {}
                u, mid = msg.get("usage"), msg.get("id") or d.get("uuid")
                ts = parse_ts(d.get("timestamp"))
                if not u or not mid or mid in seen or not ts or (since and ts < since):
                    continue
                seen.add(mid)
                out.append({"ts": ts, "session": session, "cwd": d.get("cwd"),
                            "model": msg.get("model") or "", "cost": cost_of(msg.get("model"), u),
                            "tok": sum((u.get(k) or 0) for k in ("input_tokens", "cache_creation_input_tokens",
                                                                 "cache_read_input_tokens", "output_tokens")),
                            "out": u.get("output_tokens") or 0})
    for r in out:
        r["cwd"] = r["cwd"] or cwd_of.get(r["session"], "")
    return out


def attribute(resps):
    """Add 'task' and 'project' to each response: the journal entry written after it in its session."""
    by_session = {}
    for r in resps:
        by_session.setdefault(r["session"], []).append(r)
    for rs in by_session.values():
        rs.sort(key=lambda r: r["ts"])
        cwd = next((r["cwd"] for r in rs if r["cwd"]), "")
        jdir = journal_dir(cwd) if cwd else JOURNAL_GLOBAL
        start, end = rs[0]["ts"], rs[-1]["ts"] + dt.timedelta(minutes=30)
        entries = [e for e in journal_entries(jdir) if start - dt.timedelta(minutes=1) <= e[0] <= end]
        proj = project_name(cwd) if cwd else "?"
        for r in rs:
            r["project"] = proj
            nxt = next((e for e in entries if e[0] >= r["ts"] - dt.timedelta(minutes=1)), None)
            e = nxt or (entries[-1] if entries else None)
            r["task"] = e[1] if e else f"{NO_JOURNAL} {proj}"
    return resps


def window(days):
    return dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)


# ---------- config ----------

def load_cfg():
    try:
        c = json.loads(CFG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        c = {}
    c.setdefault("limits", {})
    return c


def save_cfg(c):
    CFG.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(CFG.parent), prefix=".tmp-")
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(c, ensure_ascii=False, indent=2) + "\n")
    os.replace(tmp, CFG)


def eco_register():
    try:
        e = json.loads(ECO_FILE.read_text(encoding="utf-8"))
        if not isinstance(e, dict):
            e = {}
    except (OSError, ValueError):
        e = {}
    e.setdefault("plugins", {})
    me = {"cmd": f'"{sys.executable}" "{SCRIPT}"'}
    if e["plugins"].get(SELF) != me:
        e["plugins"][SELF] = me
        try:
            ECO_FILE.parent.mkdir(parents=True, exist_ok=True)
            ECO_FILE.write_text(json.dumps(e, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except OSError:
            pass


# ---------- commands ----------

def group(resps, by):
    key = {"task": lambda r: r["task"], "project": lambda r: r["project"],
           "day": lambda r: r["ts"].astimezone().strftime("%Y-%m-%d"),
           "model": lambda r: family(r["model"])}[by]
    g = {}
    for r in resps:
        k = key(r)
        cost, n, sessions, tok, out = g.get(k, (0.0, 0, set(), 0, 0))
        sessions.add(r["session"])
        g[k] = (cost + r["cost"], n + 1, sessions, tok + r.get("tok", 0), out + r.get("out", 0))
    return g


def tokens(n):
    return f"{n / 1e6:.1f}M" if n >= 1e6 else (f"{n / 1e3:.0f}K" if n >= 1e3 else str(n))


def cmd_report(a):
    rs = attribute(responses(window(a.days)))
    total = sum(r["cost"] for r in rs)
    print(f"last {a.days} days: {money(total)} API-equivalent, {len(rs)} responses, "
          f"{len({r['session'] for r in rs})} sessions, {tokens(sum(r['tok'] for r in rs))} tokens "
          f"({tokens(sum(r['out'] for r in rs))} output; cache reads count fully here but cost 10%)")
    if not rs:
        return
    g = sorted(group(rs, a.by).items(), key=lambda kv: (kv[0] if a.by == "day" else -kv[1][0]))
    w = max(len(k) for k, _ in g[:a.top]) if a.by != "day" else 10
    print(f"{a.by:<{w}}  {'cost':>9}  {'share':>5}  {'sessions':>8}  {'tokens':>7}  {'output':>7}")
    for k, (cost, n, sess, tok, out) in g[:a.top]:
        print(f"{k:<{w}}  {money(cost):>9}  {cost / total:>5.0%}  {len(sess):>8}  {tokens(tok):>7}  {tokens(out):>7}")
    if len(g) > a.top:
        rest = sum(v[0] for _, v in g[a.top:])
        print(f"{f'(+{len(g) - a.top} more)':<{w}}  {money(rest):>9}  {rest / total:>5.0%}")


def parse_limit(s):
    s = s.strip()
    if s.endswith("%"):
        return {"share": float(s[:-1]) / 100}
    if s.startswith("$"):
        return {"usd": float(s[1:])}
    raise SystemExit("limit must look like 30% (share of your total) or $40 (API-equivalent)")


def cmd_set(a):
    c = load_cfg()
    old = c["limits"].get(a.key)
    c["limits"][a.key] = dict(parse_limit(a.limit), days=a.days)
    save_cfg(c)
    was = ""
    if old:  # one limit per key: a new one replaces the old
        prev = f"{old['share']:.0%}" if "share" in old else money(old["usd"])
        was = f" (replaced the previous limit {prev} per {old.get('days', 7)} days)"
    print(f"limit {a.key}: {a.limit} per {a.days} days{was}")


def cmd_unset(a):
    c = load_cfg()
    print("removed" if c["limits"].pop(a.key, None) is not None else "no such limit")
    save_cfg(c)


def limit_status(c, rs_cache):
    """[(key, used, cap, ratio, days)] for every configured limit."""
    out = []
    for key, lim in c["limits"].items():
        days = int(lim.get("days", 7))
        if days not in rs_cache:
            rs_cache[days] = attribute(responses(window(days)))
        rs = rs_cache[days]
        total = sum(r["cost"] for r in rs) or 1e-9
        used = sum(r["cost"] for r in rs if key in (r["task"], r["project"]))
        cap = lim["share"] * total if "share" in lim else lim["usd"]
        out.append((key, used, cap, used / cap if cap else 0, days, lim))
    return out


def cmd_check(a):
    c = load_cfg()
    eco_register()
    if not c["limits"]:
        print("no limits set (`set KEY 30%`)" if a.verbose else "", end="")
        return
    warn = (a.at / 100) if a.at else WARN_AT
    for key, used, cap, ratio, days, lim in limit_status(c, {}):
        if ratio >= warn or a.verbose:
            mark = "OVER" if ratio >= 1 else ("near" if ratio >= warn else "ok")
            what = (f"{lim['share']:.0%} of all your spend; this key is {used / (cap / lim['share']):.0%} of it"
                    if "share" in lim and cap else (f"{lim['share']:.0%} of total" if "share" in lim
                                                    else money(lim["usd"])))
            extra = ("; nothing attributed to it yet: spend reaches a task only via a journal entry with that "
                     "first tag, written during the session or <= 30 min after it") if used == 0 else ""
            print(f"[limits] {mark}: {key} used {money(used)} of {money(cap)} ({ratio:.0%}; limit {what}, {days}d{extra})")


def cmd_estimate(a):
    terms = [t.lower().lstrip("#") for t in a.terms]
    rs = attribute(responses(window(a.days)))
    match = [r for r in rs if all(t in r["task"].lower() or t in r["project"].lower() for t in terms)]
    if not match:
        print("no past sessions for that task")
        return
    per = {}
    for r in match:
        cost, n, models = per.get(r["session"], (0.0, 0, {}))
        models[family(r["model"])] = models.get(family(r["model"]), 0) + r["cost"]
        per[r["session"]] = (cost + r["cost"], n + 1, models)
    costs = sorted(v[0] for v in per.values())
    reqs = [v[1] for v in per.values()]
    mix = {}
    for v in per.values():
        for m, x in v[2].items():
            mix[m] = mix.get(m, 0) + x
    tot = sum(mix.values())
    week = sum(r["cost"] for r in rs if r["ts"] >= window(7)) or 1e-9
    print(f"{len(per)} past sessions of '{' '.join(a.terms)}' in {a.days} days")
    print(f"per session: median {money(statistics.median(costs))}, max {money(costs[-1])}, "
          f"median {int(statistics.median(reqs))} responses")
    print("models: " + ", ".join(f"{m} {x / tot:.0%}" for m, x in sorted(mix.items(), key=lambda kv: -kv[1])))
    print(f"a median session = {statistics.median(costs) / week:.0%} of your last 7 days of spend")
    print("cheaper option: sonnet costs ~60% of opus per token; haiku ~20%.")


def cmd_where(_):
    print(CFG)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="limits.py", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("report")
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--by", choices=("task", "project", "day", "model"), default="task")
    p.add_argument("--top", type=int, default=12)
    p.set_defaults(fn=cmd_report)
    p = sub.add_parser("set")
    p.add_argument("key")
    p.add_argument("limit")
    p.add_argument("--days", type=int, default=7)
    p.set_defaults(fn=cmd_set)
    p = sub.add_parser("unset")
    p.add_argument("key")
    p.set_defaults(fn=cmd_unset)
    p = sub.add_parser("check")
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--at", type=int, help="warn from this percent of a limit (default 80)")
    p.set_defaults(fn=cmd_check)
    p = sub.add_parser("estimate")
    p.add_argument("terms", nargs="+")
    p.add_argument("--days", type=int, default=60)
    p.set_defaults(fn=cmd_estimate)
    sub.add_parser("where").set_defaults(fn=cmd_where)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
