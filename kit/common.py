"""Paths and small helpers that every part of agent-kit uses."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOME = Path(os.environ.get("HOME", str(Path.home())))


def repo_skills() -> list[str]:
    """The names of this repository's skills (the folders under skills/), sorted."""
    return sorted(p.name for p in (REPO / "skills").iterdir() if p.is_dir())


# Text in a user turn of a Claude Code log that the user did not type as a request:
# app notices, a /compact or /clear command, and the "Continue" that a resumed
# session sends. kit/replay.py and kit/search.py both skip it.
NOT_REQUESTS = ("<local-command", "<command-name>/compact", "<command-name>/clear", "Caveat:",
                "[Request interrupted", "<task-notification>", "<system-reminder>")


def not_a_request(text: str) -> bool:
    """True when a Claude Code user turn is app text, not a request the user typed."""
    return text.startswith(NOT_REQUESTS) or text.strip() == "Continue"


def cache_dir() -> Path:
    """agent-kit's cache folder: $XDG_CACHE_HOME/agent-kit, else ~/.cache/agent-kit."""
    return Path(os.environ.get("XDG_CACHE_HOME") or HOME / ".cache") / "agent-kit"


def claude_dir() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or HOME / ".claude")


def codex_dir() -> Path:
    return Path(os.environ.get("CODEX_HOME") or HOME / ".codex")


def apm_home() -> Path:
    # apm's own default is ~/.apm; agent-kit always passes APM_HOME to apm, so
    # the lock lives in the XDG data folder whether or not the shell sets it.
    xdg = Path(os.environ.get("XDG_DATA_HOME") or HOME / ".local/share")
    return Path(os.environ.get("APM_HOME") or xdg / "apm")


def roots(home: Path | None = None, claude: Path | None = None,
          codex: Path | None = None) -> dict[str, Path]:
    """The three folders that the install writes to, by short name.

    claude: $CLAUDE_CONFIG_DIR (apm writes rules/ and skills/ there)
    agents: ~/.agents (apm writes the Codex skills there; Codex reads them)
    codex:  $CODEX_HOME (agent-kit writes AGENTS.md there)
    """
    h = home or HOME
    return {"claude": claude or claude_dir(), "agents": h / ".agents",
            "codex": codex or codex_dir()}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def copy_sqlite(src: Path, dest: Path) -> Path:
    """Copy a live SQLite file with its -wal and -shm into dest; return the copy.

    The copy is what gets opened, so the write-ahead log is read and the app's
    own file is never locked.
    """
    for suffix in ("", "-wal", "-shm"):
        s = Path(str(src) + suffix)
        if s.exists():
            shutil.copy2(s, dest / (src.name + suffix))
    return dest / src.name


def find_tool(name: str, env: str, label: str | None = None) -> str:
    """The program in $env, else name on PATH; stop with a message when neither is there."""
    exe = os.environ.get(env) or shutil.which(name)
    if not exe:
        raise SystemExit(f"agent-kit: {label or name} is not on PATH (set {env})")
    return exe


def apm_bin() -> str:
    return find_tool("apm", "AGENT_KIT_APM")


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, text=True, **kw)


def say(msg: str) -> None:
    print(msg, flush=True)


def wilson(k: int, n: int) -> tuple[float, float]:
    """95% range for a share k/n (Wilson score interval). n == 0 gives (nan, nan)."""
    if n == 0:
        return float("nan"), float("nan")
    z, ph = 1.959964, k / n
    c = (ph + z * z / (2 * n)) / (1 + z * z / n)
    h = z / (1 + z * z / n) * (ph * (1 - ph) / n + z * z / (4 * n * n)) ** 0.5
    return max(0.0, c - h), min(1.0, c + h)


def mcnemar(b: int, c: int) -> float:
    """Exact two-sided McNemar test: b pairs right only after, c right only before."""
    from math import comb
    n = b + c
    return 1.0 if n == 0 else min(1.0, 2 * sum(comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)
