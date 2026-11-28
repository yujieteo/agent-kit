"""agent-kit COMMAND. Run `agent-kit help` for the list."""

from __future__ import annotations

import os
import sys

USAGE = """agent-kit COMMAND
  install [--force]   apm install -g -t agent-skills this repo, then verify
                      (--force replaces skill copies that were there before the first install)
  verify              the installed files against hashes.json and apm audit --ci
  lock [--check]      install into an empty home and write (or compare) hashes.json
  stale [--memory]    names in the rules and skills that do not exist (exit 1);
                      --memory also reports dated memory records that are out of date (exit 0)
  overlap [--installed]  skill-reach overlap of the skill descriptions, red over the limits;
                      --installed also reports them against every installed skill
  replay ...          replay past requests in a fresh Claude Code (see kit/replay.py)
  index               build the session index again (search builds it when it is missing)
  search QUERY        rank the sessions for QUERY
  search-proof cases|choose|score   real past searches from the logs, a rule chosen on
                      the older ones, scored once on the newer ones (see kit/search.py)
"""


# `nix run` without AGENT_KIT_REPO runs from a copy of the repository that has no
# .git, tests or results/ and is deleted on exit (see flake.nix). These commands
# write into the repository or read its history and results, so they stop there.
NEEDS_CLONE = {"lock": "writes hashes.json into the repository", "replay": "reads and writes results/ and git history",
               "search-proof": "reads and writes results/"}


def main() -> int:
    a = sys.argv[1:]
    cmd = a[0] if a else "help"
    if os.environ.get("AGENT_KIT_COPY") and cmd in NEEDS_CLONE and not (cmd == "lock" and "--check" in a):
        print(f"agent-kit {cmd}: this command {NEEDS_CLONE[cmd]}, so it needs a clone. Under nix run, set\n"
              f"AGENT_KIT_REPO to a clone of agent-kit, or run `python3 -m kit {cmd}` in the clone.", file=sys.stderr)
        return 2
    if cmd == "install":
        from .install import cmd_install
        return cmd_install("--force" in a[1:])
    if cmd == "verify":
        from .install import cmd_verify
        return cmd_verify()
    if cmd == "lock":
        from .install import cmd_lock
        return cmd_lock("--check" in a)
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
