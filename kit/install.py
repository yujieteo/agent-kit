"""install and verify: sync skills/ into ~/.agents/skills and check by SHA-256."""

from __future__ import annotations

import shutil
from pathlib import Path

from .common import HOME, REPO, repo_skills, roots, say, sha256


def _ignore(_dir: str, names: list[str]) -> set[str]:
    return {n for n in names if n in (".DS_Store", "__pycache__") or n.endswith(".pyc")}


def _tree_files(root: Path, base: Path) -> dict[str, Path]:
    out: dict[str, Path] = {}
    for s in repo_skills():
        d = base / s
        if d.is_dir():
            for f in sorted(d.rglob("*")):
                if f.is_file() and f.name != ".DS_Store" and "__pycache__" not in f.parts and f.suffix != ".pyc":
                    out[f"{f.relative_to(root)}"] = f
        else:
            out[f"skills/{s}/SKILL.md"] = d / "SKILL.md"
    return out


def source_files() -> dict[str, Path]:
    return _tree_files(REPO, REPO / "skills")


def installed_files(home: Path | None = None) -> dict[str, Path]:
    agents = roots(home)["agents"]
    return _tree_files(agents, agents / "skills")


def cmd_install(_force: bool = False) -> int:
    dst_root = roots(HOME)["agents"] / "skills"
    dst_root.mkdir(parents=True, exist_ok=True)
    for s in repo_skills():
        src = REPO / "skills" / s
        dst = dst_root / s
        if dst.exists() or dst.is_symlink():
            if dst.is_dir() and not dst.is_symlink():
                shutil.rmtree(dst)
            else:
                dst.unlink()
        shutil.copytree(src, dst, ignore=_ignore)
    return cmd_verify()


def cmd_verify() -> int:
    want = source_files()
    live = installed_files(HOME)
    bad: list[str] = []
    for k in sorted(set(want) | set(live)):
        sp = want.get(k)
        lp = live.get(k)
        if sp is None:
            bad.append(f"{k}: extra installed file not in repo ({lp})")
        elif lp is None or not lp.exists():
            bad.append(f"{k}: missing in {roots(HOME)['agents']}")
        elif sha256(lp) != sha256(sp):
            bad.append(f"{k}: {sha256(lp)} != repo {sha256(sp)}")
    for b in bad:
        say("FAIL " + b)
    say(f"verify: {'FAIL' if bad else 'PASS'} ({len(want)} files)")
    return 1 if bad else 0
