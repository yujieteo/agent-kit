"""overlap: skill-reach (google/skill-reach) on the skill descriptions.

`reach overlap --semantic` gives each skill its nearest rival, a word-match
ratio (BM25 of the rival against the skill's own score) and an embedding
similarity (minishlab/potion-retrieval-32M, run on this machine). skill-reach
itself sorts each pair into a group with two limits (retrieval.py:695-711):
ratio >= 0.5, similarity >= 0.75. This check is red when a pair of the
repository's skills is in any group but Distinct. `reach lint` sees a copied
description too, but it exits 0, so it cannot be the check.

--installed also measures the repository's skills against every other skill
installed for Claude Code and Codex (plugin and app skills), as a report.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from .common import REPO, HOME, claude_dir, codex_dir, find_tool, repo_skills, say

RATIO, SIMILARITY = 0.5, 0.75


def reach() -> str:
    return find_tool("reach", "AGENT_KIT_REACH", "reach (skill-reach)")


def run_overlap(corpus: Path) -> list[dict]:
    r = subprocess.run([reach(), "overlap", "--skills", str(corpus), "--semantic", "--all",
                        "--format", "json"], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit("reach overlap failed:\n" + r.stderr[-2000:])
    return json.loads(r.stdout[r.stdout.index("{"):])["skills"]


def installed_corpus(dest: Path) -> int:
    """Every SKILL.md installed for either agent, one folder per name."""
    seen = set()
    for root in [REPO / "skills", claude_dir() / "skills", claude_dir() / "plugins",
                 HOME / ".agents/skills", codex_dir() / "skills", codex_dir() / "plugins"]:
        for f in sorted(root.rglob("SKILL.md")) if root.is_dir() else []:
            if ".trash" in f.parts:
                continue
            name = f.parent.name
            if name in seen:
                continue
            seen.add(name)
            (dest / name).mkdir()
            shutil.copy(f, dest / name / "SKILL.md")
    return len(seen)


def cmd_overlap(args: list[str]) -> int:
    skills = args[args.index("--skills") + 1] if "--skills" in args else str(REPO / "skills")
    rows = run_overlap(Path(skills))
    bad = 0
    for s in sorted(rows, key=lambda s: -s["rival_ratio"]):
        sim = s.get("semantic_similarity")
        red = s["rival_ratio"] >= RATIO or (sim is not None and sim >= SIMILARITY)
        bad += red
        say(f"{'FAIL' if red else 'ok  '} {s['skill']:30} nearest {s['nearest_rival']:30} "
            f"ratio {s['rival_ratio']:.3f} similarity {sim} ({s.get('quadrant')})")
    say(f"overlap: {'FAIL' if bad else 'PASS'} ({len(rows)} skills, limits ratio {RATIO}, similarity {SIMILARITY})")
    if "--installed" in args:
        with tempfile.TemporaryDirectory(prefix="agent-kit-overlap-") as t:
            n = installed_corpus(Path(t))
            mine = set(repo_skills())
            say(f"\nagainst all {n} installed skills (report):")
            for s in run_overlap(Path(t)):
                if s["skill"] in mine:
                    say(f"     {s['skill']:30} nearest {s['nearest_rival']:30} ratio {s['rival_ratio']:.3f} "
                        f"similarity {s.get('semantic_similarity')} ({s.get('quadrant')})")
    return 1 if bad else 0
