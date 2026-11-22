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
both agents' logs. `label` is the skill that started in that session: the
first Skill call or /skill command (Claude), or the first read of a
skills/NAME/SKILL.md (Codex), before the user's next request. A /skill command
is replayed without the command, so the request must win on its words alone.
Every session with one of the repository's skills is a case, plus a fixed
random sample (seed 0) of sessions where none started.

Answers (`report`): a replay is right when it starts the skill that the
original session shows was wanted, not merely the one that started then. The
marks are in results/replay/marks/marks.jsonl, made by a separate agent that saw
only the original sessions, by the rule in marks/RULE.md: was the work kept,
or did the user correct it?

Before/after (`replay --agent A --before REV --cases FILE --runs N`): each
request runs N times with the skill descriptions at REV and N times with the
current ones, in pairs (run i of both, order drawn with Random(i)). `report`
gives each pass rate with a 95% Wilson range, an exact McNemar test on the
pairs, and a sign-flip test over requests.

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
from collections import Counter
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
        started, listed, t0, result = None, None, time.time(), None
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
                if d.get("type") == "result":
                    result = d
                if started or d.get("type") == "result" or time.time() - t0 > timeout:
                    break
        finally:
            os.killpg(p.pid, signal.SIGTERM)
            p.wait()
        out = {"started": started or "none", "skills_listed": listed, "seconds": round(time.time() - t0, 1)}
        if not started and (result is None or result.get("is_error")):
            out["error"] = "no result" if result is None else str(result.get("result") or result.get("subtype"))[:200]
        return out


# A replay must not act. A request that starts no skill runs on, and these plugins can
# drive the Mac outside the read-only sandbox: on 2026-11-22 replays opened Google Chrome
# and set off macOS keychain prompts (measured). None of the four holds a skill, so the
# list of skills Codex sees is the same without them.
NO_PLUGINS = ("browser@openai-bundled", "chrome@openai-bundled",
              "computer-use@openai-bundled", "unified-computer-use@openai-bundled")


def codex_home(base: Path, skills: Path = REPO / "skills") -> tuple[Path, Path]:
    home, cx = base / "home", base / "codex"
    (home / ".agents").mkdir(parents=True)
    shutil.copytree(skills, home / ".agents" / "skills")
    cx.mkdir()
    shutil.copy2(codex_dir() / "auth.json", cx / "auth.json")
    os.chmod(cx / "auth.json", 0o600)
    lines, skip = [], False
    for l in (codex_dir() / "config.toml").read_text().splitlines():
        if l.startswith("["):
            skip = l.startswith("[mcp_servers") or any(l == f'[plugins."{n}"]' for n in NO_PLUGINS)
        if skip or l.startswith("notify"):
            continue
        lines.append(l)
    lines += [f'\n[plugins."{n}"]\nenabled = false' for n in NO_PLUGINS]
    (cx / "config.toml").write_text("\n".join(lines) + "\n")
    # The user's plugins, linked one by one, without the ones in NO_PLUGINS.
    cache = codex_dir() / "plugins" / "cache"
    if cache.is_dir():
        for src in cache.iterdir():
            if src.is_dir():
                for plug in src.iterdir():
                    if f"{plug.name}@{src.name}" not in NO_PLUGINS:
                        (cx / "plugins" / "cache" / src.name).mkdir(parents=True, exist_ok=True)
                        (cx / "plugins" / "cache" / src.name / plug.name).symlink_to(plug)
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
                if not started and time.time() - t0 > timeout:
                    err = "timeout"
                if started or d.get("type") in ("turn.completed", "turn.failed") or time.time() - t0 > timeout:
                    break
        finally:
            os.killpg(p.pid, signal.SIGTERM)
            p.wait()
        return {"started": started or "none", "seconds": round(time.time() - t0, 1), **({"error": err} if err else {})}


# ---- before/after: the same requests with two versions of the skill descriptions ----

def skills_at(rev: str, dest: Path) -> Path:
    """The repository's skills/ folder as it was at git revision REV."""
    dest.mkdir(parents=True)
    tar = subprocess.run(["git", "-C", str(REPO), "archive", rev, "skills"], capture_output=True, check=True).stdout
    subprocess.run(["tar", "-x", "-C", str(dest)], input=tar, check=True)
    return dest / "skills"


def run_ab(agent: str, cases: list[dict], before: str, runs: int, out: Path, model: str, workers: int = 4) -> None:
    """Each request runs once per condition in every block i (order drawn with Random(i)).

    Claude Code reads the installed copies in $CLAUDE_CONFIG_DIR/skills, so the SKILL.md
    files that differ are swapped for each block and put back after. Codex gets one
    scratch home per condition and worker.
    """
    from concurrent.futures import ThreadPoolExecutor
    done = set()
    if out.exists():
        done = {(r["session"], r["run"], r["condition"]) for r in map(json.loads, out.read_text().splitlines())
                if "error" not in r}
    with tempfile.TemporaryDirectory(prefix="agent-kit-ab-") as base:
        trees = {"before": skills_at(before, Path(base) / "before"), "after": REPO / "skills"}
        swap = [n for n in MINE if (trees["before"] / n / "SKILL.md").read_bytes() != (REPO / "skills" / n / "SKILL.md").read_bytes()]
        live = {n: claude_dir() / "skills" / n / "SKILL.md" for n in swap} if agent == "claude" else {}
        saved = {n: f.read_bytes() for n, f in live.items()}
        if live:  # put the files back on `kill` too
            signal.signal(signal.SIGTERM, lambda *_: sys.exit(1))
        homes = {}
        if agent == "codex":
            for cond, tree in trees.items():
                for w in range(workers):
                    homes[cond, w] = codex_home(Path(base) / f"{cond}-{w}", tree)
        try:
            for i in range(runs):
                order = ["before", "after"]
                random.Random(i).shuffle(order)
                for cond in order:
                    todo = [c for c in cases if (c["session"], i, cond) not in done]
                    if not todo:
                        continue
                    if agent == "claude":
                        for n, f in live.items():
                            f.write_bytes((trees[cond] / n / "SKILL.md").read_bytes())
                        go = lambda c, w: run_claude(c["request"], model)
                        w_n = workers
                    else:
                        go = lambda c, w: run_codex(c["request"], *homes[cond, w])
                        w_n = workers
                    with ThreadPoolExecutor(w_n) as ex:
                        res = list(ex.map(lambda cw: go(*cw), [(c, k % w_n) for k, c in enumerate(todo)]))
                    with out.open("a") as fh:
                        for c, r in zip(todo, res):
                            fh.write(json.dumps({**c, "agent": agent, "run": i, "condition": cond, **r}, ensure_ascii=False) + "\n")
                    say(f"run {i} {cond}: " + ", ".join(r["started"] for r in res))
        finally:
            for n, f in live.items():
                f.write_bytes(saved[n])


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
    if "--before" in args:  # replay --agent A --before REV --cases FILE --runs N
        cases = [json.loads(l) for l in Path(args[args.index("--cases") + 1]).read_text().splitlines()]
        run_ab(agent, cases, args[args.index("--before") + 1], int(args[args.index("--runs") + 1]),
               OUT / f"ab-{agent}.jsonl", model)
        return 0
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


# ---- report: right or wrong by what happened next in the original session ----------

MARKS = OUT / "marks" / "marks.jsonl"


def answers() -> dict[str, str]:
    """Session -> the skill the request should start, from marks.jsonl (see marks/RULE.md).
    `none` means no skill; `not:X` means anything but X. Unclear cases have no answer."""
    out = {}
    if MARKS.exists():
        for m in map(json.loads, MARKS.read_text().splitlines()):
            if m.get("outcome") in ("kept", "corrected") and m.get("answer"):
                out[m["session"]] = m["answer"]
    return out


def right(started: str, answer: str) -> bool:
    return started != answer[4:] if answer.startswith("not:") else started == answer


def wilson(k: int, n: int) -> str:
    """95% range for a share k/n (Wilson score interval)."""
    if n == 0:
        return "-"
    z, ph = 1.959964, k / n
    c = (ph + z * z / (2 * n)) / (1 + z * z / n)
    h = z / (1 + z * z / n) * (ph * (1 - ph) / n + z * z / (4 * n * n)) ** 0.5
    return f"{k}/{n} [{max(0, c - h):.2f}, {min(1, c + h):.2f}]"


def mcnemar(b: int, c: int) -> float:
    """Exact two-sided McNemar test: b pairs right only after, c right only before."""
    from math import comb
    n = b + c
    return 1.0 if n == 0 else min(1.0, 2 * sum(comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)


def sign_flip(diffs: list[float]) -> float:
    """Two-sided sign-flip test of the mean of paired differences (all 2^n sign choices)."""
    import itertools
    obs = abs(sum(diffs))
    if not diffs:
        return 1.0
    hits = sum(abs(sum(d * s for d, s in zip(diffs, signs))) >= obs - 1e-12
               for signs in itertools.product((1, -1), repeat=len(diffs)))
    return hits / 2 ** len(diffs)


def report_ab(ans: dict[str, str]) -> None:
    for agent in ("claude", "codex"):
        f = OUT / f"ab-{agent}.jsonl"
        if not f.exists():
            continue
        rows = [r for r in map(json.loads, f.read_text().splitlines()) if "error" not in r]
        by: dict[str, dict] = {}
        for r in rows:
            by.setdefault(r["session"], {"req": r["request"], "how": r.get("how", ""), "before": {}, "after": {}})
            by[r["session"]][r["condition"]][r["run"]] = r["started"]
        say(f"\n{agent}: before = 54ae930, after = 62c5fcb; skills started per request")
        b = c = 0
        diffs = []
        for sid, d in by.items():
            a = ans.get(sid)
            cnt = lambda cond: ", ".join(f"{k} {v}" for k, v in Counter(d[cond].values()).most_common())
            line = f"  {d['req'][:60]!r} ({d['how']}) answer {a or 'unmarked'}"
            say(line)
            for cond in ("before", "after"):
                k = sum(right(x, a) for x in d[cond].values()) if a else None
                say(f"      {cond:6} {cnt(cond):70} " + (f"right {wilson(k, len(d[cond]))}" if a else ""))
            if a:
                runs = d["before"].keys() & d["after"].keys()
                b += sum(right(d["after"][i], a) and not right(d["before"][i], a) for i in runs)
                c += sum(right(d["before"][i], a) and not right(d["after"][i], a) for i in runs)
                diffs.append(sum(right(d["after"][i], a) for i in runs) / len(runs)
                             - sum(right(d["before"][i], a) for i in runs) / len(runs))
        say(f"  paired runs where only 'after' was right: {b}; only 'before': {c}; exact McNemar p = {mcnemar(b, c):.4f}")
        say(f"  sign-flip test over {len(diffs)} marked requests: p = {sign_flip(diffs):.4f} "
            f"(smallest possible {2 / 2 ** len(diffs):.4f})")
        for sid, d in by.items():
            if "1512.06410" in d["req"] and ans.get(sid):
                a, runs = ans[sid], d["before"].keys() & d["after"].keys()
                b1 = sum(right(d["after"][i], a) and not right(d["before"][i], a) for i in runs)
                c1 = sum(right(d["before"][i], a) and not right(d["after"][i], a) for i in runs)
                say(f"  the request the change was made for: only after {b1}, only before {c1}, p = {mcnemar(b1, c1):.4f}")


def cmd_report() -> int:
    ans = answers()
    say(f"marks: {len(ans)} requests have an answer ({MARKS})")
    for a in ("claude", "codex"):
        f = OUT / f"{a}.jsonl"
        if not f.exists():
            continue
        rs: dict[str, dict] = {}
        for r in map(json.loads, f.read_text().splitlines()):
            if "error" not in r:
                rs.setdefault(r["session"], r)
        scored = [r for r in rs.values() if r["session"] in ans]
        k = sum(right(r["started"], ans[r["session"]]) for r in scored)
        same = sum(r["started"] == r["label"] for r in scored)
        say(f"\n{a}: {len(rs)} requests replayed, {len(scored)} with an answer")
        say(f"  right by what happened next: {wilson(k, len(scored))}")
        say(f"  same skill as the original session (the old pass rule): {same}/{len(scored)}")
        for r in scored:
            if not right(r["started"], ans[r["session"]]):
                say(f"    started {r['started']:28} answer {ans[r['session']]:28} {r['request'][:60]!r}")
    report_ab(ans)
    return 0
