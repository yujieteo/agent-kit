"""replay: the user's real past requests, replayed in a fresh Claude Code and a
fresh Codex, and the skill that starts in each.

skill-reach (google/skill-reach) cannot count this on the user's setup:
- it has no Codex runtime;
- with its config isolation on, Claude Code has no sign-in ("Not logged in");
- with it off, every skill outside the test set (the user's plugin skills)
  ends the run as a "residency leak", so the real competition is not counted.
So this runner detects a start the way skill-reach does for Claude (a
`Skill` tool_use in --output-format stream-json, claude_code.py:289-292) and
counts every skill, plugin skills too.

Cases (`replay cases`): the first real request of each past session, from
both agents' logs. The label is the skill that started in that session:
the first Skill call or /skill command (Claude), or the first read of a
skills/NAME/SKILL.md (Codex), before the user's next request. A /skill command is replayed without the
command, so the request must win on its words alone. Every session with one
of the repository's skills is a case, plus a fixed random sample (seed 0) of
sessions where none started.

Claude: `claude -p` in an empty folder, the user's own CLAUDE_CONFIG_DIR (its
sign-in, skills and plugins), --tools Skill (so the request does no work),
--no-session-persistence (no log), the model of this run.
Codex: `codex exec --json -s read-only` in an empty folder, a scratch
CODEX_HOME (sign-in copied in, the user's config.toml without the notifier
and the MCP servers, no logs left in the real folder), a scratch HOME whose
~/.agents/skills holds the repository's skills, as after `agent-kit install`.
It is stopped at the first SKILL.md it reads.
"""

from __future__ import annotations

import json
import os
import random
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from .common import REPO, HOME, claude_dir, codex_dir, say

OUT = REPO / "results" / "replay"
MINE = {p.name for p in (REPO / "skills").iterdir() if p.is_dir()}
SKILL_MD = re.compile(r"skills/([\w.:-]+)/SKILL\.md")
NOT_REQUESTS = ("<local-command", "<command-name>/compact", "<command-name>/clear", "Caveat:",
                "[Request interrupted", "<task-notification>", "<system-reminder>", "Continue")


# ---- cases ----------------------------------------------------------------------

def claude_cases(exclude: set[str]):
    for f in (claude_dir() / "projects").glob("*/*.jsonl"):
        if f.stem in exclude:
            continue
        request = label = None
        for line in f.open(errors="replace"):
            try:
                d = json.loads(line)
            except ValueError:
                continue
            msg = d.get("message") or {}
            if d.get("type") == "user" and not d.get("isMeta") and request is not None and label is None:
                c = msg.get("content")
                if isinstance(c, str) and c.strip() and not c.startswith(NOT_REQUESTS):
                    break  # the next request: the first one started no skill
            if d.get("type") == "user" and not d.get("isMeta") and request is None:
                c = msg.get("content")
                if isinstance(c, list):
                    if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
                        continue
                    c = "\n".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
                if not isinstance(c, str) or not c.strip():
                    continue
                m = re.search(r"<command-name>/([\w:-]+)</command-name>", c)
                if m:
                    args = re.search(r"<command-args>(.*?)</command-args>", c, re.S)
                    if m.group(1) in ("advisor", "model", "config", "compact", "clear", "auto-mode-setup") or not (args and args.group(1).strip()):
                        continue
                    request, label = args.group(1).strip(), m.group(1)
                    continue
                if c.startswith(NOT_REQUESTS):
                    continue
                request = c.strip()
            if d.get("type") == "assistant" and request is not None and label is None:
                for b in msg.get("content") or []:
                    if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == "Skill":
                        label = (b.get("input") or {}).get("skill")
                        break
            if request is not None and label is not None:
                break
        if request:
            yield {"source": "claude", "session": f.stem, "request": request, "label": label or "none"}


def codex_cases():
    seen = set()
    files = list((codex_dir() / "sessions").rglob("*.jsonl")) + list((codex_dir() / "archived_sessions").glob("*.jsonl"))
    for f in files:
        sid, request, label, exec_run = f.stem, None, None, False
        for line in f.open(errors="replace"):
            try:
                d = json.loads(line)
            except ValueError:
                continue
            p = d.get("payload") or {}
            if d.get("type") == "session_meta":
                sid = p.get("id", sid)
                exec_run = p.get("originator") == "codex_exec"
            if d.get("type") != "response_item":
                continue
            if p.get("type") == "message" and p.get("role") == "user":
                t = "\n".join(b.get("text", "") for b in p.get("content") or [] if isinstance(b, dict))
                if t.lstrip().startswith(("<environment_context", "# AGENTS.md", "<user_instructions", "<permissions", "<turn_aborted")):
                    continue
                if request is not None:
                    break  # the next request: label only what the first one started
                request = t.strip()
            elif p.get("type") in ("function_call", "custom_tool_call") and request and label is None:
                m = SKILL_MD.search(str(p.get("arguments") or p.get("input") or ""))
                if m:
                    label = m.group(1)
        if request and not exec_run and sid not in seen:  # a thread can be in sessions/ and archived_sessions/
            seen.add(sid)
            yield {"source": "codex", "session": sid, "request": request, "label": label or "none"}
    # Threads that live only in the thread store.
    src = codex_dir() / "thread_history_1.sqlite"
    with tempfile.TemporaryDirectory() as t:
        for s in ("", "-wal", "-shm"):
            if Path(str(src) + s).exists():
                shutil.copy2(str(src) + s, Path(t) / (src.name + s))
        db = sqlite3.connect(Path(t) / src.name)
        threads: dict[str, dict] = {}
        for tid, typ, js in db.execute("select thread_id, item_type, item_json from thread_items "
                                       "where item_type in ('userMessage','commandExecution') order by thread_id, rollout_ordinal"):
            if tid in seen:
                continue
            c = threads.setdefault(tid, {"source": "codex-store", "session": tid, "request": None, "label": "none"})
            d = json.loads(js)
            if typ == "userMessage" and c["request"] is not None:
                c["closed"] = True
            elif c.get("closed"):
                continue
            elif typ == "userMessage":
                c["request"] = "\n".join(b.get("text", "") for b in d.get("content") or [] if isinstance(b, dict)).strip() or None
            elif typ == "commandExecution" and c["request"] and c["label"] == "none":
                m = SKILL_MD.search(d.get("command", ""))
                if m:
                    c["label"] = m.group(1)
        db.close()
    yield from ({k: v for k, v in c.items() if k != "closed"} for c in threads.values() if c["request"])


def build_cases(exclude: set[str], negatives: int) -> list[dict]:
    allc = [c for c in [*claude_cases(exclude), *codex_cases()]
            if 10 <= len(c["request"]) <= 6000 and c["session"] not in exclude]
    pos = [c for c in allc if c["label"] in MINE]
    neg = [c for c in allc if c["label"] == "none"]
    other = [c for c in allc if c["label"] not in MINE and c["label"] != "none"]
    rng = random.Random(0)
    rng.shuffle(neg)
    rng.shuffle(other)
    return pos + neg[:negatives] + other[: max(4, negatives // 4)]


# ---- running --------------------------------------------------------------------

# One fixed, empty working folder: Claude Code makes an (empty) projects/<folder>/memory
# for each new working folder, even with --no-session-persistence (measured).
CLAUDE_CWD = Path(os.environ.get("XDG_CACHE_HOME") or HOME / ".cache") / "agent-kit" / "replay-cwd"


def run_claude(req: str, model: str, timeout: int = 180) -> dict:
    CLAUDE_CWD.mkdir(parents=True, exist_ok=True)
    if any(CLAUDE_CWD.iterdir()):
        raise SystemExit(f"agent-kit: {CLAUDE_CWD} must be empty")
    if True:
        wd = str(CLAUDE_CWD)
        cmd = ["claude", "-p", req, "--output-format", "stream-json", "--verbose", "--tools", "Skill",
               "--no-session-persistence", "--max-turns", "2", "--model", model]
        p = subprocess.Popen(cmd, cwd=wd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                             start_new_session=True)
        started, listed, t0 = None, None, time.time()
        try:
            for line in p.stdout:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if d.get("type") == "system" and d.get("subtype") == "init":
                    listed = len(d.get("skills") or [])
                for b in (d.get("message") or {}).get("content") or []:
                    if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == "Skill":
                        started = (b.get("input") or {}).get("skill")
                        break
                if started or d.get("type") == "result" or time.time() - t0 > timeout:
                    break
        finally:
            os.killpg(p.pid, signal.SIGTERM)
            p.wait()
        return {"started": started or "none", "skills_listed": listed, "seconds": round(time.time() - t0, 1)}


def codex_home(base: Path) -> tuple[Path, Path]:
    home, cx = base / "home", base / "codex"
    (home / ".agents").mkdir(parents=True)
    shutil.copytree(REPO / "skills", home / ".agents" / "skills")
    cx.mkdir()
    shutil.copy2(codex_dir() / "auth.json", cx / "auth.json")
    os.chmod(cx / "auth.json", 0o600)
    lines, skip = [], False
    for l in (codex_dir() / "config.toml").read_text().splitlines():
        if l.startswith("["):
            skip = l.startswith("[mcp_servers")
        if skip or l.startswith("notify"):
            continue
        lines.append(l)
    (cx / "config.toml").write_text("\n".join(lines) + "\n")
    if (codex_dir() / "plugins").is_dir():
        (cx / "plugins").symlink_to(codex_dir() / "plugins")
    return home, cx


def run_codex(req: str, home: Path, cx: Path, timeout: int = 240) -> dict:
    with tempfile.TemporaryDirectory(prefix="agent-kit-replay-") as wd:
        env = {**os.environ, "HOME": str(home), "CODEX_HOME": str(cx)}
        cmd = ["codex", "exec", "--skip-git-repo-check", "-s", "read-only", "--json", req]
        p = subprocess.Popen(cmd, cwd=wd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, text=True, start_new_session=True)
        started, t0, err = None, time.time(), None
        try:
            for line in p.stdout:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                it = d.get("item") or {}
                m = SKILL_MD.search(json.dumps(it.get("command") or it.get("arguments") or ""))
                if m:
                    started = m.group(1)
                if d.get("type") in ("error", "turn.failed"):
                    err = str(d)[:200]
                if started or d.get("type") in ("turn.completed", "turn.failed") or time.time() - t0 > timeout:
                    break
        finally:
            os.killpg(p.pid, signal.SIGTERM)
            p.wait()
        return {"started": started or "none", "seconds": round(time.time() - t0, 1), **({"error": err} if err else {})}


def cmd_replay(args: list[str]) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    exclude = set(args[args.index("--exclude") + 1].split(",")) if "--exclude" in args else set()
    if args[:1] == ["cases"]:
        n = int(args[args.index("--negatives") + 1]) if "--negatives" in args else 20
        cases = build_cases(exclude, n)
        (OUT / "cases.jsonl").write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cases))
        from collections import Counter
        say(f"{len(cases)} cases: " + ", ".join(f"{k} {v}" for k, v in Counter(c['label'] for c in cases).most_common()))
        return 0
    if args[:1] == ["report"]:
        return cmd_report()
    agent = args[args.index("--agent") + 1]
    model = args[args.index("--model") + 1] if "--model" in args else "claude-opus-5-5"
    cases = [json.loads(l) for l in (OUT / "cases.jsonl").read_text().splitlines()]
    out = OUT / f"{agent}.jsonl"
    done = {json.loads(l)["session"] for l in out.read_text().splitlines()} if out.exists() else set()
    auth_before = (codex_dir() / "auth.json").read_bytes()
    with tempfile.TemporaryDirectory(prefix="agent-kit-codex-") as base:
        home = cx = None
        if agent == "codex":
            home, cx = codex_home(Path(base))
        for i, c in enumerate(cases):
            if c["session"] in done:
                continue
            r = run_claude(c["request"], model) if agent == "claude" else run_codex(c["request"], home, cx)
            row = {**c, "agent": agent, **r}
            row["request"] = c["request"][:300]
            with out.open("a") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            say(f"[{i + 1}/{len(cases)}] {c['label']:28} -> {r['started']:28} {r['seconds']}s")
        if agent == "codex" and (Path(cx) / "auth.json").read_bytes() != auth_before:
            say("NOTE: Codex refreshed its sign-in in the scratch copy; the real auth.json was not changed")
    return 0


def names_skill(c: dict) -> bool:
    """The request itself names the skill (a /name or $name the user typed)."""
    return c["label"] in MINE and re.search(r"[/$]" + re.escape(c["label"]) + r"\b", c["request"]) is not None


def cmd_report() -> int:
    rows = {}
    for a in ("claude", "codex"):
        if (OUT / f"{a}.jsonl").exists():
            rows[a] = {}
            for r in map(json.loads, (OUT / f"{a}.jsonl").read_text().splitlines()):
                rows[a].setdefault(r["session"], r)  # the first run of a request counts
    for a, rs in rows.items():
        mine = [r for r in rs.values() if r["label"] in MINE]
        words = [r for r in mine if not names_skill(r)]
        neg = [r for r in rs.values() if r["label"] not in MINE]
        hit = lambda xs: sum(r["started"] == r["label"] for r in xs)
        say(f"\n{a}: {len(rs)} requests replayed")
        say(f"  past start of a repository skill: {len(mine)}; same skill now {hit(mine)}, "
            f"another skill {sum(r['started'] not in ('none', r['label']) for r in mine)}, none {sum(r['started'] == 'none' for r in mine)}")
        say(f"    of them, the request does not name the skill: {len(words)}; same skill now {hit(words)}")
        say(f"  past start of no repository skill: {len(neg)}; a repository skill starts now "
            f"{sum(r['started'] in MINE for r in neg)}, another skill {sum(r['started'] not in MINE and r['started'] != 'none' for r in neg)}")
        for r in rs.values():
            if r["started"] != r["label"] and (r["started"] in MINE or r["label"] in MINE):
                say(f"    {r['label']:28} -> {r['started']:28} {r['request'][:70]!r}")
    if len(rows) == 2:
        both = rows["claude"].keys() & rows["codex"].keys()
        diff = [s for s in both if rows["claude"][s]["started"] != rows["codex"][s]["started"]]
        say(f"\nthe two agents start a different skill on {len(diff)} of {len(both)} requests:")
        for s in diff:
            say(f"    claude {rows['claude'][s]['started']:28} codex {rows['codex'][s]['started']:28} {rows['claude'][s]['request'][:60]!r}")
    return 0
