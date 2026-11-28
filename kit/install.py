"""install, lock and verify: the skills the user writes, put in place and hashed.

apm (microsoft/apm) does most of it:
- `apm install -g -t agent-skills <repo>` copies skills/ to ~/.agents/skills;
- `apm audit --ci`, run in $APM_HOME, fails on a file that differs from apm's
  own lock.

What apm does not do, agent-kit does:
- A lock that holds across machines. apm's lock lives in $APM_HOME and
  each machine writes its own, so it only compares a machine with itself.
  hashes.json, in this repository, holds the hash of each installed file,
  keyed by root and relative path. `verify` compares the live files with it.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .common import REPO, HOME, apm_bin, apm_home, repo_skills, roots, run, say, sha256

HASHES = REPO / "hashes.json"


def apm_env(home: Path, apm: Path) -> dict[str, str]:
    env = dict(os.environ)
    env.pop("CLAUDE_CONFIG_DIR", None)
    env.pop("CODEX_HOME", None)
    env.update(HOME=str(home), APM_HOME=str(apm), APM_NON_INTERACTIVE="1")
    return env


def apm_install(env: dict[str, str], source: Path, force: bool = False) -> None:
    # apm adopts a skill copy that was there before the first install without a
    # record that it wrote it, and later refuses to replace it (measured);
    # --force lets it, once.
    r = run([apm_bin(), "install", "-g", "-t", "agent-skills", *(["--force"] if force else []), str(source)],
            env=env, capture_output=True)
    if r.returncode:
        raise SystemExit("apm install failed:\n" + r.stdout + r.stderr)


def owned_files(rts: dict[str, Path]) -> dict[str, Path]:
    """The installed files of this repository, keyed root:relative-path."""
    out: dict[str, Path] = {}
    for s in repo_skills():
        d = rts["agents"] / "skills" / s
        if d.is_dir():
            for f in sorted(d.rglob("*")):
                # Files the system or a skill's own run makes are not the user's.
                if f.is_file() and f.name != ".DS_Store" and "__pycache__" not in f.parts:
                    out[f"agents:{f.relative_to(rts['agents'])}"] = f
        else:
            out[f"agents:skills/{s}/SKILL.md"] = d / "SKILL.md"  # missing: verify says so
    return out


def build_hashes(source: Path = REPO) -> dict:
    """Install into an empty home, and hash what landed."""
    with tempfile.TemporaryDirectory(prefix="agent-kit-lock-") as t:
        home = Path(t)
        apm = home / ".local/share/apm"
        apm_install(apm_env(home, apm), source)
        files = owned_files(roots(home))
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


# ---- install and verify -----------------------------------------------------

def cmd_install(force: bool = False) -> int:
    apm = apm_home()
    apm.mkdir(parents=True, exist_ok=True)
    apm_install(apm_env(HOME, apm), REPO, force)
    return cmd_verify()


def cmd_verify() -> int:
    apm = apm_home()
    bad: list[str] = []
    want = json.loads(HASHES.read_text())["files"]
    live = owned_files(roots(HOME))
    for k in sorted(set(want) | set(live)):
        p = live.get(k)
        got = sha256(p) if p and p.exists() else "absent"
        if k not in want:
            bad.append(f"{k}: a file that hashes.json does not list ({p})")
        elif got != want[k]:
            bad.append(f"{k}: {got} != hashes.json {want[k]}")
    if not apm.is_dir():
        bad.append(f"no apm lock in {apm}: agent-kit is not installed on this machine")
        audit = 1
    else:
        r = run([apm_bin(), "audit", "--ci"], cwd=apm, capture_output=True,
                env=apm_env(HOME, apm))
        audit = r.returncode
        if audit:
            drift = [l.strip() for l in (r.stdout + r.stderr).splitlines() if "hash-drift" in l or "[x]" in l]
            bad.append("apm audit --ci: exit %d: %s" % (audit, "; ".join(drift) or "see apm audit"))
    for b in bad:
        say("FAIL " + b)
    say(f"verify: {'FAIL' if bad else 'PASS'} ({len(want)} files in hashes.json, apm audit exit {audit})")
    return 1 if bad else 0
