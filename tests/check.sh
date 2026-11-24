#!/usr/bin/env bash
# tests/check.sh: every check of this repository in one command. It builds the
# flake's apm and skill-reach, then runs each test script and shellcheck.
# It never touches the live home: install.sh installs into a scratch home.
# Exit 0 only when every part passes.
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

if ! out=$(nix build --no-link --no-write-lock-file --print-out-paths .#apm .#skill-reach); then
  echo "== nix build: FAIL"; exit 1
fi
apm=$(echo "$out" | grep -- '-apm-cli-') reach=$(echo "$out" | grep -- '-skill-reach-')
export AGENT_KIT_APM=$apm/bin/apm AGENT_KIT_REACH=$reach/bin/reach

# The XDG variables of the shell would point the scratch install at live folders.
part "tests/install.sh" env -u XDG_CONFIG_HOME -u XDG_DATA_HOME -u XDG_STATE_HOME bash tests/install.sh
part "tests/checks.sh" bash tests/checks.sh
part "tests/stats.py" python3 tests/stats.py
part "tests/video.sh" bash tests/video.sh
part "shellcheck" shellcheck -S warning tests/*.sh
[ $fail = 0 ] && echo "all checks: pass" || echo "all checks: FAIL"
exit $fail
