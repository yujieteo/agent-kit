# agent-kit

What the user teaches coding agents: four skills and the standing instructions.
One command installs the skills into `~/.agents/skills` and verifies them against `skills/` by SHA-256. The staleness, replay, and search commands also inspect Claude Code's config and logs where present.

```sh
agent-kit install              # copy skills/ into ~/.agents/skills, then verify
agent-kit verify               # compare ~/.agents/skills against skills/ by SHA-256
agent-kit stale [--memory]     # check repo-internal links/paths/skills (--memory audits Claude memory)
agent-kit replay cases|--agent claude|report
agent-kit index | search WORDS
```

Run `nix run github:yujieteo/agent-kit -- install` on any machine with Nix, or `python3 -m kit install` inside a clone (pure Python standard library, no third-party packages). Set `AGENT_KIT_REPO=/path/to/clone` when running `replay` via `nix run`.

## Where each thing lives

| What | Source in this repository | Installed to |
|---|---|---|
| Skills (4) | `skills/` | `~/.agents/skills` |

Memory and session logs go to restic through the dotfiles (`users/yj/backup.nix`), not into this repository.

## Tests

Run every check with one command: `bash tests/check.sh`. It needs only `python3` and `shellcheck` and does not touch live agent folders (`~/.config/claude`, `~/.agents`).

- `tests/install.sh` installs into a scratch home, verifies clean install, and checks that edits to either the installed copy or the source fail `verify`.
- `tests/checks.sh` checks repo-internal paths, markdown links, and explicit skill names in `stale`, plus `stale --memory` reporting.
- `tests/video.sh` runs `prepare.py` and `build.py --lint` on a tiny Markdown sample in a scratch folder, confirming a broken formula fails lint.
