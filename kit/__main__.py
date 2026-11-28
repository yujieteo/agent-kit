"""agent-kit COMMAND. Run `agent-kit help` for the list."""

from __future__ import annotations

import os
import sys

USAGE = """agent-kit COMMAND
  install             copy skills/ to ~/.agents/skills, then verify by SHA-256
  verify              compare ~/.agents/skills against this repository's skills/
  stale [--memory]    check repo-internal paths and skill references (exit 1);
                      --memory also reports dated memory records that are out of date (exit 0)
  replay ...          replay past requests in a fresh Claude Code (see kit/replay.py)
  index               build the session index again (search builds it when it is missing)
  search QUERY        rank the sessions for QUERY
"""


def main() -> int:
    a = sys.argv[1:]
    cmd = a[0] if a else "help"
    if os.environ.get("AGENT_KIT_COPY") and cmd == "replay":
        print("agent-kit replay: reads and writes results/ and git history, so it needs a clone.\n"
              "Set AGENT_KIT_REPO to a clone of agent-kit, or run `python3 -m kit replay` in the clone.", file=sys.stderr)
        return 2
    if cmd == "install":
        from .install import cmd_install
        return cmd_install("--force" in a[1:])
    if cmd == "verify":
        from .install import cmd_verify
        return cmd_verify()
    if cmd == "stale":
        from .stale import cmd_stale
        return cmd_stale(a[1:])
    if cmd == "replay":
        from .replay import cmd_replay
        return cmd_replay(a[1:])
    if cmd in ("search", "index"):
        from .search import cmd_search
        return cmd_search(cmd, a[1:])
    print(USAGE)
    return 0 if cmd in ("help", "-h", "--help") else 2


if __name__ == "__main__":
    sys.exit(main())
