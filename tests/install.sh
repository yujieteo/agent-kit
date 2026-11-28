#!/usr/bin/env bash
# tests/install.sh: install into a scratch home, verify, then plant two
# faults. Each must turn verify (or lock --check) red. Exit 0 only when the
# clean run passes and every fault fails.
set -u
repo=$(cd "$(dirname "$0")/.." && pwd)
t=$(mktemp -d "${TMPDIR:-/tmp}/agent-kit-test.XXXX")
trap 'chmod -R u+w "$t"; rm -rf "$t"' EXIT
export HOME=$t/home
export APM_HOME=$t/home/.local/share/apm XDG_CACHE_HOME=$t/home/.cache
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

f=$HOME/.agents/skills/atomic-math-workbooks/SKILL.md
cp "$f" "$t/keep"; echo planted >> "$f"
expect 1 "fault 1: edited skill file (~/.agents)" kit verify
cp "$t/keep" "$f"
expect 0 "back to clean" kit verify

# Fault 2: the repo source edited but hashes.json not rebuilt. Use a copy.
cp -R "$repo" "$t/repo"; rm -rf "$t/repo/.git"
echo planted >> "$t/repo/skills/deeper-task/SKILL.md"
expect 1 "fault 2: edited skill source, hashes.json stale" bash -c "cd '$t/repo' && python3 -m kit lock --check"
exit $fail
