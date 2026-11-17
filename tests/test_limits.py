"""End-to-end tests for scripts/limits.py (stdlib unittest, no dependencies)."""
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "limits.py"


def iso(d):
    return d.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


class LimitsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.claude = self.tmp / "claude"
        self.proj = self.tmp / "work" / "bot"
        (self.proj / ".journal" / "log").mkdir(parents=True)
        (self.proj / ".git").mkdir()  # not a real repo: git fails, cwd is used as the root
        self.env = dict(os.environ, CLAUDE_CONFIG_DIR=str(self.claude),
                        JOURNAL_GLOBAL_DIR=str(self.tmp / "journal"),
                        ANIMUS_LIMITS_FILE=str(self.tmp / "limits.json"),
                        CLAUDE_ECOSYSTEM_FILE=str(self.tmp / "eco.json"),
                        PYTHONIOENCODING="utf-8")
        self.now = dt.datetime.now().astimezone().replace(second=0, microsecond=0)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_l(self, *args, ok=True):
        r = subprocess.run([sys.executable, str(SCRIPT), *args], env=self.env,
                           capture_output=True, text=True, encoding="utf-8")
        if ok:
            self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def session(self, sid, start, n, model="claude-opus-5-5", out_tokens=1000, cwd=None, sub=False):
        d = self.claude / "projects" / "p"
        f = (d / sid / "subagents" / "agent-1.jsonl") if sub else (d / f"{sid}.jsonl")
        f.parent.mkdir(parents=True, exist_ok=True)
        lines = []
        for i in range(n):
            u = {"input_tokens": 0, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0,
                 "output_tokens": out_tokens}
            rec = {"type": "assistant", "timestamp": iso(start + dt.timedelta(minutes=i)),
                   "cwd": str(cwd or self.proj), "sessionId": sid,
                   "message": {"id": f"{sid}-{'s' if sub else 'm'}{i}", "model": model, "usage": u}}
            lines.append(json.dumps(rec))
            lines.append(json.dumps(rec))  # the same response often appears twice; count once
        with open(f, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")

    def entry(self, when, tags, title="t"):
        log = self.proj / ".journal" / "log" / f"{when:%Y-%m}.md"
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(f"## {when:%Y-%m-%d %H:%M} {' '.join('#' + t for t in tags)} — {title}\nDone: x\n\n")

    def test_cost_dedup_and_attribution(self):
        s = self.now - dt.timedelta(hours=3)
        self.session("a", s, 10)                       # 10 x 1000 opus output = $0.25
        self.entry(s + dt.timedelta(minutes=12), ["parser", "api"])
        self.session("b", s + dt.timedelta(hours=1), 4)  # no journal entry
        out = self.run_l("report")
        self.assertIn("$0.35 API-equivalent, 14 responses, 2 sessions", out)
        self.assertIn("parser", out)
        self.assertIn("$0.25", out)
        self.assertIn("(no journal) bot", out)
        self.assertNotIn("api ", out)  # only the first tag is the task
        self.assertIn("14K tokens (14K output", out)
        self.assertRegex(out, r"parser\s+\$0\.25\s+71%\s+1\s+10K\s+10K")
        self.run_l("set", "parser", "$0.5")              # 50% used
        self.assertEqual(self.run_l("check").strip(), "")  # below the default 80%
        self.assertIn("near: parser", self.run_l("check", "--at", "40"))
        self.run_l("set", "nothing-yet", "$5")
        self.assertIn("nothing attributed to it yet", self.run_l("check", "--verbose"))

    def test_two_entries_split_a_session(self):
        s = self.now - dt.timedelta(hours=3)
        self.session("a", s, 10)
        self.entry(s + dt.timedelta(minutes=4), ["first"])   # covers 0..5 (1-min tolerance: entries are stamped to the minute)
        self.entry(s + dt.timedelta(minutes=20), ["second"])  # covers 6..9
        out = self.run_l("report")
        self.assertRegex(out, r"first\s+\$0\.15")
        self.assertRegex(out, r"second\s+\$0\.10")

    def test_subagents_and_models(self):
        s = self.now - dt.timedelta(hours=2)
        self.session("a", s, 2, model="claude-sonnet-5-5")
        self.session("a", s, 2, model="claude-haiku-5-5", sub=True)
        out = self.run_l("report", "--by", "model")
        self.assertIn("sonnet", out)
        self.assertIn("haiku", out)
        self.assertIn("1 sessions", out)

    def test_limits_check_and_estimate(self):
        s = self.now - dt.timedelta(hours=5)
        self.session("a", s, 8)
        self.entry(s + dt.timedelta(minutes=10), ["bot-ml"])
        self.session("b", s + dt.timedelta(hours=1), 2)
        self.entry(s + dt.timedelta(hours=1, minutes=5), ["ui"])
        self.assertEqual(self.run_l("check"), "")  # no limits: silent
        self.run_l("set", "bot-ml", "50%")
        self.run_l("set", "ui", "$10")
        out = self.run_l("check")
        self.assertIn("OVER: bot-ml", out)         # 80% of spend vs a 50% limit
        self.assertNotIn("ui", out)                 # far below $10
        self.assertIn("ok: ui", self.run_l("check", "--verbose"))
        est = self.run_l("estimate", "bot-ml")
        self.assertIn("1 past sessions", est)
        self.assertIn("opus 100%", est)
        self.run_l("unset", "bot-ml")
        self.assertEqual(self.run_l("check"), "")
        self.assertIn("no past sessions", self.run_l("estimate", "nothing-like-this"))

    def test_bad_limit_and_old_data(self):
        r = subprocess.run([sys.executable, str(SCRIPT), "set", "x", "lots"], env=self.env,
                           capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.session("old", self.now - dt.timedelta(days=30), 3)
        self.assertIn("$0.00 API-equivalent, 0 responses", self.run_l("report"))
        self.assertIn("3 responses", self.run_l("report", "--days", "40"))


if __name__ == "__main__":
    unittest.main()
