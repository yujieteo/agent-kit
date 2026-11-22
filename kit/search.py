"""search: one ranked full-text search over the sessions of both agents.

adobe/pi-session-search reads only pi's own JSONL (~/.pi/agent/sessions, one
folder level) and matches a regex or substring with no ranking. Here the
same idea covers every store, ranked with SQLite FTS5 BM25:

  Claude Code  $CLAUDE_CONFIG_DIR/projects/*/*.jsonl and */subagents/*.jsonl
  Codex        $CODEX_HOME/sessions/**/rollout-*.jsonl, archived_sessions/
  Codex store  $CODEX_HOME/thread_history_1.sqlite (thread_items); on
               2026-11-22, 71 of its 160 threads had no rollout file
  pi           $PI_CODING_AGENT_DIR/sessions/**/*.jsonl

The text of a row is what a person or an agent wrote: user and assistant
text, and the input of each tool call (a Write's content, a command).
Tool results are left out: they are mostly file reads, and a session that
only read a memory file did not make it.

Live SQLite files are copied with their -wal and -shm first, and the copy is
opened, so the write-ahead log is read and the app's file is never locked.

A session's score is the BM25 score of its best row.

search-proof. The rule, fixed before the first run on 2026-11-22: for each
memory file with originSessionId, the query is the file's description and
body (front matter dropped, so not the session id). It passes when the
origin session ranks in the top 5 of all sessions; sessions named in
--exclude (this session and its subagents) are left out. A file whose origin
log is gone is listed apart as "cannot test". The proof passes when every
testable file passes.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import tempfile
from collections import Counter
from pathlib import Path

from .common import HOME, claude_dir, codex_dir, say

CACHE = Path(os.environ.get("XDG_CACHE_HOME") or HOME / ".cache") / "agent-kit"
DB = CACHE / "sessions.db"
TOPK = 5
STOP = set("""a about above after again against all am an and any are as at be because been before
being below between both but by can did do does doing down during each few for from further had has
have having he her here hers him his how i if in into is it its itself just me more most my no nor not
now of off on once only or other our out over own same she should so some such than that the their
them then there these they this those through to too under until up very was we were what when where
which while who whom why will with you your yours one also each the via per use used""".split())


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


def codex_rollout_rows():
    files = list((codex_dir() / "sessions").rglob("*.jsonl")) + list((codex_dir() / "archived_sessions").glob("*.jsonl"))
    for f in files:
        sid, cwd = f.stem, ""
        for line in f.open(errors="replace"):
            try:
                d = json.loads(line)
            except ValueError:
                continue
            p = d.get("payload") or {}
            if d.get("type") == "session_meta":
                sid, cwd = p.get("id", sid), p.get("cwd", "")
                continue
            if d.get("type") != "response_item":
                continue
            t, role = "", p.get("role", "tool")
            if p.get("type") == "message" and role in ("user", "assistant"):
                t = text_of(p.get("content"))
            elif p.get("type") in ("function_call", "custom_tool_call"):
                t = f"[{p.get('name')}] " + str(p.get("arguments") or p.get("input") or "")
            if t.strip():
                yield sid, "codex", cwd, d.get("timestamp", ""), role, t


def copy_sqlite(src: Path, dest: Path) -> Path:
    for suffix in ("", "-wal", "-shm"):
        s = Path(str(src) + suffix)
        if s.exists():
            shutil.copy2(s, dest / (src.name + suffix))
    return dest / src.name


def codex_store_rows(tmp: Path):
    src = codex_dir() / "thread_history_1.sqlite"
    if not src.exists():
        return
    db = sqlite3.connect(copy_sqlite(src, tmp))
    for tid, ms, typ, js in db.execute(
            "select thread_id, created_at_ms, item_type, item_json from thread_items "
            "where item_type in ('userMessage','agentMessage','fileChange','commandExecution','mcpToolCall')"):
        d = json.loads(js)
        if typ == "userMessage":
            t = text_of(d.get("content"))
        elif typ == "agentMessage":
            t = d.get("text", "")
        elif typ == "fileChange":
            t = "\n".join(c.get("path", "") + "\n" + (c.get("diff") or "") for c in d.get("changes", []))
        elif typ == "commandExecution":
            t = d.get("command", "")
        else:
            t = json.dumps(d.get("arguments", ""), ensure_ascii=False)
        if t.strip():
            yield tid, "codex-store", "", str(ms), typ, t
    db.close()


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
    with tempfile.TemporaryDirectory(prefix="agent-kit-index-") as t:
        for src in (claude_rows(), codex_rollout_rows(), codex_store_rows(Path(t)), pi_rows()):
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
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2 and w not in STOP and not w.isdigit() or (w.isdigit() and len(w) >= 3)]


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


def rank(db: sqlite3.Connection, text: str, exclude: set[str] = frozenset(), limit: int = 20):
    q = make_query(db, text)
    if not q:
        return []
    best: dict[str, tuple[float, str, str]] = {}
    for sid, kind, place, score in db.execute(
            "select sid, kind, place, bm25(rows) from rows where rows match ? order by bm25(rows) limit 3000", (q,)):
        if sid in exclude:
            continue
        if sid not in best or score < best[sid][0]:
            best[sid] = (score, kind, place)
    return sorted(((s, sid, k, p) for sid, (s, k, p) in best.items()))[:limit]


def memory_records() -> list[tuple[Path, str, str]]:
    out = []
    for f in sorted((claude_dir() / "projects").glob("*/memory/*.md")):
        raw = f.read_text(errors="replace")
        m = re.search(r"^\s*originSessionId:\s*([\w-]+)", raw, re.M)
        if not m or not raw.startswith("---\n"):
            continue
        front, body = raw[4:].split("\n---\n", 1)
        desc = (re.search(r"^description:\s*(.*)$", front, re.M) or [None, ""])[1]
        out.append((f, m.group(1), desc.strip("\"' ") + "\n" + body))
    return out


def cmd_search(cmd: str, args: list[str]) -> int:
    exclude = set()
    if "--exclude" in args:
        exclude = set(args[args.index("--exclude") + 1].split(","))
    if cmd == "index" or "--reindex" in args or not DB.exists():
        n = build_index()
        say(f"indexed {sum(n.values())} rows: " + ", ".join(f"{k} {v}" for k, v in sorted(n.items())))
        if cmd == "index":
            return 0
    db = sqlite3.connect(DB)
    if cmd == "search":
        q = " ".join(a for a in args if not a.startswith("--") and a not in exclude)
        for s, sid, k, p in rank(db, q, exclude):
            say(f"{s:9.2f}  {k:15} {sid}  {p}")
        return 0
    have = {r[0] for r in db.execute("select distinct sid from rows")}
    passed = failed = 0
    gone = []
    as_json = "--json" in args
    results = []
    for f, origin, text in memory_records():
        name = f"{f.parent.parent.name}/{f.name}"
        if origin not in have:
            gone.append(name)
            results.append({"file": name, "origin": origin, "rank": None})
            continue
        ranked = [sid for _, sid, _, _ in rank(db, text, exclude, limit=200)]
        r = ranked.index(origin) + 1 if origin in ranked else None
        ok = r is not None and r <= TOPK
        passed += ok
        failed += not ok
        results.append({"file": name, "origin": origin, "rank": r, "top": ranked[:5]})
        if not as_json:
            say(f"{'ok  ' if ok else 'FAIL'} rank {r if r else '>200':>4}  {name}")
    for g in gone:
        if not as_json:
            say(f"cannot test (origin log gone)  {g}")
    if as_json:
        print(json.dumps(results, indent=1))
    say(f"search-proof: {'PASS' if failed == 0 and passed else 'FAIL'} ({passed} pass, {failed} fail, "
        f"{len(gone)} cannot test; pass = origin in top {TOPK})")
    return 0 if failed == 0 and passed else 1
