#!/usr/bin/env bash
# tests/video.sh: the definition-embedded-videos scripts on a tiny Markdown
# sample in a scratch folder. prepare.py makes the beats file, then
# build.py --lint checks it against a glossary. No voice, no video.
# A planted formula with no spoken form must fail the lint.
# Exit 0 only when the clean run passes and the fault fails.
set -u
repo=$(cd "$(dirname "$0")/.." && pwd)
scripts=$repo/skills/definition-embedded-videos/scripts
t=$(mktemp -d "${TMPDIR:-/tmp}/agent-kit-video.XXXX")
trap 'rm -rf "$t"' EXIT
export PYTHONDONTWRITEBYTECODE=1
fail=0
expect() { # expect WANT_RC LABEL CMD...
  want=$1 label=$2; shift 2
  out=$("$@" 2>&1); rc=$?
  if { [ "$want" = 0 ] && [ $rc = 0 ]; } || { [ "$want" != 0 ] && [ $rc != 0 ]; }; then
    echo "ok   $label (exit $rc)"
  else
    echo "BAD  $label (exit $rc)"; echo "$out" | tail -5; fail=1
  fi
}

cat > "$t/src.md" <<'EOF'
# A small note

## 1. Points

A rational point is a point with coordinates that are fractions.
The curve $y^2 = x^3 + 1$ has the rational point $(0, 1)$.
EOF
mkdir "$t/work"
cat > "$t/work/glossary.txt" <<'EOF'
rational point; rational points = a point whose two coordinates are fractions
(base) curve = the set of points that solve one equation
EOF
beats=$t/work/01-note.beats
expect 0 "prepare.py: Markdown to beats" python3 "$scripts/prepare.py" "$t/src.md" --out "$beats"
grep -q '^The curve \$y^2 = x^3 + 1\$ has' "$beats" && echo "ok   prepare.py kept the formula as TeX" \
  || { echo "BAD  prepare.py lost the formula"; fail=1; }
expect 0 "build.py --lint: clean" python3 "$scripts/build.py" "$t/work" --lint
# \frac with one argument: the build cannot say it, so lint asks for a spoken form.
# (A formula that only TeX rejects, such as an unbalanced brace, passes plain
# --lint; only --lint --formulas, which runs pdflatex, catches that.)
echo 'Then $\frac{1}$ holds.' >> "$beats"
expect 1 "build.py --lint: planted broken formula" python3 "$scripts/build.py" "$t/work" --lint
exit $fail
