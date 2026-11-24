#!/usr/bin/env bash
# tests/checks.sh: the stale check and the overlap check, clean and with a
# planted fault each. Exit 0 only when each clean run passes and each fault fails.
set -u
repo=$(cd "$(dirname "$0")/.." && pwd)
t=$(mktemp -d "${TMPDIR:-/tmp}/agent-kit-checks.XXXX")
trap 'rm -rf "$t"' EXIT
fail=0
expect() { # expect WANT_RC LABEL DIR CMD...
  want=$1 label=$2 dir=$3; shift 3
  out=$(cd "$dir" && "$@" 2>&1); rc=$?
  if { [ "$want" = 0 ] && [ $rc = 0 ]; } || { [ "$want" != 0 ] && [ $rc != 0 ]; }; then
    echo "ok   $label (exit $rc)"
  else
    echo "BAD  $label (exit $rc)"; fail=1
  fi
  echo "$out" | grep -E '^FAIL' | head -3 | sed 's/^/       /'
}
fresh() { rm -rf "$t/r"; cp -R "$repo" "$t/r"; rm -rf "$t/r/.git"; }
# The stale check runs in a scratch home, so it reads no live agent folder and
# asks GitHub nothing (no rule names a branch). The ~/ paths that the clean
# rules name are made there first, so a clean run passes on any machine. The
# cost: this test does not show that those paths exist in the real home.
sh_home=$t/home
stale() { HOME="$sh_home" CLAUDE_CONFIG_DIR="$t/cfg" CODEX_HOME="$t/codex" python3 -m kit stale "$@"; }

fresh
(cd "$t/r" && HOME="$sh_home" python3 -c '
import os
from pathlib import Path
from kit import stale
home = Path(os.environ["HOME"])
for f in stale.rule_files():
    for p in stale.PATH_RE.findall(f.read_text(errors="replace")):
        d = stale.expand(p)
        if not stale.placeholder(p) and d.is_relative_to(home):  # never outside the scratch home
            d.mkdir(parents=True, exist_ok=True)')
expect 0 "stale: clean" "$t/r" stale
echo 'Keep the notes in `~/src/agent-kit/no-such-notes.md`.' >> "$t/r/.apm/instructions/standing.instructions.md"
expect 1 "stale: planted dead path in the standing rules" "$t/r" stale
fresh
printf '\nRead `references/gone.md` first.\n' >> "$t/r/skills/deeper-task/SKILL.md"
expect 1 "stale: planted dead path in a skill" "$t/r" stale
fresh
printf '\nThen run /no-such-skill on the result.\n' >> "$t/r/skills/deeper-task/SKILL.md"
expect 1 "stale: planted dead skill name" "$t/r" stale

# Memory records are reported, not failed, so these read the report.
memcheck() { # memcheck WANT LABEL SENTENCE: WANT is "report" or "quiet"
  m="$t/cfg/projects/p/memory"; rm -rf "$t/cfg"; mkdir -p "$m"
  printf -- '---\nname: x\ndescription: x\n---\n\n%s\n' "$3" > "$m/x.md"
  out=$(cd "$t/r" && stale --memory 2>&1)
  if echo "$out" | grep -q "path ~/no-such-folder-xyz"; then got=report; else got=quiet; fi
  if [ "$got" = "$1" ]; then echo "ok   $2 ($got)"; else echo "BAD  $2 ($got)"; fail=1; fi
}
fresh
memcheck report "stale --memory: planted dead path in a record" 'The notes are in `~/no-such-folder-xyz/notes.md`.'
memcheck quiet "stale --memory: the same path, called gone" 'The notes were in `~/no-such-folder-xyz/notes.md`, gone since.'

fresh
expect 0 "overlap: clean" "$t/r" python3 -m kit overlap
mkdir "$t/r/skills/task-deepener"
{ echo '---'; echo 'name: task-deepener'; grep -m1 '^description:' "$t/r/skills/deeper-task/SKILL.md"; echo '---'; echo; echo 'Another body.'; } \
  > "$t/r/skills/task-deepener/SKILL.md"
expect 1 "overlap: planted copied description" "$t/r" python3 -m kit overlap
exit $fail
