"""stale: check repo-internal references in rules and skills, plus optional --memory audit."""

from __future__ import annotations

import functools
import json
import os
import re
import subprocess
from pathlib import Path

from .common import HOME, REPO, claude_dir, repo_skills, say

OWNER = os.environ.get("AGENT_KIT_GH_OWNER", "yujieteo")


def skill_names() -> set[str]:
    names = set(repo_skills())
    for r in (claude_dir() / "skills", HOME / ".agents/skills", claude_dir() / "plugins"):
        if r.is_dir():
            for f in r.rglob("SKILL.md"):
                if ".trash" in f.parts:
                    continue
                names.add(f.parent.name)
                m = re.search(r"^name:\s*['\"]?([\w:.-]+)", f.read_text(errors="replace")[:500], re.M)
                if m:
                    names.add(m.group(1))
    return names


@functools.cache
def gh_json(*args: str) -> dict | None:
    r = subprocess.run(["gh", *args], capture_output=True, text=True)
    if r.returncode:
        return None
    return json.loads(r.stdout or "null")


@functools.cache
def repo_slug(name: str) -> str | None:
    """A repository name (dotfiles, server) to owner/name on GitHub."""
    local = HOME / "src" / name
    if (local / ".git").exists():
        r = subprocess.run(["git", "-C", str(local), "remote", "get-url", "origin"],
                           capture_output=True, text=True)
        m = re.search(r"github\.com[:/]([^/]+/[^/.\s]+)", r.stdout)
        if m:
            return m.group(1)
    if gh_json("repo", "view", f"{OWNER}/{name}", "--json", "name"):
        return f"{OWNER}/{name}"
    return None


@functools.cache
def branch_exists(slug: str, branch: str) -> bool:
    r = subprocess.run(["git", "ls-remote", "--heads", f"https://github.com/{slug}", branch],
                       capture_output=True, text=True, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    if r.returncode:
        return gh_json("api", f"repos/{slug}/branches/{branch}") is not None
    return bool(r.stdout.strip())


def pr_state(slug: str, n: int) -> str | None:
    d = gh_json("pr", "view", str(n), "-R", slug, "--json", "state")
    return d["state"] if d else None


# ---- reading references ----------------------------------------------------------

PATH_RE = re.compile(r"(?<![\w/.])((?:~|\$HOME|/Users/[\w.-]+)/[\w@%+=:,./-]*[\w/])")
CODE_RE = re.compile(r"`([^`\n]+)`")
MD_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)\s]+)\)")
SKILL_RE = re.compile(r"(?:\bskill `([a-z][\w:-]+)`|`([a-z][\w:-]+)` skill\b)")
BRANCH_RE = re.compile(r"(?:\b([\w-]+) )?branch(?:es)? `([\w./-]+)`|`([\w./-]+)` branch\b", re.I)
PR_RE = re.compile(r"(?:\b([\w-]+) )?PRs? #?(\d+)")
REL_RE = re.compile(r"^(?:\.\./|\./)?(?:references|scripts|assets)/[\w./-]+$")


def expand(p: str) -> Path:
    return Path(os.path.expanduser(p.replace("$HOME", str(HOME))))


def sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.;!?])\s+|\n\s*\n|\n- ", text) if s.strip()]


def strip_front(text: str) -> str:
    return text.split("\n---\n", 1)[1] if text.startswith("---\n") else text


def placeholder(s: str) -> bool:
    return bool(re.search(r"[<>*{}\[\]]|\.\.\.|(?:^|[/_-])[A-Z][A-Z0-9]{2,}(?:$|[/._-])", s))


def check_text(text: str, file_dir: Path, skill_root: Path, skills: set[str]) -> list[str]:
    """Check deterministic repo-internal paths, markdown links, and explicit skill names."""
    bad = []
    for code in set(CODE_RE.findall(text)):
        c = code.strip()
        if REL_RE.match(c) and not placeholder(c) and "." in c.rsplit("/", 1)[-1]:
            if not (skill_root / c).exists() and not (file_dir / c).exists() and not (REPO / c).exists():
                bad.append(f"path {c} does not exist (next to {skill_root.name}/)")
    for target in set(MD_LINK_RE.findall(text)):
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        rel = target.split("#", 1)[0]
        if not rel or placeholder(rel):
            continue
        if not (file_dir / rel).exists() and not (skill_root / rel).exists():
            bad.append(f"link {target} does not exist (next to {file_dir.name}/)")
    for a, b in SKILL_RE.findall(text):
        s = a or b
        if s not in skills:
            bad.append(f"skill {s} does not exist")
    return bad


def rule_files() -> list[Path]:
    files = sorted((REPO / ".apm" / "instructions").glob("*.md"))
    files += sorted(f for f in (REPO / "skills").rglob("*.md"))
    return files


# ---- memory ------------------------------------------------------------------------

PR_DONE = re.compile(r"\b(merged|closed)\b", re.I)
PR_OPEN = re.compile(r"\b(open|opened|draft|waits?|waiting|not merged|ready)\b", re.I)
BRANCH_SKIP = re.compile(r"\b(deleted|gone|removed|merged|not pushed|local branch|locally)\b", re.I)
PATH_SKIP = re.compile(r"\b(on the (desktop|server)|leftovers?|moved|gone|old|trashed|cleared|deleted|removed|dead)\b", re.I)
SLUG_PR_RE = re.compile(r"\b([\w-]+/[\w.-]+)#(\d+)")
REPO_AT_RE = re.compile(r"~/src/([\w.-]+)|github\.com/[\w-]+/([\w.-]+)|\b[\w-]+/([\w.-]+)#\d+|\b" + OWNER + r"/([\w-]+)")


def file_repo(text: str) -> str | None:
    m = REPO_AT_RE.search(text)
    return next((g for g in m.groups() if g), None) if m else None


def repo_before(para: str, pos: int, default: str | None) -> str | None:
    last = None
    for m in REPO_AT_RE.finditer(para[:pos]):
        last = next(g for g in m.groups() if g)
    for m in re.finditer(r"\b([\w-]+) (?:PRs?|branch)\b", para[:pos]):
        if repo_slug(m.group(1)):
            last = m.group(1)
    return last or default


def check_memory(path: Path) -> list[str]:
    raw = path.read_text(errors="replace")
    front = raw.split("\n---\n", 1)[0] if raw.startswith("---\n") else ""
    text = (re.search(r"^description:\s*(.*)$", front, re.M) or [None, ""])[1] + "\n" + strip_front(raw)
    default = file_repo(text)
    out = []
    for para in [p for p in re.split(r"\n\s*\n|\n(?=- )", text) if p.strip()]:
        for sent in sentences(para):
            at = para.find(sent)
            slug_prs = SLUG_PR_RE.findall(sent)
            prs = [(slug, n) for slug, n in slug_prs]
            if not slug_prs:
                for m in PR_RE.finditer(sent):
                    repo, n = m.group(1), m.group(2)
                    name = repo if repo and repo_slug(repo) else repo_before(para, at + m.start(), default)
                    prs.append((repo_slug(name) if name else None, n))
            if PR_OPEN.search(sent) and not PR_DONE.search(sent):
                for slug, n in prs:
                    st = pr_state(slug, int(n)) if slug else None
                    if st in ("MERGED", "CLOSED"):
                        out.append(f"PR {n} ({slug}) is called open, GitHub says {st}: {sent.strip()[:110]!r}")
            if BRANCH_SKIP.search(sent):
                continue
            for m in BRANCH_RE.finditer(sent):
                repo, branch = m.group(1), m.group(2) or m.group(3)
                name = repo if repo and repo_slug(repo) else repo_before(para, at + m.start(), default)
                slug = repo_slug(name) if name else None
                if slug and not branch_exists(slug, branch):
                    out.append(f"branch {branch} is not on GitHub ({slug}): {sent.strip()[:110]!r}")
    live = {p for para in re.split(r"\n\s*\n|\n(?=- )", text) for sent in sentences(para)
            if not PATH_SKIP.search(sent) for p in PATH_RE.findall(sent)}
    for p in sorted(live):
        if not placeholder(p) and not expand(p).exists():
            out.append(f"path {p} does not exist on this machine")
    return out


def memory_files() -> list[Path]:
    return sorted(f for f in (claude_dir() / "projects").glob("*/memory/*.md") if f.name != "MEMORY.md") \
        + sorted((claude_dir() / "projects").glob("*/memory/MEMORY.md"))


def cmd_stale(args: list[str]) -> int:
    skills = skill_names()
    fails = 0
    for f in rule_files():
        skill_root = f.parent if f.parent.name != "references" else f.parent.parent
        for b in check_text(f.read_text(errors="replace"), f.parent, skill_root, skills):
            fails += 1
            say(f"FAIL {f.relative_to(REPO)}: {b}")
    say(f"stale rules and skills: {'FAIL' if fails else 'PASS'} ({len(rule_files())} files, {fails} dead names)")
    if "--memory" in args:
        n = 0
        for f in memory_files():
            for o in check_memory(f):
                n += 1
                say(f"OUT OF DATE {f.parent.parent.name}/memory/{f.name}: {o}")
        say(f"memory: {n} out-of-date records in {len(memory_files())} files (reported, not a failure)")
    return 1 if fails else 0
