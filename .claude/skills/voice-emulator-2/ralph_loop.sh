#!/usr/bin/env bash
# Ralph loop for the voice emulator: generate -> audit -> revise, until the
# audit passes or we hit MAX_ITERS. Named after the "just keep running the same
# prompt until it's done" pattern.
#
# The generator is pluggable. In this session it is agent-driven: Claude writes
# each candidate, the loop audits it, Claude reads the findings and revises. You
# can also wire in a live model command with --gen.
#
# Modes:
#   ralph_loop.sh <candidate_file>
#       Audit one file once. Exit 0 if it passes, 1 if not.
#
#   ralph_loop.sh --replay <dir>
#       Replay iteration_*.md in <dir> in order, printing PASS/FAIL for each and
#       stopping at the first PASS. Shows the FAIL -> ... -> PASS run on record.
#
#   ralph_loop.sh --gen "<command>" <candidate_file>
#       Live loop. Each round: run <command> (it must (re)write <candidate_file>),
#       then audit it. Stop at PASS or after MAX_ITERS rounds. <command> receives
#       the question file as $1 and the last audit report as $2 so a model can act
#       on the findings.
#
# Env:
#   MAX_ITERS   rounds before giving up in --gen mode (default 8)
#   QUESTION    question file passed to the generator (default tests/finance_law_question.md)

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUDIT="python3 $HERE/audit.py"
MAX_ITERS="${MAX_ITERS:-8}"
QUESTION="${QUESTION:-$HERE/tests/finance_law_question.md}"

banner() { printf '\n########## %s ##########\n' "$1"; }

replay() {
  local dir="$1"
  local n=0 passed=""
  for f in "$dir"/iteration_*.md; do
    [ -e "$f" ] || { echo "no iteration_*.md in $dir"; exit 2; }
    n=$((n + 1))
    banner "ROUND $n: $(basename "$f")"
    if $AUDIT "$f"; then
      passed="$f"
      echo ">> PASS on $(basename "$f") after $n round(s)."
      break
    else
      echo ">> FAIL; revise and try the next candidate."
    fi
  done
  if [ -n "$passed" ]; then
    echo
    echo "Ralph loop converged: $(basename "$passed")"
    exit 0
  fi
  echo "Ralph loop did not converge in $n round(s)."
  exit 1
}

live() {
  local gen="$1" candidate="$2"
  local report
  report="$(mktemp)"
  : > "$report"
  for i in $(seq 1 "$MAX_ITERS"); do
    banner "ROUND $i"
    # The generator rewrites the candidate, acting on the last report.
    QUESTION="$QUESTION" bash -c "$gen" _ "$QUESTION" "$report"
    if $AUDIT "$candidate" | tee "$report"; then
      echo ">> PASS after $i round(s): $candidate"
      exit 0
    fi
    echo ">> FAIL; feeding findings back into round $((i + 1))."
  done
  echo "Hit MAX_ITERS=$MAX_ITERS without a pass."
  exit 1
}

case "${1:-}" in
  --replay)
    [ $# -ge 2 ] || { echo "usage: ralph_loop.sh --replay <dir>"; exit 2; }
    replay "$2"
    ;;
  --gen)
    [ $# -ge 3 ] || { echo "usage: ralph_loop.sh --gen \"<cmd>\" <candidate_file>"; exit 2; }
    live "$2" "$3"
    ;;
  "" )
    echo "usage: ralph_loop.sh <candidate_file> | --replay <dir> | --gen \"<cmd>\" <file>"
    exit 2
    ;;
  *)
    banner "AUDIT: $(basename "$1")"
    $AUDIT "$1"
    ;;
esac
