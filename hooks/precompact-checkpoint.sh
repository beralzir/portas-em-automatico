#!/usr/bin/env bash
# PreCompact hook — context backstop for the portas-em-automatico skill.
# Fires right before (auto) compaction, i.e. exactly when the context is full.
#
# It does NOT block compaction: blocking it can create an auto-compact failure loop.
# Side effect only — snapshot the transcript so state survives compaction, and nudge
# the model to refresh its SESSION.md checkpoint.

input="$(cat)"
command -v jq >/dev/null 2>&1 || exit 0

tp="$(printf '%s' "$input" | jq -r '.transcript_path // empty' 2>/dev/null)"
backup_dir="${HOME}/.claude/portas-checkpoints"
mkdir -p "$backup_dir" 2>/dev/null

if [ -n "$tp" ] && [ -f "$tp" ]; then
  ts="$(date +%Y%m%d-%H%M%S 2>/dev/null || echo snapshot)"
  cp "$tp" "${backup_dir}/precompact-${ts}.jsonl" 2>/dev/null
fi

echo "portas-em-automatico: context compaction imminent (context is full). Transcript snapshotted to ${backup_dir}. If SESSION.md is not current, write it now — instructions from early in the session may be dropped." >&2
exit 0
