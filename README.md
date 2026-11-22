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
agent-kit index | search WORDS | search-proof
```

`nix run github:yujieteo/agent-kit -- install` installs on any machine with
Nix. The flake builds `agent-kit`, `apm` and `skill-reach` (the overlap
check); three Python packages that nixpkgs lacks come from PyPI wheels,
pinned by hash.

If a skill folder was already there before the first install, apm takes it
over without a record that it wrote the files, and a later install refuses
to replace them (measured). Run `agent-kit install --force` once in that case.

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

- **Session search.** `search-proof` looks for the session that wrote each
  memory file. It ranks the file's description and its body separately, and
  merges the two rankings by reciprocal rank. Result: 38 of 38 found in the top 5, 31
  cannot be tested because their session log is gone (measured). One ranking
  of the whole text found 34 of 37 (an earlier run). Taking the last session that wrote the
  file found fewer.
- **Competing skills.** In a replay of 50 past requests, Claude and Codex
  started the same skill as before in 15 of 16 cases each (measured). The two
  video skills competed: for "split this paper into several videos", Codex
  started the narrative skill. Both descriptions now say which one splits a
  text into several videos. The replay before and after the change is in
  results/replay/ on the machine that ran it (not in the repository).
- **Stale memory.** `stale --memory` reported 54 records. After the records
  were corrected and the check skips sentences that call a path old, moved,
  gone or on another machine, 9 are left; all 9 are history the record states
  on purpose (read in the records).

## Tests

`tests/install.sh` installs into a scratch home. It needs a clean pass, and a
fail for each of four planted faults: an edited Claude skill copy, an edited
`~/.agents` copy, an edited Codex AGENTS.md, and an edited source with a
stale hashes.json. `tests/checks.sh` does the same for the stale check (a
dead path in the rules, a dead path in a skill, a dead skill name) and the
overlap check (a copied description). Both pass on 2026-11-22 (measured).
