"""agent-kit COMMAND. Run `agent-kit help` for the list."""

from __future__ import annotations

import sys

USAGE = """agent-kit COMMAND
  install             apm install -g this repo, write Codex AGENTS.md, set the settings keys, verify
  verify              the installed files against hashes.json, apm audit --ci, the settings keys
  lock [--check]      install into an empty home and write (or compare) hashes.json
  inventory [--show]  each entry of both agent folders is in inventory.tsv
  stale [--memory]    names in the rules and skills that do not exist (exit 1);
                      --memory also reports dated memory records that are out of date (exit 0)
  overlap             skill-reach overlap of the skill descriptions, red over the limits
  replay ...          replay past requests in a fresh Claude Code and Codex (see kit/replay.py)
  search QUERY        rank the sessions of both agents for QUERY
  search-proof        each memory file finds the session that made it
"""


def main() -> int:
    a = sys.argv[1:]
    cmd = a[0] if a else "help"
    if cmd == "install":
        from .install import cmd_install
        return cmd_install()
    if cmd == "verify":
        from .install import cmd_verify
        return cmd_verify()
    if cmd == "lock":
        from .install import cmd_lock
        return cmd_lock("--check" in a)
    if cmd == "inventory":
        from .inventory import cmd_inventory
        return cmd_inventory("--show" in a)
    if cmd == "stale":
        from .stale import cmd_stale
        return cmd_stale(a[1:])
    if cmd == "overlap":
        from .overlap import cmd_overlap
        return cmd_overlap(a[1:])
    if cmd == "replay":
        from .replay import cmd_replay
        return cmd_replay(a[1:])
    if cmd in ("search", "search-proof", "index"):
        from .search import cmd_search
        return cmd_search(cmd, a[1:])
    print(USAGE)
    return 0 if cmd in ("help", "-h", "--help") else 2


if __name__ == "__main__":
    sys.exit(main())
