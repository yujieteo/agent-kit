"""tests/settings.py: the Claude Code settings merge combines lists, and verify
accepts the user's own extra list items but not a missing declared one.

Run from the repository: python3 tests/settings.py (exit 0 when all pass).
"""
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kit.install import merge_settings, settings_gaps  # noqa: E402

want = {"theme": "dark", "permissions": {"defaultMode": "auto", "deny": ["Read(~/.ssh/**)", "Read(**/.env)"],
                                         "ask": ["Bash(sudo:*)"]}}
have = {"theme": "light", "model": "x",
        "permissions": {"deny": ["Bash(rm -rf:*)", "Read(**/.env)"], "allow": ["Bash(ls:*)"]}}
fail = 0


def check(label, ok):
    global fail
    fail |= not ok
    print(f"{'ok  ' if ok else 'BAD '} {label}")


merged = copy.deepcopy(have)
merge_settings(merged, want)
check("deny keeps the user's rules first and adds the declared ones it lacks, once",
      merged["permissions"]["deny"] == ["Bash(rm -rf:*)", "Read(**/.env)", "Read(~/.ssh/**)"])
check("a list the user did not have is added", merged["permissions"]["ask"] == ["Bash(sudo:*)"])
check("the user's other keys stay", merged["permissions"]["allow"] == ["Bash(ls:*)"] and merged["model"] == "x")
check("declared plain values replace the user's", merged["theme"] == "dark" and merged["permissions"]["defaultMode"] == "auto")
again = copy.deepcopy(merged)
merge_settings(again, want)
check("a second merge changes nothing", again == merged)
merged["permissions"]["ask"].append("Bash(ssh:*)")
check("the merge does not share a list with the declared settings", want["permissions"]["ask"] == ["Bash(sudo:*)"])
check("verify: a merged file with extra user items passes", settings_gaps(merged, want) == [])
check("verify: a declared list item that is missing fails",
      settings_gaps(have, want)[:1] == ["theme is 'light', not 'dark'"]
      and "permissions.deny lacks ['Read(~/.ssh/**)']" in settings_gaps(have, want))
sys.exit(fail)
