#!/usr/bin/env bash
# tests/install.sh: install into made-up agent folders in a scratch home,
# verify, then plant three faults. Each must turn verify (or lock
# --check) red. Exit 0 only when the clean run passes and every fault fails.
set -u
repo=$(cd "$(dirname "$0")/.." && pwd)
t=$(mktemp -d "${TMPDIR:-/tmp}/agent-kit-test.XXXX")
trap 'chmod -R u+w "$t"; rm -rf "$t"' EXIT
export HOME=$t/home CODEX_HOME=$t/home/.config/codex
export APM_HOME=$t/home/.local/share/apm XDG_CACHE_HOME=$t/home/.cache
mkdir -p "$CODEX_HOME"
: > "$CODEX_HOME/AGENTS.md"
printf 'notify = ["a"]\nmodel = "other"\n\n[desktop]\nx = 1\n' > "$CODEX_HOME/config.toml"
kit() { (cd "$repo" && python3 -m kit "$@") 2>&1; }

fail=0
expect() { # expect WANT_RC LABEL CMD...
  want=$1 label=$2; shift 2
  out=$("$@"); rc=$?
  if { [ "$want" = 0 ] && [ $rc = 0 ]; } || { [ "$want" != 0 ] && [ $rc != 0 ]; }; then
    echo "ok   $label (exit $rc)"
  else
    echo "BAD  $label (exit $rc)"; echo "$out" | tail -5; fail=1
  fi
  echo "$out" | grep -E '^FAIL' | head -3 | sed 's/^/       /'
}

expect 0 "clean install and verify" kit install
grep -q '^notify = \["a"\]' "$CODEX_HOME/config.toml" && grep -q '^model = "gpt' "$CODEX_HOME/config.toml" \
  && echo "ok   config.toml keeps Codex's lines" || { echo "BAD  config merge"; fail=1; }

f=$HOME/.agents/skills/atomic-math-workbooks/SKILL.md
cp "$f" "$t/keep"; echo planted >> "$f"
expect 1 "fault 1: edited skill file, Codex copy (~/.agents)" kit verify
cp "$t/keep" "$f"
echo planted >> "$CODEX_HOME/AGENTS.md"
expect 1 "fault 2: edited Codex AGENTS.md (apm does not see it)" kit verify
(cd "$repo" && python3 -c 'import kit.install as i, pathlib; p=pathlib.Path(i.HOME)/".config/codex/AGENTS.md"; p.write_text(i.agents_md())')
expect 0 "back to clean" kit verify

# Fault 3: the repo source edited but hashes.json not rebuilt. Use a copy.
cp -R "$repo" "$t/repo"; rm -rf "$t/repo/.git"
echo planted >> "$t/repo/skills/deeper-task/SKILL.md"
expect 1 "fault 3: edited skill source, hashes.json stale" bash -c "cd '$t/repo' && python3 -m kit lock --check"
exit $fail
