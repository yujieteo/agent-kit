#!/usr/bin/env bash
# tests/checks.sh: the stale check, clean and with planted faults.
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
sh_home=$t/home
stale() { HOME="$sh_home" CLAUDE_CONFIG_DIR="$t/cfg" python3 -m kit stale "$@"; }

fresh
expect 0 "stale: clean" "$t/r" stale
printf '\nRead `references/gone.md` first.\n' >> "$t/r/skills/deeper-task/SKILL.md"
expect 1 "stale: planted dead path in a skill" "$t/r" stale
fresh
printf '\nSee [gone](references/missing.md).\n' >> "$t/r/skills/deeper-task/SKILL.md"
expect 1 "stale: planted dead markdown link in a skill" "$t/r" stale
fresh
printf '\nUse the `no-such-skill` skill on the result.\n' >> "$t/r/skills/deeper-task/SKILL.md"
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
exit $fail
