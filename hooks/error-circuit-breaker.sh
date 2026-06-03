#!/usr/bin/env bash
# PostToolUse + PostToolUseFailure hook — doom-loop circuit breaker for the
# portas-em-automatico skill (cross-check #4). Registered (via SKILL.md frontmatter)
# on BOTH events:
#   - PostToolUseFailure -> the DOCUMENTED, dedicated failure signal -> increment.
#   - PostToolUse        -> a tool ran; inspect the payload for a non-zero exit as a
#                           secondary signal, otherwise treat as success and RESET.
# Trips (exit 2) after THRESHOLD consecutive failures. FAILS OPEN: any uncertainty -> 0.
#
# Confirm the real payload shape on your Claude Code version by exporting PORTAS_DEBUG=1
# — it appends raw stdin to ~/.claude/portas-checkpoints/posthook-debug.jsonl so you can
# see exactly which event fires and which fields carry the exit status, then tune.
#
# Tunable: PORTAS_ERROR_THRESHOLD (default 4).

THRESHOLD="${PORTAS_ERROR_THRESHOLD:-4}"
input="$(cat)"
command -v jq >/dev/null 2>&1 || exit 0

if [ -n "${PORTAS_DEBUG:-}" ]; then
  d="${HOME}/.claude/portas-checkpoints"; mkdir -p "$d" 2>/dev/null
  printf '%s\n' "$input" >> "$d/posthook-debug.jsonl"
fi

event="$(printf '%s' "$input" | jq -r '.hook_event_name // empty' 2>/dev/null)"
sid="$(printf '%s' "$input" | jq -r '.session_id // empty' 2>/dev/null)"
[ -z "$sid" ] && exit 0
state="${TMPDIR:-/tmp}/portas-errcount-${sid}"

failed=0
if [ "$event" = "PostToolUseFailure" ]; then
  failed=1
else
  # PostToolUse: best-effort non-zero-exit / error detection across common field shapes.
  sig="$(printf '%s' "$input" | jq -r '
    ( .tool_response.exit_code // .tool_response.exitCode
      // .tool_response.returncode // .tool_response.code
      // .tool_response.error // .tool_response.is_error // .error
      // empty ) as $s
    | if ($s == null) or ($s == "") or ($s == false) or ($s == 0)
      then "ok" else "err" end' 2>/dev/null)"
  [ "$sig" = "err" ] && failed=1
fi

if [ "$failed" = "1" ]; then
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
  rm -f "$state" 2>/dev/null   # a clean success resets the streak
fi
exit 0
