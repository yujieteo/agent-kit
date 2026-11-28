"""Paths and small helpers that every part of agent-kit uses."""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOME = Path(os.environ.get("HOME", str(Path.home())))


def repo_skills() -> list[str]:
    """The names of this repository's skills (the folders under skills/), sorted."""
    return sorted(p.name for p in (REPO / "skills").iterdir() if p.is_dir())


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


def roots(home: Path | None = None) -> dict[str, Path]:
    """The folder that the install writes to, by short name."""
    h = home or HOME
    return {"agents": h / ".agents"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


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
