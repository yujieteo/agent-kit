"""Paths and small helpers that every part of agent-kit uses."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOME = Path(os.environ.get("HOME", str(Path.home())))


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


def apm_bin() -> str:
    exe = os.environ.get("AGENT_KIT_APM") or shutil.which("apm")
    if not exe:
        sys.exit("agent-kit: apm is not on PATH (set AGENT_KIT_APM)")
    return exe


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, text=True, **kw)


def say(msg: str) -> None:
    print(msg, flush=True)
