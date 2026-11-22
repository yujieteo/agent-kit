"""inventory: each top-level entry of both agent folders must be in inventory.tsv."""

from __future__ import annotations

import fnmatch

from .common import REPO, claude_dir, codex_dir, say


def rows() -> list[dict[str, str]]:
    lines = [l for l in (REPO / "inventory.tsv").read_text().splitlines()
             if l and not l.startswith("#")]
    head = lines[0].split("\t")
    return [dict(zip(head, l.split("\t"))) for l in lines[1:]]


def classify() -> list[tuple[str, str, dict[str, str] | None]]:
    table = rows()
    out = []
    for agent, d in (("claude", claude_dir()), ("codex", codex_dir())):
        for e in sorted(p.name for p in d.iterdir()):
            hit = next((r for r in table if r["agent"] == agent
                        and fnmatch.fnmatchcase(e, r["pattern"])), None)
            out.append((agent, e, hit))
    return out


def cmd_inventory(show: bool) -> int:
    bad = 0
    for agent, e, r in classify():
        if r is None:
            bad += 1
            say(f"FAIL {agent}/{e}: in no row of inventory.tsv")
        elif show:
            say(f"{r['kind']:7} {r['action']:7} {agent}/{e}")
    say(f"inventory: {'FAIL' if bad else 'PASS'} ({bad} unsorted)")
    return 1 if bad else 0
