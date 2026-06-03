#!/usr/bin/env bash
# PostToolUse hook (matcher: Bash) — best-effort doom-loop circuit breaker for
# the portas-em-automatico skill. Counts consecutive tool failures per session and
# trips after THRESHOLD to force a pause (cross-check #4).
#
# FAILS OPEN by design: any uncertainty -> do nothing. It can only ever (a) trip on
# clearly-detected repeated failures, or (b) be a harmless no-op. It never blocks a
# successful command.
#
# NOTE: reliable failure detection from the PostToolUse payload varies by Claude Code
# version (a non-zero exit is still a "successful" tool run). Treat as EXPERIMENTAL.
# The hard guarantee in this skill is block-broad-scan.py, not this file.
#
# Tunable: PORTAS_ERROR_THRESHOLD (default 4).

THRESHOLD="${PORTAS_ERROR_THRESHOLD:-4}"
input="$(cat)"

command -v jq >/dev/null 2>&1 || exit 0

sid="$(printf '%s' "$input" | jq -r '.session_id // empty' 2>/dev/null)"
[ -z "$sid" ] && exit 0
state="${TMPDIR:-/tmp}/portas-errcount-${sid}"

# Heuristic failure detection across common payload shapes. Unknown -> "ok".
verdict="$(printf '%s' "$input" | jq -r '
  ( .tool_response.error
    // .tool_response.is_error
    // .tool_response.stderr
    // .tool_response.exit_code
    // .error
    // empty ) as $sig
  | if   ($sig == null) or ($sig == "") or ($sig == false) or ($sig == 0)
    then "ok" else "err" end' 2>/dev/null)"

if [ "$verdict" = "err" ]; then
  prev="$(cat "$state" 2>/dev/null || echo 0)"
  case "$prev" in (''|*[!0-9]*) prev=0 ;; esac
  n=$((prev + 1))
  printf '%s' "$n" > "$state"
  if [ "$n" -ge "$THRESHOLD" ]; then
    rm -f "$state"
    echo "CIRCUIT BREAKER (portas-em-automatico): $n consecutive tool failures. Stop retrying variants — report the error, your hypothesis, and what you need to proceed (cross-check #4)." >&2
    exit 2
  fi
else
  rm -f "$state" 2>/dev/null   # a success resets the streak
fi
exit 0
