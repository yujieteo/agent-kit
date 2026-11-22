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

Times: the Codex store keeps milliseconds; they are turned into the same ISO
text as the other stores, so `ts < T` means "written before T" for every row.

search-proof tests the search on real searches from the logs, in three steps
whose order is the proof:

  search-proof cases [--until T] [--exclude IDS] [--cut T]
      Finds each moment when a person or agent looked for earlier work (a user
      request, a grep or rg over the log folders, a T3 thread search), and the
      session then opened or quoted (find_cases). The query is what the searcher
      typed. Writes results/search/older.jsonl and newer.jsonl (split at --cut)
      and funnel.json (how many candidates each rule dropped).
  search-proof choose
      Scores the ranking rules in RULES on the older cases only, picks the best
      mean reciprocal rank (a tie keeps "merged", the old rule), and writes the
      choice, the cut and the SHA-256 of both case files to freeze.json.
  search-proof score [--pi CHECKOUT]
      Refuses if the case files changed since freeze.json, or if the newer cases
      were scored before. Scores the chosen rule, the old merged ranking, one
      ranked query, ripgrep and (with a pi-session-search checkout and node on
      PATH) pi-session-search, on the same cases, each seeing only what was
      written before the case and never the searching session.

Each case sees only rows older than itself (word frequencies for picking the
rarest query words still come from the whole index; inferred to matter little).

History, 2026-11-22. The old proof used memory files as queries and their
origin session as the answer: 38 of 38 in the top 5 with the merged ranking,
34 of 35 with one ranked query (measured in the session that made it). That
text is often copied word for word into its origin session, so it was replaced.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
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


def iso_ms(ms) -> str:
    """Milliseconds since 1970 as the ISO text the other stores use (UTC)."""
    import datetime
    return datetime.datetime.fromtimestamp(int(ms) / 1000, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


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
            yield tid, "codex-store", "", iso_ms(ms), typ, t
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


def rank(db: sqlite3.Connection, text: str, exclude: set[str] = frozenset(), limit: int = 20,
         before: str = "9999", best: int = 1, terms: int = 40):
    """Sessions by the BM25 score of their best row (or the sum of their best `best` rows).

    Only rows written before `before` (ISO time) count, so a test sees what existed then.
    """
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


def rank_merged(db: sqlite3.Connection, parts: list[str], exclude: set[str] = frozenset(), limit: int = 200,
                before: str = "9999"):
    """Rank each part on its own, then merge by reciprocal rank (k = 60)."""
    score: dict[str, float] = {}
    for part in parts:
        for i, (_, sid, _, _) in enumerate(rank(db, part, exclude, limit=10_000, before=before)):
            score[sid] = score.get(sid, 0.0) + 1.0 / (60 + i + 1)
    return sorted(score, key=lambda s: -score[s])[:limit]


# ---- search-proof: real searches from the logs ----------------------------------

UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
PREFIX = re.compile(r"(?<![0-9a-f-])([0-9a-f]{8})(?![0-9a-f])")
LOG_PATHS = re.compile(r"(claude/projects|\.claude/projects|codex/sessions|archived_sessions|rollout-|"
                       r"thread_history|\.pi/agent/sessions|state_5\.sqlite)")
SEARCH_TOOL = re.compile(r"""((^|[\s;|&('"`])(rg|grep|egrep|zgrep|ag|ugrep|sqlite3|jq)\s|python3?\b[\s\S]*\bin\s+(l|line|s|t|text)\b)""")
# T3 Code keeps its threads here; a thread read names a T3 thread, not a session.
T3_DB = HOME / ".local/share/t3/userdata/statev2.sqlite"
PROOF = Path(__file__).resolve().parent.parent / "results" / "search"
AGENT_WINDOW, USER_WINDOW = 10, 40  # tool calls after the search in which the open must come


def t3_sessions(tmp: Path) -> dict[str, str]:
    """T3 thread id -> session id: the session whose first request is the thread's first message."""
    if not T3_DB.exists():
        return {}
    db = sqlite3.connect(copy_sqlite(T3_DB, tmp))
    first: dict[str, str] = {}
    for tid, pj in db.execute("select thread_id, payload_json from orchestration_v2_projection_messages "
                              "where role = 'user' order by created_at"):
        t = (json.loads(pj).get("text") or "").strip()
        if t and tid not in first:
            first[tid] = re.sub(r"\s+", " ", t)[:300]
    out = {}
    for tid, rc in db.execute("select thread_id, resume_cursor_json from provider_session_runtime"):
        r = json.loads(rc or "{}").get("resume") if rc else None
        if r:
            out[tid] = r
    db.close()
    starts: dict[str, set[str]] = {}
    for sid, ev in session_events():
        for e in ev:
            if e[1] == "user":
                starts.setdefault(re.sub(r"\s+", " ", e[2].strip())[:300], set()).add(sid)
                break
    for tid, t in first.items():
        if len(starts.get(t, ())) == 1:
            out.setdefault(tid, next(iter(starts[t])))
    return out


def claude_events(f: Path):
    """(time, 'user'|'say'|'result', text) and (time, 'call', name, input), in order."""
    ev = []
    for line in f.open(errors="replace"):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        ts, c = d.get("timestamp", ""), (d.get("message") or {}).get("content")
        if d.get("type") == "user" and not d.get("isMeta"):
            for b in ([{"type": "text", "text": c}] if isinstance(c, str) else c or []):
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "tool_result":
                    r = b.get("content")
                    ev.append((ts, "result", (r if isinstance(r, str) else json.dumps(r))[:20000]))
                elif b.get("type") == "text" and b.get("text", "").strip() and not b["text"].startswith(
                        ("<local-command", "Caveat:", "<task-notification>", "<system-reminder>", "[Request interrupted")):
                    ev.append((ts, "user", b["text"]))
        elif d.get("type") == "assistant":
            for b in c or []:
                if isinstance(b, dict) and b.get("type") == "text":
                    ev.append((ts, "say", b.get("text", "")))
                elif isinstance(b, dict) and b.get("type") == "tool_use":
                    ev.append((ts, "call", b.get("name") or "", b.get("input") or {}))
    return ev


def codex_events(f: Path):
    sid, ev = None, []
    for line in f.open(errors="replace"):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        ts, p = d.get("timestamp", ""), d.get("payload") or {}
        if d.get("type") == "session_meta":
            sid = p.get("id")
        if d.get("type") != "response_item":
            continue
        t = p.get("type")
        if t == "message":
            txt = "\n".join(b.get("text", "") for b in p.get("content") or [] if isinstance(b, dict))
            if p.get("role") == "user" and not txt.lstrip().startswith(
                    ("<environment_context", "# AGENTS.md", "<user_instructions", "<permissions", "<turn_aborted")):
                ev.append((ts, "user", txt))
            elif p.get("role") == "assistant":
                ev.append((ts, "say", txt))
        elif t in ("function_call", "custom_tool_call"):
            a = p.get("arguments") or p.get("input") or ""
            try:
                a = json.loads(a) if isinstance(a, str) and a.startswith("{") else {"command": a}
            except ValueError:
                a = {"command": a}
            ev.append((ts, "call", p.get("name") or "", a))
        elif t in ("function_call_output", "custom_tool_call_output"):
            o = p.get("output")
            ev.append((ts, "result", (o if isinstance(o, str) else json.dumps(o))[:20000]))
    return sid, ev


def store_events(tmp: Path):
    """Threads that live only in the Codex thread store: requests, replies, commands."""
    src = codex_dir() / "thread_history_1.sqlite"
    if not src.exists():
        return
    db = sqlite3.connect(copy_sqlite(src, tmp))
    threads: dict[str, list] = {}
    for tid, ms, typ, js in db.execute("select thread_id, created_at_ms, item_type, item_json from thread_items "
                                       "order by thread_id, rollout_ordinal"):
        d, ts = json.loads(js), iso_ms(ms)
        e = threads.setdefault(tid, [])
        if typ == "userMessage":
            e.append((ts, "user", text_of(d.get("content"))))
        elif typ == "agentMessage":
            e.append((ts, "say", d.get("text", "")))
        elif typ == "commandExecution":
            e.append((ts, "call", "exec", {"command": d.get("command", "")}))
            e.append((ts, "result", str(d.get("aggregatedOutput") or "")[:20000]))
    db.close()
    yield from threads.items()


def session_events():
    """(searching session, events) for every Claude session, subagent, Codex rollout and store thread."""
    seen = set()
    for f in (claude_dir() / "projects").glob("*/*.jsonl"):
        seen.add(f.stem)
        yield f.stem, claude_events(f)
    for f in (claude_dir() / "projects").glob("*/*/subagents/*.jsonl"):
        yield f.parent.parent.name, claude_events(f)  # a subagent searches for its parent
    for f in list((codex_dir() / "sessions").rglob("*.jsonl")) + list((codex_dir() / "archived_sessions").glob("*.jsonl")):
        sid, ev = codex_events(f)
        if sid and sid not in seen:
            seen.add(sid)
            yield sid, ev
    with tempfile.TemporaryDirectory(prefix="agent-kit-proof-") as t:
        for tid, ev in store_events(Path(t)):
            if tid not in seen:
                yield tid, ev


def call_text(e) -> str:
    a = e[3]
    cmd = a.get("command") or a.get("cmd") if isinstance(a, dict) else None
    if isinstance(cmd, list):
        cmd = " ".join(map(str, cmd))
    return cmd or json.dumps(a, ensure_ascii=False)


def is_log_search(e) -> bool:
    if e[1] != "call":
        return False
    if e[2] == "Grep":
        return bool(LOG_PATHS.search(json.dumps(e[3])))
    s = call_text(e)
    return bool(LOG_PATHS.search(s) and SEARCH_TOOL.search(s) and "/memory/" not in s)


def search_words(e) -> list[str]:
    """What the searcher typed: the patterns of a grep, rg or Grep call."""
    if e[2] == "Grep":
        return [e[3].get("pattern", "")]
    s = call_text(e)
    pats = [a or b for a, b in re.findall(r"(?:-e|--regexp)\s+(?:'([^']+)'|\"([^\"]+)\")", s)]
    if not pats:
        m = re.search(r"\b(?:rg|grep|egrep|ag)\b(?:\s+-[-\w=]+)*\s+(?:'([^']+)'|\"([^\"]+)\")", s)
        pats = [m.group(1) or m.group(2)] if m else []
    if any("$" in p for p in pats):  # for p in "a" "b"; do grep "$p" ...
        m = re.search(r"\bfor\s+\w+\s+in\s+((?:\"[^\"]+\"\s*)+);", s)
        pats = re.findall(r"\"([^\"]+)\"", m.group(1)) if m else []
    return [x for p in pats for x in re.split(r"\\\||\|", p) if x.strip()]


class Names:
    """Known session ids named in a text: a full id, or an 8-character prefix that fits one session."""

    def __init__(self, known: set[str], t3: dict[str, str]):
        self.known, self.t3 = known, t3
        self.prefix: dict[str, set[str]] = {}
        for s in known:
            if UUID.fullmatch(s):
                self.prefix.setdefault(s[:8], set()).add(s)

    def __call__(self, text: str, me: str, as_log: bool = False) -> list[str]:
        """With as_log, only ids that point at a session log: in a log folder path, or
        followed by .jsonl or a * glob (a scratch folder named after a session is not its log)."""
        def ok(m):
            return not as_log or LOG_PATHS.search(text[max(0, m.start() - 200):m.start()]) or \
                re.match(r"[\w-]*(\.jsonl|\*)", text[m.end():m.end() + 40])
        out = [m.group(0) for m in UUID.finditer(text) if m.group(0) in self.known and ok(m)]
        out += [next(iter(self.prefix[m.group(1)])) for m in PREFIX.finditer(text)
                if len(self.prefix.get(m.group(1), ())) == 1 and ok(m)]
        return [u for u in dict.fromkeys(out) if u != me]

    def opened(self, e, me: str) -> list[str]:
        if e[1] == "call" and e[2].endswith("t3_thread_read"):
            s = self.t3.get(str(e[3].get("threadId", "")))
            return [s] if s and s != me and s in self.known else []
        if e[1] == "call":
            return self(json.dumps(e[3], ensure_ascii=False), me, as_log=True)
        return self(e[2], me) if e[1] == "say" else []


def find_cases(db: sqlite3.Connection, until: str, exclude: set[str]):
    """Moments when a person or agent looked for earlier work, and the session then opened.

    A trigger is a user request, a search of the log folders (grep, rg, Grep, sqlite3 ...),
    or a T3 thread search. The answer is the first session opened (by path, by id or by a
    T3 thread read) or quoted after it, within 10 tool calls (40 after a user request,
    before the next request), that was not named anywhere before the trigger. The step that
    opens it must name exactly one session; a loop over several sessions is a scan, not a
    pick, and is dropped. Nothing is dropped for having opened the "wrong" session.
    """
    known = {r[0] for r in db.execute("select distinct sid from rows")}
    with tempfile.TemporaryDirectory(prefix="agent-kit-t3-") as t:
        names = Names(known, t3_sessions(Path(t)))
    funnel: Counter = Counter()
    cases, seen = [], set()
    for me, ev in session_events():
        if me in exclude:
            continue
        flat = lambda x: x[2] if x[1] != "call" else json.dumps(x[3], ensure_ascii=False)
        named: set[str] = set()
        for i, e in enumerate(ev):
            named.update(names(flat(e), me))
            kind = ("user" if e[1] == "user" else "agent-grep" if is_log_search(e)
                    else "agent-t3" if e[1] == "call" and e[2].endswith("t3_thread_search") else None)
            if not kind or not e[0] or e[0] >= until:
                continue
            funnel[kind, "1 triggers"] += 1
            calls, j = 0, None
            for k in range(i + 1, len(ev)):
                x = ev[k]
                if x[1] == "user":
                    break
                calls += x[1] == "call"
                if calls > (USER_WINDOW if kind == "user" else AGENT_WINDOW):
                    break
                if names.opened(x, me):
                    j = k
                    break
            if j is None:
                continue
            funnel[kind, "2 then opened a session"] += 1
            new = [s for s in names.opened(ev[j], me) if s not in named]
            if not new:
                continue
            funnel[kind, "3 not named before"] += 1
            if len(names.opened(ev[j], me)) != 1:
                funnel[kind, "4 dropped: the step names several sessions"] += 1
                continue
            answer = new[0]
            if kind == "user":
                query = e[2]
            elif kind == "agent-t3":
                query = [str(x[3].get("query", "")) for x in ev[i:j] if x[1] == "call" and x[2].endswith("t3_thread_search")][-1]
            else:  # the search whose result first names the answer, else the trigger
                query = " | ".join(search_words(e))
                for k in range(i, j):
                    if is_log_search(ev[k]) and k + 1 < len(ev) and ev[k + 1][1] == "result" and answer in names(ev[k + 1][2], me):
                        query = " | ".join(search_words(ev[k])) or query
                        break
            if not query.strip() or (me, answer, kind) in seen:
                continue
            seen.add((me, answer, kind))
            funnel[kind, "5 kept"] += 1
            cases.append({"searcher": me, "ts": e[0], "kind": kind, "query": query[:4000], "answer": answer,
                          "opened_by": (call_text(ev[j]) if ev[j][1] == "call" else ev[j][2])[:200]})
    cases.sort(key=lambda c: c["ts"])
    return cases, funnel


# ---- the methods compared ----

def rule_rank(db, rule: str, c: dict, exclude: set[str]) -> list[str]:
    """Our ranking rules, each a list of sessions, best first, from rows older than the case."""
    ex, q, t = exclude | {c["searcher"]}, c["query"], c["ts"]
    if rule == "merged":  # the old proof's rule: first line and the rest ranked apart, merged
        first, _, rest = q.strip().partition("\n")
        return rank_merged(db, [first, rest] if rest.strip() else [q], ex, 10_000, before=t)
    best, terms = {"single": (1, 40), "best3": (3, 40), "terms10": (1, 10)}[rule]
    return [r[1] for r in rank(db, q, ex, 10_000, before=t, best=best, terms=terms)]


def patterns_of(c: dict) -> list[str]:
    """The fixed strings given to ripgrep and pi-session-search: a grep's own patterns,
    else the words of the query (as for the index)."""
    if c["kind"] == "agent-grep":
        return [p.strip() for p in c["query"].split(" | ") if p.strip()]
    return list(dict.fromkeys(words(c["query"])))


def ripgrep_rank(c: dict, exclude: set[str]) -> list[str]:
    """ripgrep as the agents ran it: over the raw log files (tool output too), fixed strings,
    any case. Only lines whose own timestamp is before the case count. ripgrep has no
    ranking; the order used here: sessions by matching lines, then the latest match."""
    pats = patterns_of(c)
    if not pats:
        return []
    cmd = ["rg", "-i", "-F", "--no-line-number", "--with-filename", "--no-messages", "--glob", "*.jsonl"]
    for p in pats:
        cmd += ["-e", p]
    roots = [claude_dir() / "projects", codex_dir() / "sessions", codex_dir() / "archived_sessions"]
    proc = subprocess.Popen(cmd + [str(r) for r in roots if r.exists()], stdout=subprocess.PIPE, text=True, errors="replace")
    count: Counter = Counter()
    last: dict[str, str] = {}
    for line in proc.stdout:
        path, _, row = line.partition(".jsonl:")
        m = re.search(r'"timestamp":\s*"([^"]+)"', row)
        if not m or m.group(1) >= c["ts"]:
            continue
        f = Path(path + ".jsonl")
        sid = f.parent.parent.name if f.parent.name == "subagents" else (UUID.findall(f.name) or [f.stem])[-1]
        if sid in exclude or sid == c["searcher"]:
            continue
        count[sid] += 1
        last[sid] = max(last.get(sid, ""), m.group(1))
    proc.wait()
    return sorted(count, key=lambda s: (-count[s], tuple(-ord(ch) for ch in last[s])))


PI_DRIVER = """
import { searchSessions } from %s;
const cases = JSON.parse(await (await import("node:fs/promises")).readFile(process.argv[2], "utf8"));
const out = [];
for (const c of cases) {
  const r = await searchSessions({ query: c.query, until: c.until, maxResults: 1000 });
  out.push({ hits: r.hits.map(h => [h.sessionId, h.timestamp]), truncated: r.truncated, skipped: r.skippedFiles });
}
console.log(JSON.stringify(out));
"""


def pi_tree(db: sqlite3.Connection, root: Path) -> Path:
    """The index rows as pi session files (one per session), so pi-session-search reads the same text."""
    if (root / ".done").exists():
        return root
    shutil.rmtree(root, ignore_errors=True)
    (root / "--all--").mkdir(parents=True)
    cur, f = None, None
    for sid, ts, role, body in db.execute("select sid, ts, role, body from rows order by sid, ts"):
        if sid != cur:
            if f:
                f.close()
            cur = sid
            name = re.sub(r"[:.]", "-", ts[:23]) + "Z_" + sid + ".jsonl"
            f = (root / "--all--" / name).open("w")
            f.write(json.dumps({"type": "session", "id": sid, "timestamp": ts}) + "\n")
        r = "user" if role in ("user", "userMessage") else "assistant"
        f.write(json.dumps({"type": "message", "timestamp": ts,
                            "message": {"role": r, "content": [{"type": "text", "text": body}]}}) + "\n")
    if f:
        f.close()
    (root / ".done").touch()
    return root


def pi_rank_all(checkout: Path, root: Path, cases: list[dict], exclude: set[str]) -> list[list[str]]:
    """Run the real pi-session-search (its searchSessions, as its tool calls it) on each case.

    Query: its own /regex/i form, the case's fixed strings joined by |. until = the case time
    (it filters by session start). Hits come newest first (its order); a session ranks by its
    first hit. Hits from after the case, and the searching session, are then dropped.
    """
    jobs = [{"query": "/" + "|".join(re.escape(p).replace("/", "\\/") for p in patterns_of(c)) + "/i",
             "until": c["ts"]} for c in cases]
    with tempfile.TemporaryDirectory(prefix="agent-kit-pi-") as t:
        (Path(t) / "jobs.json").write_text(json.dumps(jobs))
        drv = Path(t) / "run.mjs"
        drv.write_text(PI_DRIVER % json.dumps(str(checkout / "index.ts")))
        env = {**os.environ, "PI_SESSION_SEARCH_ROOT": str(root)}
        r = subprocess.run(["node", str(drv), str(Path(t) / "jobs.json")], capture_output=True, text=True, env=env)
        if r.returncode:
            raise SystemExit("pi-session-search failed:\n" + r.stderr[-2000:])
        res = json.loads(r.stdout)
    out = []
    for c, r in zip(cases, res):
        order = []
        for sid, ts in r["hits"]:
            if ts < c["ts"] and sid not in exclude and sid != c["searcher"] and sid not in order:
                order.append(sid)
        out.append(order)
        c["pi_truncated"], c["pi_skipped_files"] = r["truncated"], r["skipped"]
    return out


# ---- scores ----

def scores(cases: list[dict], ranks: list[list[str]]) -> dict:
    """Recall at 5 and mean reciprocal rank, with a 95% range from resampling searching sessions."""
    import random
    per = []
    for c, r in zip(cases, ranks):
        pos = r.index(c["answer"]) + 1 if c["answer"] in r else None
        per.append((c["searcher"], pos))
    def stat(rows):
        if not rows:
            return float("nan"), float("nan")
        return (sum(p is not None and p <= TOPK for _, p in rows) / len(rows),
                sum(1 / p for _, p in rows if p) / len(rows))
    r5, mrr = stat(per)
    groups: dict[str, list] = {}
    for row in per:
        groups.setdefault(row[0], []).append(row)
    keys, rng, boot = list(groups), random.Random(0), []
    for _ in range(10_000):
        boot.append(stat([row for k in rng.choices(keys, k=len(keys)) for row in groups[k]]))
    lo_hi = lambda xs: (sorted(xs)[249], sorted(xs)[9749])
    return {"n": len(per), "sessions": len(keys), "recall5": r5, "mrr": mrr,
            "recall5_range": lo_hi([b[0] for b in boot]), "mrr_range": lo_hi([b[1] for b in boot]),
            "ranks": [p for _, p in per]}


def copied(db: sqlite3.Connection, c: dict) -> bool:
    """The query, or every grep pattern, stands word for word in the answer's rows before the case."""
    text = " ".join(b for (b,) in db.execute("select body from rows where sid = ? and ts < ?", (c["answer"], c["ts"])))
    text = re.sub(r"\s+", " ", text).lower()
    pats = patterns_of(c) if c["kind"] == "agent-grep" else [c["query"]]
    return all(re.sub(r"\s+", " ", p).strip().lower() in text for p in pats)


RULES = ["merged", "single", "best3", "terms10"]  # written before any case was scored; "merged" wins a tie


def cmd_proof(db: sqlite3.Connection, args: list[str]) -> int:
    """search-proof cases | choose | score  (see the README; the order is the proof)."""
    import hashlib
    PROOF.mkdir(parents=True, exist_ok=True)
    opt = lambda k, d=None: args[args.index(k) + 1] if k in args else d
    exclude = set((opt("--exclude") or "").split(",")) - {""}
    step = args[0] if args else "cases"
    cut = opt("--cut", "2026-11-20T00:00:00Z")
    files = {"older": PROOF / "older.jsonl", "newer": PROOF / "newer.jsonl"}
    load = lambda f: [json.loads(l) for l in f.read_text().splitlines()]
    digest = lambda: {k: hashlib.sha256(f.read_bytes()).hexdigest() for k, f in files.items()}
    if step == "cases":
        until = opt("--until", "9999")
        cases, funnel = find_cases(db, until, exclude)
        for c in cases:
            c["copied"] = copied(db, c)
        old = [c for c in cases if c["ts"] < cut]
        for k, part in (("older", old), ("newer", [c for c in cases if c["ts"] >= cut])):
            files[k].write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in part))
        (PROOF / "funnel.json").write_text(json.dumps({" / ".join(k): v for k, v in sorted(funnel.items())}, indent=1))
        for k, v in sorted(funnel.items()):
            say(f"  {k[0]:11} {k[1]:45} {v}")
        say(f"{len(cases)} cases ({len(old)} before {cut}); copied word for word: {sum(c['copied'] for c in cases)}")
        return 0
    if step == "choose":  # older cases only
        cases = load(files["older"])
        res = {r: scores(cases, [rule_rank(db, r, c, exclude) for c in cases]) for r in RULES}
        top = max(res[r]["mrr"] for r in RULES)
        chosen = next(r for r in RULES if res[r]["mrr"] == top)
        freeze = {"chosen": chosen, "cut": cut, "exclude": sorted(exclude), "sha256": digest(),
                  "older": {r: {k: v for k, v in s.items() if k != "ranks"} | {"ranks": s["ranks"]} for r, s in res.items()}}
        (PROOF / "freeze.json").write_text(json.dumps(freeze, indent=1))
        for r in RULES:
            say(f"  {r:8} recall@5 {res[r]['recall5']:.2f}  MRR {res[r]['mrr']:.2f}  ranks {res[r]['ranks']}")
        say(f"chosen on the {len(cases)} older cases: {chosen}; frozen in {PROOF / 'freeze.json'}")
        return 0
    if step == "score":  # newer cases, once
        freeze = json.loads((PROOF / "freeze.json").read_text())
        if freeze["sha256"] != digest():
            raise SystemExit("search-proof: the case files changed after the rule was chosen")
        if (PROOF / "scores.json").exists() and "--again" not in args:
            raise SystemExit("search-proof: the newer cases were already scored once (scores.json)")
        exclude = set(freeze["exclude"])
        out = {}
        for part in ("newer", "older"):
            cases = load(files[part])
            ranks = {"chosen: " + freeze["chosen"]: [rule_rank(db, freeze["chosen"], c, exclude) for c in cases],
                     "merged (old proof)": [rule_rank(db, "merged", c, exclude) for c in cases],
                     "one ranked query": [rule_rank(db, "single", c, exclude) for c in cases],
                     "ripgrep": [ripgrep_rank(c, exclude) for c in cases]}
            if opt("--pi"):
                ranks["pi-session-search"] = pi_rank_all(Path(opt("--pi")), pi_tree(db, CACHE / "proof-pi"), cases, exclude)
            out[part] = {m: scores(cases, r) for m, r in ranks.items()}
            say(f"\n{part} cases: {len(cases)} from {len({c['searcher'] for c in cases})} searching sessions")
            for m, s in out[part].items():
                say(f"  {m:22} recall@5 {s['recall5']:.2f} {fmt(s['recall5_range'])}  "
                    f"MRR {s['mrr']:.2f} {fmt(s['mrr_range'])}  ranks {s['ranks']}")
        (PROOF / "scores.json").write_text(json.dumps(out, indent=1))
        return 0
    raise SystemExit("search-proof cases|choose|score")


def fmt(r) -> str:
    return f"[{r[0]:.2f}, {r[1]:.2f}]"


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
    return cmd_proof(db, [a for a in args if a != "--reindex"])
