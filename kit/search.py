"""search: ranked full-text search over Claude Code and pi session logs (SQLite FTS5 BM25)."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from collections import Counter
from pathlib import Path

from .common import HOME, cache_dir, claude_dir, say

CACHE = cache_dir()
DB = CACHE / "sessions.db"
STOP = set("""a about above after again against all am an and any are as at be because been before
being below between both but by can did do does doing down during each few for from further had has
have having he her here hers him his how i if in into is it its itself just me more most my no nor not
now of off on once only or other our out over own same she should so some such than that the their
them then there these they this those through to too under until up very was we were what when where
which while who whom why will with you your yours one also the via per use used""".split())


def text_of(content) -> str:
    if isinstance(content, str):
        return content
    out = []
    for b in content or []:
        if not isinstance(b, dict):
            continue
        t = b.get("type")
        if t in ("text", "input_text", "output_text"):
            out.append(b.get("text", ""))
        elif t == "tool_use":
            out.append(f"[{b.get('name')}] " + json.dumps(b.get("input", {}), ensure_ascii=False))
        elif t == "toolCall":
            out.append(f"[{b.get('name')}] " + json.dumps(b.get("arguments", {}), ensure_ascii=False))
    return "\n".join(x for x in out if x)


def claude_rows():
    for f in (claude_dir() / "projects").glob("*/*.jsonl"):
        yield from claude_file(f, f.stem, "claude")
    for f in (claude_dir() / "projects").glob("*/*/subagents/*.jsonl"):
        yield from claude_file(f, f.parent.parent.name, "claude-subagent")


def claude_file(f: Path, sid: str, kind: str):
    project = f.parts[-2] if kind == "claude" else f.parts[-4]
    for line in f.open(errors="replace"):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("type") not in ("user", "assistant") or d.get("isMeta"):
            continue
        t = text_of((d.get("message") or {}).get("content"))
        if t.strip():
            yield sid, kind, project, d.get("timestamp", ""), d["type"], t


def pi_rows():
    root = Path(os.environ.get("PI_CODING_AGENT_DIR") or HOME / ".pi/agent") / "sessions"
    for f in root.rglob("*.jsonl") if root.is_dir() else []:
        sid = f.stem
        for line in f.open(errors="replace"):
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get("type") == "session":
                sid = d.get("id", sid)
            m = d.get("message") or {}
            if d.get("type") == "message" and m.get("role") in ("user", "assistant"):
                t = text_of(m.get("content"))
                if t.strip():
                    yield sid, "pi", "", d.get("timestamp", ""), m["role"], t


def build_index(path: Path = DB) -> Counter:
    path.parent.mkdir(parents=True, exist_ok=True)
    new = path.with_suffix(".new")
    new.unlink(missing_ok=True)
    db = sqlite3.connect(new)
    db.execute("create virtual table rows using fts5(sid unindexed, kind unindexed, place unindexed, "
               "ts unindexed, role unindexed, body, tokenize='unicode61 remove_diacritics 2')")
    n: Counter = Counter()
    for src in (claude_rows(), pi_rows()):
        batch = []
        for r in src:
            n[r[1]] += 1
            batch.append(r[:5] + (r[5][:200_000],))
            if len(batch) >= 2000:
                db.executemany("insert into rows values (?,?,?,?,?,?)", batch)
                batch = []
        db.executemany("insert into rows values (?,?,?,?,?,?)", batch)
    db.execute("create virtual table vocab using fts5vocab(rows, row)")
    db.commit()
    db.close()
    new.replace(path)
    return n


def words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2 and w not in STOP]


def make_query(db: sqlite3.Connection, text: str, terms: int = 40) -> str:
    """The rarest words of the text (by how many rows hold them), joined by OR."""
    uniq = list(dict.fromkeys(words(text)))
    df = {}
    for w in uniq:
        r = db.execute("select doc from vocab where term = ?", (w,)).fetchone()
        if r:
            df[w] = r[0]
    picked = sorted(df, key=lambda w: df[w])[:terms]
    return " OR ".join(f'"{w}"' for w in picked)


def rank(db: sqlite3.Connection, text: str, exclude: set[str] = frozenset(), limit: int = 20,
         before: str = "9999", best: int = 1, terms: int = 40):
    """Sessions by the BM25 score of their best row (or the sum of their best `best` rows)."""
    q = make_query(db, text, terms)
    if not q:
        return []
    rows: dict[str, list[float]] = {}
    info: dict[str, tuple[str, str]] = {}
    for sid, kind, place, score in db.execute(
            "select sid, kind, place, bm25(rows) from rows where rows match ? and ts < ? "
            "order by bm25(rows) limit 3000", (q, before)):
        if sid in exclude:
            continue
        rows.setdefault(sid, []).append(score)
        info.setdefault(sid, (kind, place))
    scored = [(sum(sorted(v)[:best]), sid, *info[sid]) for sid, v in rows.items()]
    return sorted(scored)[:limit]


def cmd_search(cmd: str, args: list[str]) -> int:
    exclude = set()
    query_words = []
    i = 0
    while i < len(args):
        if args[i] == "--exclude" and i + 1 < len(args):
            exclude.update(x for x in args[i + 1].split(",") if x)
            i += 2
            continue
        if not args[i].startswith("--"):
            query_words.append(args[i])
        i += 1
    if cmd == "index" or "--reindex" in args or not DB.exists():
        n = build_index()
        say(f"indexed {sum(n.values())} rows: " + ", ".join(f"{k} {v}" for k, v in sorted(n.items())))
        if cmd == "index":
            return 0
    db = sqlite3.connect(DB)
    q = " ".join(query_words)
    for s, sid, k, p in rank(db, q, exclude):
        say(f"{s:9.2f}  {k:15} {sid}  {p}")
    return 0
