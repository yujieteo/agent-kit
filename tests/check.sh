#!/usr/bin/env bash
# tests/check.sh: every check of this repository in one command.
# Reads and writes no live agent folder (~/.config/claude, ~/.agents).
set -u
repo=$(cd "$(dirname "$0")/.." && pwd)
cd "$repo" || exit 1
export PYTHONDONTWRITEBYTECODE=1
fail=0
part() { # part LABEL CMD...
  label=$1; shift
  echo "== $label"
  if "$@"; then echo "== $label: pass"; else echo "== $label: FAIL"; fail=1; fi
}

part "tests/install.sh" env -u XDG_CONFIG_HOME -u XDG_DATA_HOME -u XDG_STATE_HOME -u CLAUDE_CONFIG_DIR bash tests/install.sh
part "tests/checks.sh" bash tests/checks.sh
part "tests/video.sh" bash tests/video.sh
part "shellcheck" shellcheck -S warning tests/*.sh
[ $fail = 0 ] && echo "all checks: pass" || echo "all checks: FAIL"
exit $fail
