#!/usr/bin/env bash
# tests/install.sh: install into a scratch home, verify, then plant two
# faults (edited installed file, and edited repo source). Exit 0 only when
# clean runs pass and faults fail.
set -u
repo=$(cd "$(dirname "$0")/.." && pwd)
t=$(mktemp -d "${TMPDIR:-/tmp}/agent-kit-test.XXXX")
trap 'chmod -R u+w "$t"; rm -rf "$t"' EXIT
export HOME=$t/home
export XDG_CACHE_HOME=$t/home/.cache
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

# Fault 2: repo source edited relative to installed copy.
cp -R "$repo" "$t/repo"; rm -rf "$t/repo/.git"
echo planted >> "$t/repo/skills/deeper-task/SKILL.md"
expect 1 "fault 2: edited skill source differs from installed copy" bash -c "cd '$t/repo' && python3 -m kit verify"
exit $fail
