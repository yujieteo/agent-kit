# agent-kit

What the user teaches Claude Code and Codex: four skills, the standing
instructions, and each agent's own settings. One command installs them into
both agents, on any machine, and checks them by SHA-256.

```sh
agent-kit install [--force] # apm install, Codex AGENTS.md, settings merge, then verify
agent-kit verify         # live files against hashes.json, `apm audit --ci`, settings keys
agent-kit lock [--check] # rebuild hashes.json in an empty home (or compare with it)
agent-kit inventory      # sort every file of both config folders (inventory.tsv)
agent-kit stale [--memory]
agent-kit overlap [--installed]
agent-kit replay cases|--agent claude|--agent codex|report
agent-kit index | search WORDS | search-proof cases|choose|score
```

`nix run github:yujieteo/agent-kit -- install` installs on a machine with
Nix. In a fresh NixOS 26.05 virtual machine (x86_64-linux, Nix 2.34.9), as a
normal user with an empty home, `install` ended with exit code 0 in 35
seconds, and `verify` ended with exit code 0 in 1 second. Both printed
`verify: PASS (38 files in hashes.json, apm audit exit 0)`. No `--force` was
needed (measured, 2026-11-22). The first run downloads 264.5 MiB, and apm
also writes `~/.apm-local` (measured). It also runs on one Mac
(aarch64-darwin, measured, but not in a fresh home). aarch64-linux is not
tested. The flake builds `agent-kit`, `apm` and `skill-reach` (the overlap
check); three Python packages that nixpkgs lacks come from PyPI wheels,
pinned by hash.

If a skill folder was already there before the first install, apm takes it
over without a record that it wrote the files, and a later install refuses
to replace them (measured). Run `agent-kit install --force` once in that case.
It passes apm's `--force`, which also deploys despite critical findings of
apm's security scan, so run it only after `agent-kit verify` passes, which
shows the installed copies are the ones in hashes.json.

## Where each thing lives

| What | Source in this repository | Installed to |
|---|---|---|
| Skills (4) | `skills/` | `$CLAUDE_CONFIG_DIR/skills`, `~/.agents/skills` (for Codex) |
| Shared instructions | `.apm/instructions/standing.instructions.md` | `$CLAUDE_CONFIG_DIR/rules/standing.md`, `$CODEX_HOME/AGENTS.md` |
| Claude Code settings | `agents/claude/settings.json` (declared keys) | merged into `$CLAUDE_CONFIG_DIR/settings.json` |
| Codex settings | `agents/codex/config.toml` (declared keys) | merged into `$CODEX_HOME/config.toml` |

`inventory.tsv` sorts every top-level entry of both config folders into
four kinds: written by the user (here), memory (backup), session logs
(backup), and owned by the app (left alone). Memory and logs go to restic
through the dotfiles (`users/yj/backup.nix`), not into this repository.

Sandbox rules are not here. The sandbox-exec profile is dotfiles PR 303;
only Codex's own `sandbox_mode` key is in `agents/codex/config.toml`.

## Upstream projects: what was used and why

- **microsoft/apm 0.37.0** installs the skills and the rules, and its
  `apm audit --ci` catches an edited installed file. It reads
  `CLAUDE_CONFIG_DIR` at user scope (measured). It puts Codex skills only in
  `~/.agents/skills`, not in `$CODEX_HOME/skills` (measured). Codex reads
  both folders (measured: it lists the four from `~/.agents/skills`, and past
  sessions read `$CODEX_HOME/skills/atomic-math-workbooks`). `apm compile -g` never writes Codex's AGENTS.md (read in
  the source: global discovery scans only `apm_modules/`), so agent-kit
  writes it, and hashes it itself. apm fails on a read-only source folder
  (measured), so the Nix wrapper gives it a copy.
- **google/skill-reach** measures overlap (`reach overlap --semantic`). Its
  replay (`reach eval`) cannot be used here. It has no Codex runtime. With
  config isolation on, Claude Code is not signed in. With isolation off, the
  user's other skills end the run as a "residency leak". So `agent-kit
  replay` detects a start the same way (a `Skill` tool call in stream-json)
  and counts every skill.
- **adobe/ai-repo-harness-guide** has its staleness check only as a prompt
  for an agent (read in the source). `agent-kit stale` is that check as a
  script.
- **adobe/pi-session-search** reads only pi's logs, and matches without
  ranking (read in the source; its 47 tests pass, measured). `agent-kit
  search` ranks every store of both agents with SQLite FTS5.

## What the checks found (2026-11-22)

Each claim below says what it rests on: measured (seen in a run or a log),
read in the source, or inferred.

### Session search

**The test.** The old test asked: which session wrote this memory file? The
memory file was often copied from that session, so the test was easy. The
new test uses real searches instead (measured):

1. `search-proof cases` reads the raw logs of both agents and the T3
   thread database. A case is a moment when a person or an agent looked for
   earlier work: a user request, an agent's search of the log files, or a T3
   thread search. The answer is the first other session that the searching
   session then opened or quoted. That session must not be named before the
   search, and the opening step must name only that one session.
2. The cases are split by date, at 2026-11-20. `search-proof choose` tries
   four ranking rules on the older cases only, and writes the winner and the
   SHA-256 of both case files to a file.
3. `search-proof score` scores the newer cases once. It refuses to run if
   the case files changed, and refuses a second run unless told `--again`.

Every method sees only log text written before the search.

| Moment | Candidates | Then opened a session | Not named before | Kept |
|---|---|---|---|---|
| agent searched the logs | 126 | 17 | 9 | 2 |
| agent searched T3 threads | 3 | 3 | 3 | 2 |
| user request | 1,667 | 6 | 5 | 3 |

The 7 cases come from 3 searching sessions. 3 cases are older (1 session)
and 4 are newer (2 sessions). In 2 of the 7, the search text stands word for
word in the answer session; in the old memory test, it was 20 of 38. So the
new test is harder (measured).

**The measures.** "Found in the top 5" is the share of cases in which the
answer is among the first five sessions listed. "Mean reciprocal rank" is the
average of 1 divided by the answer's place in the list: 1 when it is first,
0.5 when it is second, near 0 when it is far down or missing. The range is a
95% range. For "found in the top 5" it is a Wilson range on the count. The
range from resampling sessions is too narrow to trust with 2 sessions, so it
is not given for mean reciprocal rank.

**The result on the 4 newer cases** (measured):

| Method | Found in the top 5 | Mean reciprocal rank | Places of the 4 answers |
|---|---|---|---|
| `agent-kit search`, the rule chosen on the older cases (sum of each session's best 3 rows) | 3 of 4 [0.30, 0.95] | 0.57 | 1, 14, 5, 1 |
| `agent-kit search` as it ships (two rankings merged) | 3 of 4 [0.30, 0.95] | 0.62 | 1, 3, 7, 1 |
| one ranked query | 3 of 4 [0.30, 0.95] | 0.62 | 1, 3, 7, 1 |
| ripgrep over the raw log files | 0 of 4 [0, 0.49] | 0.07 | 112, 7, 15, 13 |
| pi-session-search (commit 5a36613) | 1 of 4 [0.05, 0.70] | 0.25 | missing, 1, missing, missing |

The chosen rule won on the older cases only by places 52 against 63, which
is chance. On the newer cases it is a little worse than the shipped rule. So
the shipped rule stays. With 4 cases, the ranges of all methods overlap, so
this test cannot show that one method is better than another. The FTS5 rules
put 3 of 4 answers in the top 5, ripgrep 0 and pi-session-search 1. On the
older cases, which were not held out, ripgrep did better: 2 of 3 in the top
5, against 1 of 3 for every FTS5 rule (measured). ripgrep lists the sessions
with the most matching lines first, and pi-session-search lists the newest
hits first and stops at 1,000 (read in the source).

**Not tested.** 68 memory files name the session that wrote them, and 31 of
those sessions have no log left. They are untested (measured). The old README
said one ranking found "34 of 37"; the run printed 34 of 35 (measured), which
is now in `kit/search.py`.

### Competing skills

**The answers.** The old test called a replay right when it started the same
skill as the original session. Now an agent read what happened next in each
original session, by a rule written before the replays: the work was kept,
the user corrected the choice, or it is unclear. A kept case's answer is the
skill that started; a corrected case's answer is the skill the user wanted.
Unclear cases are not scored. Of 52 marked rows, 28 were kept, 1 was
corrected, and 23 are unclear; 28 different requests have an answer
(measured).

**The replay of the past requests** (measured, one run each):

| | Right | 95% range |
|---|---|---|
| Claude Code | 15 of 27 | [0.37, 0.72] |
| Codex | 13 of 26 | [0.32, 0.68] |

Codex has one case fewer: that request timed out twice, after about 240 seconds,
before Codex started a skill, so it has no result. Its answer is "no skill"
(measured).

This is lower than the old "15 of 16" for each agent, for two causes
(measured). First, 5 misses of each agent are requests that began with the
typed command `/definition-embedded-videos`. The replay sends only the text
after the command, a bare link, so no skill starts. Without those 5, Claude
is right in 15 of 22 and Codex in 13 of 21. Second, one answer is
`video-explainer`, a skill that no longer exists, so no replay can match it.

**The video skills, before and after.** "Before" is both video descriptions
as at commit 54ae930, and "after" is as at 62c5fcb, where the deciding words
come first. Each of the 10 video requests ran 15 times in each condition.
The two runs of one pair ran in the same block, in a drawn order (measured):

| Request | Claude before | Claude after | Codex before | Codex after |
|---|---|---|---|---|
| 3 past requests that name the definition skill | 45 of 45 | 45 of 45 | 44 of 45 | 45 of 45 |
| past: "video explainers for the 3 PDFs" (narrative) | 0 of 15 (none) | 0 of 15 (none) | 15 of 15 | 15 of 15 |
| past: answer `video-explainer` (gone) | 0 of 15 | 0 of 15 | 0 of 15 | 0 of 15 |
| past: split 1512.06410 into several videos (not marked) | definition 15 | definition 15 | narrative 9, definition 5, `sites` 1 | definition 12, `sites` 3 |
| 4 made-up requests (not marked) | as intended, 60 of 60 | as intended, 60 of 60 | 59 of 60 | 59 of 60 |

The paired test on the marked requests finds no difference. Claude has no
pair where only one condition was right, and Codex has one, for "after"
(exact McNemar p = 1.0 for both; measured). The split request was the reason
for the change, but its original session is unclear, so it has no answer.
For it, Codex started the narrative skill in 9 of 15 runs before and in 0 of
15 after (exact McNemar p = 0.004 on "started the narrative skill"; measured).
So the change stops Codex from starting the narrative skill for that
request; whether the definition skill is the right answer is inferred from
the request's words. `sites` is a Codex plugin skill; the request also says
"upload to my site".

**Why Codex cut the description.** Codex 0.170 gives its list of skills a
fixed space: 2% of the model's context window, which is 5,440 tokens for
`gpt-6.2-astra` (read in the source: `codex-rs/ext/skills/src/render.rs:23-29`
and `:169-195`; the window size measured in `models_cache.json`). When the
list does not fit, Codex hands out the space one character at a time to each
skill in turn, so every long description is cut to the same length
(`render.rs:469-506`, read in the source). It adds no marker and shows no
warning; it only writes the log line "fit skills context budget"
(`render_observability.rs:52-66`, read in the source). The real Codex log has
22 such lines from 17 to 21 November, with `budget_limit=5440` (measured).
The request that Codex sent was captured through a local server set as
`openai_base_url` (measured). In the replay's setup, Codex lists 59 skills,
and the narrative description stops after about 372 characters, at "…two or
three cases side by side — w" (measured). That is the same place as the old
quote (measured in that session's log). With the real home's 65 skills, it
stops after about 282 characters (measured). With the old descriptions, the
deciding sentence was cut in every capture; with the new ones, the deciding
words end at character 162 (narrative) and 131 (definition), inside every cut
(measured). Setting `[skills] max_context_tokens = 10000` would stop the cut
(inferred from the source; not tried).

The Codex replays leave out the browser, chrome, computer-use and
unified-computer-use plugins, which hold no skill. While they were on, Chrome
opened and macOS asked for keychain access during the runs (measured); that
the plugins caused it is inferred. The replay's Codex lists 59
skills, not the real 65: the 6 runtime plugin skills are missing under a
scratch home (measured).

### Stale memory

`stale --memory` reported 54 records. After the records were corrected and
the check skips sentences that call a path old, moved, gone or on another
machine, 7 are left; each is history the record states on purpose (read in
the records).

## Tests

`tests/install.sh` installs into a scratch home. It needs a clean pass, and a
fail for each of four planted faults: an edited Claude skill copy, an edited
`~/.agents` copy, an edited Codex AGENTS.md, and an edited source with a
stale hashes.json. `tests/checks.sh` does the same for the stale check (a
dead path in the rules, a dead path in a skill, a dead skill name) and the
overlap check (a copied description). It also checks that `stale --memory`
reports a dead path in a record, and does not report it in a sentence that
calls it gone. Both pass on 2026-11-22 (measured). They need the flake's
apm and skill-reach: set `AGENT_KIT_APM` to `bin/apm` in the output of
`nix build --print-out-paths .#apm`, and `AGENT_KIT_REACH` to `bin/reach` in
the output of `.#skill-reach`.
