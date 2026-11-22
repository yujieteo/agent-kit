"""install, lock and verify: the files the user writes, put in place and hashed.

apm (microsoft/apm) does most of it:
- `apm install -g <repo>` copies skills/ to $CLAUDE_CONFIG_DIR/skills and
  ~/.agents/skills, and .apm/instructions to $CLAUDE_CONFIG_DIR/rules;
- `apm audit --ci`, run in $APM_HOME, fails on a file that differs from apm's
  own lock.

What apm does not do, agent-kit does:
- Codex AGENTS.md. `apm compile -g` (0.37.0) looks for instructions only
  directly under apm_modules/, so it never finds those of an installed
  package, and it writes no AGENTS.md.
- A lock that holds across machines. apm's lock lives in $APM_HOME and
  each machine writes its own, so it only compares a machine with itself.
  hashes.json, in this repository, holds the hash of each installed file,
  keyed by root and relative path. `verify` compares the live files with it.
- The keys of each agent's settings that are the user's (agents/*).
"""

from __future__ import annotations

import json
import subprocess
import os
import re
import shutil
import tempfile
import tomllib
from pathlib import Path

from .common import REPO, HOME, apm_bin, apm_home, claude_dir, codex_dir, roots, run, say, sha256

MARK = "<!-- written by agent-kit from .apm/instructions; edit it there -->"
HASHES = REPO / "hashes.json"


def standing_text() -> str:
    """The body of each instruction file, frontmatter dropped, in name order."""
    parts = []
    for f in sorted((REPO / ".apm" / "instructions").glob("*.instructions.md")):
        t = f.read_text()
        if t.startswith("---\n"):
            t = t.split("\n---\n", 1)[1]
        parts.append(t.strip() + "\n")
    return "\n".join(parts)


def agents_md() -> str:
    return MARK + "\n\n" + standing_text()


def write_agents_md(codex: Path) -> None:
    p = codex / "AGENTS.md"
    if p.exists() and p.stat().st_size and not p.read_text().startswith(MARK):
        raise SystemExit(f"agent-kit: {p} was written by hand; move it away first")
    codex.mkdir(parents=True, exist_ok=True)
    p.write_text(agents_md())


def apm_env(home: Path, claude: Path, codex: Path, apm: Path) -> dict[str, str]:
    env = dict(os.environ)
    env.update(HOME=str(home), CLAUDE_CONFIG_DIR=str(claude), CODEX_HOME=str(codex),
               APM_HOME=str(apm), APM_NON_INTERACTIVE="1")
    return env


def apm_install(env: dict[str, str], source: Path) -> None:
    r = run([apm_bin(), "install", "-g", "-t", "claude,codex", str(source)], env=env,
            capture_output=True)
    if r.returncode:
        raise SystemExit("apm install failed:\n" + r.stdout + r.stderr)


def owned_files(rts: dict[str, Path]) -> dict[str, Path]:
    """The installed files of this repository, keyed root:relative-path."""
    out: dict[str, Path] = {}
    skills = sorted(p.name for p in (REPO / "skills").iterdir() if p.is_dir())
    rules = sorted(f.name.removesuffix(".instructions.md") + ".md"
                   for f in (REPO / ".apm" / "instructions").glob("*.instructions.md"))
    for root in ("claude", "agents"):
        for s in skills:
            d = rts[root] / "skills" / s
            if d.is_dir():
                for f in sorted(d.rglob("*")):
                    # Files the system or a skill's own run makes are not the user's.
                    if f.is_file() and f.name != ".DS_Store" and "__pycache__" not in f.parts:
                        out[f"{root}:{f.relative_to(rts[root])}"] = f
            else:
                out[f"{root}:skills/{s}/SKILL.md"] = d / "SKILL.md"  # missing: verify says so
    for r in rules:
        out[f"claude:rules/{r}"] = rts["claude"] / "rules" / r
    out["codex:AGENTS.md"] = rts["codex"] / "AGENTS.md"
    return out


def build_hashes(source: Path = REPO) -> dict:
    """Install into an empty home, and hash what landed."""
    with tempfile.TemporaryDirectory(prefix="agent-kit-lock-") as t:
        home = Path(t)
        claude, codex, apm = home / ".config/claude", home / ".config/codex", home / ".local/share/apm"
        apm_install(apm_env(home, claude, codex, apm), source)
        write_agents_md(codex)
        files = owned_files(roots(home, claude, codex))
        missing = [k for k, p in files.items() if not p.exists()]
        if missing:
            raise SystemExit(f"agent-kit lock: apm did not write {missing}")
        v = run([apm_bin(), "--version"], capture_output=True).stdout.strip().split()[-1]
        return {"apm_version": v, "files": {k: sha256(p) for k, p in files.items()}}


def cmd_lock(check: bool) -> int:
    new = build_hashes()
    if check:
        old = json.loads(HASHES.read_text())
        diff = sorted(k for k in set(old["files"]) | set(new["files"])
                      if old["files"].get(k) != new["files"].get(k))
        for k in diff:
            say(f"FAIL lock: {k} source {new['files'].get(k, 'absent')} != hashes.json {old['files'].get(k, 'absent')}")
        say("lock check: " + ("FAIL" if diff else "PASS") + f" ({len(new['files'])} files)")
        return 1 if diff else 0
    HASHES.write_text(json.dumps(new, indent=1, sort_keys=True) + "\n")
    say(f"wrote {HASHES} ({len(new['files'])} files)")
    return 0


# ---- the settings keys that are the user's ---------------------------------

def flat(d: dict, pre: str = "") -> dict[str, object]:
    out: dict[str, object] = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out.update(flat(v, f"{pre}{k}."))
        else:
            out[pre + k] = v
    return out


def claude_settings_merge(path: Path) -> None:
    want = json.loads((REPO / "agents/claude/settings.json").read_text())
    have = json.loads(path.read_text()) if path.exists() else {}

    def merge(a: dict, b: dict) -> None:
        for k, v in b.items():
            if isinstance(v, dict):
                merge(a.setdefault(k, {}), v)
            else:
                a[k] = v
    merge(have, want)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.agent-kit")
    tmp.write_text(json.dumps(have, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(path)


def toml_value(v: object) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return json.dumps(v)
    return str(v)


def codex_config_merge(path: Path) -> None:
    """Set each declared key, by line, and keep every other line as it is."""
    want = flat(tomllib.loads((REPO / "agents/codex/config.toml").read_text()))
    lines = path.read_text().splitlines() if path.exists() else []
    for key, v in want.items():
        table, _, name = key.rpartition(".")
        line = f"{name} = {toml_value(v)}"
        sec, start, end = "", None, len(lines)
        # find the table's span ("" is the top, before the first header)
        spans: dict[str, tuple[int, int]] = {}
        cur, cur_start = "", 0
        for i, l in enumerate(lines):
            m = re.match(r"^\s*\[([^\[\]]+)\]\s*$", l)
            if m:
                spans.setdefault(cur, (cur_start, i))
                cur, cur_start = m.group(1).strip(), i + 1
        spans.setdefault(cur, (cur_start, len(lines)))
        if table in spans:
            a, b = spans[table]
            for i in range(a, b):
                if re.match(rf"^\s*{re.escape(name)}\s*=", lines[i]):
                    lines[i] = line
                    break
            else:
                lines.insert(a if table == "" else b, line)
        else:
            lines += ["", f"[{table}]", line]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def settings_problems(claude: Path, codex: Path) -> list[str]:
    bad = []
    want = flat(json.loads((REPO / "agents/claude/settings.json").read_text()))
    p = claude / "settings.json"
    have = flat(json.loads(p.read_text())) if p.exists() else {}
    bad += [f"{p}: {k} is {have.get(k)!r}, not {v!r}" for k, v in want.items() if have.get(k) != v]
    want = flat(tomllib.loads((REPO / "agents/codex/config.toml").read_text()))
    p = codex / "config.toml"
    have = flat(tomllib.loads(p.read_text())) if p.exists() else {}
    bad += [f"{p}: {k} is {have.get(k)!r}, not {v!r}" for k, v in want.items() if have.get(k) != v]
    return bad


# ---- install and verify -----------------------------------------------------

def cmd_install() -> int:
    claude, codex, apm = claude_dir(), codex_dir(), apm_home()
    apm.mkdir(parents=True, exist_ok=True)
    apm_install(apm_env(HOME, claude, codex, apm), REPO)
    write_agents_md(codex)
    claude_settings_merge(claude / "settings.json")
    codex_config_merge(codex / "config.toml")
    return cmd_verify()


def cmd_verify() -> int:
    claude, codex, apm = claude_dir(), codex_dir(), apm_home()
    bad: list[str] = []
    want = json.loads(HASHES.read_text())["files"]
    live = owned_files(roots(HOME, claude, codex))
    for k in sorted(set(want) | set(live)):
        p = live.get(k)
        got = sha256(p) if p and p.exists() else "absent"
        if k not in want:
            bad.append(f"{k}: a file that hashes.json does not list ({p})")
        elif got != want[k]:
            bad.append(f"{k}: {got} != hashes.json {want[k]}")
    if not apm.is_dir():
        bad.append(f"no apm lock in {apm}: agent-kit is not installed on this machine")
        r = subprocess.CompletedProcess([], 1, "", "")
    else:
        r = run([apm_bin(), "audit", "--ci"], cwd=apm, capture_output=True,
                env=apm_env(HOME, claude, codex, apm))
    if r.returncode and apm.is_dir():
        drift = [l.strip() for l in (r.stdout + r.stderr).splitlines() if "hash-drift" in l or "[x]" in l]
        bad.append("apm audit --ci: exit %d: %s" % (r.returncode, "; ".join(drift) or "see apm audit"))
    bad += settings_problems(claude, codex)
    for b in bad:
        say("FAIL " + b)
    say(f"verify: {'FAIL' if bad else 'PASS'} ({len(want)} files in hashes.json, apm audit exit {r.returncode})")
    return 1 if bad else 0
