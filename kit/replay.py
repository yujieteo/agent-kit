"""replay: the user's real past requests, replayed in a fresh Claude Code, and the skill that starts in each.

Cases (`replay cases`): the first real request of each past Claude Code session.
`label` is the skill that started in that session: the first Skill call or /skill
command before the user's next request. A /skill command is replayed without the
command, so the request must win on its words alone. Every session with one of the
repository's skills is a case, plus a fixed random sample (seed 0) of sessions
where none started.

Answers (`report`): a replay is right when it starts the skill that the original
session shows was wanted, not merely the one that started then. The marks are in
results/replay/marks/marks.jsonl.

Before/after (`replay --agent claude --before REV --cases FILE --runs N`): each
request runs N times with the skill descriptions at REV and N times with the
current ones, using isolated temporary CLAUDE_CONFIG_DIR staging so live skills
are never mutated on disk.
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

from .common import (REPO, cache_dir, claude_dir, mcnemar, not_a_request, repo_skills,
                     say, wilson)

OUT = REPO / "results" / "replay"
MINE = set(repo_skills())
SKILL_MD = re.compile(r"skills/([\w.:-]+)/SKILL\.md")


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
                if isinstance(c, str) and c.strip() and not not_a_request(c):
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
                if not_a_request(c):
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


def build_cases(exclude: set[str], negatives: int) -> list[dict]:
    allc = [c for c in claude_cases(exclude)
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
CLAUDE_CWD = cache_dir() / "replay-cwd"


def run_claude(req: str, model: str, timeout: int = 180, env: dict[str, str] | None = None) -> dict:
    CLAUDE_CWD.mkdir(parents=True, exist_ok=True)
    if any(CLAUDE_CWD.iterdir()):
        raise SystemExit(f"agent-kit: {CLAUDE_CWD} must be empty")
    cmd = ["claude", "-p", req, "--output-format", "stream-json", "--verbose", "--tools", "Skill",
           "--no-session-persistence", "--max-turns", "2", "--model", model]
    p = subprocess.Popen(cmd, cwd=CLAUDE_CWD, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                         start_new_session=True, env=env)
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
        try:
            os.killpg(p.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        p.wait()
    out = {"started": started or "none", "skills_listed": listed, "seconds": round(time.time() - t0, 1)}
    if not started and (result is None or result.get("is_error")):
        out["error"] = "no result" if result is None else str(result.get("result") or result.get("subtype"))[:200]
    return out


# ---- before/after: the same requests with two versions of the skill descriptions ----

def skills_at(rev: str, dest: Path) -> Path:
    """The repository's skills/ folder as it was at git revision REV."""
    dest.mkdir(parents=True)
    tar = subprocess.run(["git", "-C", str(REPO), "archive", rev, "skills"], capture_output=True, check=True).stdout
    subprocess.run(["tar", "-x", "-C", str(dest)], input=tar, check=True)
    return dest / "skills"


def git_rev(rev: str) -> str:
    """REV as a short commit name; stops with a message when git cannot resolve it."""
    r = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", rev + "^{commit}"], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"agent-kit replay: git cannot resolve {rev!r} in {REPO}: {r.stderr.strip()}")
    return r.stdout.strip()


def ab_revisions(before: str) -> dict[str, str]:
    """The two versions of the skills that a before/after run compares, as stored in each row.
    "after" is the working tree's skills/: HEAD, with "+edits" when skills/ differs from HEAD."""
    dirty = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain", "--", "skills"],
                           capture_output=True, text=True, check=True).stdout.strip()
    return {"before_rev": git_rev(before), "after_rev": git_rev("HEAD") + ("+edits" if dirty else "")}


def _stage_claude_dir(dest: Path, skills_src: Path) -> Path:
    """Create a temp CLAUDE_CONFIG_DIR that symlinks auth/settings and overlays skills_src."""
    dest.mkdir(parents=True, exist_ok=True)
    src = claude_dir()
    if src.is_dir():
        for entry in src.iterdir():
            if entry.name == "skills":
                continue
            (dest / entry.name).symlink_to(entry)
    dst_skills = dest / "skills"
    dst_skills.mkdir(exist_ok=True)
    if (src / "skills").is_dir():
        for entry in (src / "skills").iterdir():
            if entry.name not in MINE:
                (dst_skills / entry.name).symlink_to(entry)
    for n in MINE:
        if (skills_src / n).is_dir():
            shutil.copytree(skills_src / n, dst_skills / n)
    return dest


def run_ab(agent: str, cases: list[dict], before: str, runs: int, out: Path, model: str, workers: int = 4) -> None:
    """Each request runs once per condition in every block i (order drawn with Random(i)).

    Each condition runs against an isolated temporary CLAUDE_CONFIG_DIR so live skills are never modified.
    """
    from concurrent.futures import ThreadPoolExecutor
    revs = ab_revisions(before)
    done = set()
    if out.exists():
        done = {(r["session"], r["run"], r["condition"]) for r in map(json.loads, out.read_text().splitlines())
                if "error" not in r}
    with tempfile.TemporaryDirectory(prefix="agent-kit-ab-") as base:
        base_p = Path(base)
        trees = {"before": skills_at(before, base_p / "before"), "after": REPO / "skills"}
        cfg_dirs = {cond: _stage_claude_dir(base_p / f"cfg-{cond}", trees[cond]) for cond in ("before", "after")}
        for i in range(runs):
            order = ["before", "after"]
            random.Random(i).shuffle(order)
            for cond in order:
                todo = [c for c in cases if (c["session"], i, cond) not in done]
                if not todo:
                    continue
                env = {**os.environ, "CLAUDE_CONFIG_DIR": str(cfg_dirs[cond])}
                with ThreadPoolExecutor(workers) as ex:
                    res = list(ex.map(lambda c: run_claude(c["request"], model, env=env), todo))
                with out.open("a") as fh:
                    for c, r in zip(todo, res):
                        fh.write(json.dumps({**c, "agent": agent, "run": i, "condition": cond, **revs, **r},
                                            ensure_ascii=False) + "\n")
                say(f"run {i} {cond}: " + ", ".join(r["started"] for r in res))


def cmd_replay(args: list[str]) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    exclude = set(args[args.index("--exclude") + 1].split(",")) if "--exclude" in args else set()
    if args[:1] == ["cases"]:
        n = int(args[args.index("--negatives") + 1]) if "--negatives" in args else 20
        cases = build_cases(exclude, n)
        (OUT / "cases.jsonl").write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cases))
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
    for i, c in enumerate(cases):
        if c["session"] in done:
            continue
        r = run_claude(c["request"], model)
        row = {**c, "agent": agent, **r}
        row["request"] = c["request"][:300]
        with out.open("a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        say(f"[{i + 1}/{len(cases)}] {c['label']:28} -> {r['started']:28} {r['seconds']}s")
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


def wilson_text(k: int, n: int) -> str:
    """k/n and its 95% Wilson range, as the report prints it."""
    if n == 0:
        return "-"
    lo, hi = wilson(k, n)
    return f"{k}/{n} [{lo:.2f}, {hi:.2f}]"


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
    for agent in ("claude",):
        f = OUT / f"ab-{agent}.jsonl"
        if not f.exists():
            continue
        rows = [r for r in map(json.loads, f.read_text().splitlines()) if "error" not in r]
        by: dict[str, dict] = {}
        for r in rows:
            by.setdefault(r["session"], {"req": r["request"], "how": r.get("how", ""), "before": {}, "after": {}})
            by[r["session"]][r["condition"]][r["run"]] = r["started"]
        pairs = sorted({(r.get("before_rev", "not recorded"), r.get("after_rev", "not recorded")) for r in rows})
        say(f"\n{agent}: " + "; ".join(f"before = {b}, after = {a}" for b, a in pairs) + "; skills started per request")
        b = c = 0
        diffs = []
        for sid, d in by.items():
            a = ans.get(sid)
            cnt = lambda cond: ", ".join(f"{k} {v}" for k, v in Counter(d[cond].values()).most_common())
            line = f"  {d['req'][:60]!r} ({d['how']}) answer {a or 'unmarked'}"
            say(line)
            for cond in ("before", "after"):
                k = sum(right(x, a) for x in d[cond].values()) if a else None
                say(f"      {cond:6} {cnt(cond):70} " + (f"right {wilson_text(k, len(d[cond]))}" if a else ""))
            if a:
                runs = d["before"].keys() & d["after"].keys()
                if runs:
                    b += sum(right(d["after"][i], a) and not right(d["before"][i], a) for i in runs)
                    c += sum(right(d["before"][i], a) and not right(d["after"][i], a) for i in runs)
                    diffs.append(sum(right(d["after"][i], a) for i in runs) / len(runs)
                                 - sum(right(d["before"][i], a) for i in runs) / len(runs))
        say(f"  paired runs where only 'after' was right: {b}; only 'before': {c}; exact McNemar p = {mcnemar(b, c):.4f}")
        min_p = min(1.0, 2 / 2 ** len(diffs))
        say(f"  sign-flip test over {len(diffs)} marked requests: p = {sign_flip(diffs):.4f} "
            f"(smallest possible {min_p:.4f})")


def cmd_report() -> int:
    ans = answers()
    say(f"marks: {len(ans)} requests have an answer ({MARKS})")
    for a in ("claude",):
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
        say(f"  right by what happened next: {wilson_text(k, len(scored))}")
        say(f"  same skill as the original session (the old pass rule): {same}/{len(scored)}")
        for r in scored:
            if not right(r["started"], ans[r["session"]]):
                say(f"    started {r['started']:28} answer {ans[r['session']]:28} {r['request'][:60]!r}")
    report_ab(ans)
    return 0
