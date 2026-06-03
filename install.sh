#!/usr/bin/env bash
# install.sh — finishes setting up portas-em-automatico after a clone into
# ~/.claude/skills/portas-em-automatico/.
#
# Two enforcement scopes:
#   - ALWAYS-ON (global, in ~/.claude/settings.json): the scan/destruction blocker
#     (PreToolUse) and the context-% status line. Added here, idempotently.
#   - SKILL-SCOPED (in SKILL.md frontmatter): the error circuit breaker and the
#     precompact checkpoint — they load automatically when the skill is engaged and
#     need NO settings.json changes.
#
# Safe to re-run. Backs up settings.json before touching it; never clobbers existing keys.
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
SETTINGS="${HOME}/.claude/settings.json"
SL_CMD="bash ${SKILL_DIR}/hooks/statusline-context.sh"
BLOCK_CMD="python3 ${SKILL_DIR}/hooks/block-broad-scan.py"

command -v jq >/dev/null 2>&1 || { echo "ERROR: jq is required (brew install jq)."; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 is required."; exit 1; }

echo "1/3  Making hook scripts executable..."
chmod +x "${SKILL_DIR}/hooks/"*.sh "${SKILL_DIR}/hooks/"*.py 2>/dev/null || true

echo "2/3  Wiring always-on pieces into settings.json (scan blocker + status line)..."
mkdir -p "${HOME}/.claude"
[ -f "$SETTINGS" ] || echo '{}' > "$SETTINGS"
cp "$SETTINGS" "${SETTINGS}.bak-portas"
echo "     backup -> ${SETTINGS}.bak-portas"

# Status line (no-clobber).
if jq -e '.statusLine' "$SETTINGS" >/dev/null 2>&1; then
  echo "     a statusLine already exists — leaving it untouched (ours: ${SL_CMD})."
else
  tmp="$(mktemp)"
  jq --arg cmd "$SL_CMD" '.statusLine = {type:"command", command:$cmd}' "$SETTINGS" > "$tmp"
  mv "$tmp" "$SETTINGS"
  echo "     added context-% status line."
fi

# Global scan/destruction blocker (idempotent — appends, never clobbers other hooks).
if jq -e --arg c "$BLOCK_CMD" '[(.hooks.PreToolUse // [])[].hooks[]?.command] | index($c)' "$SETTINGS" >/dev/null 2>&1; then
  echo "     scan blocker already registered globally."
else
  tmp="$(mktemp)"
  jq --arg c "$BLOCK_CMD" '.hooks.PreToolUse = ((.hooks.PreToolUse // []) + [{matcher:"Bash", hooks:[{type:"command", command:$c}]}])' "$SETTINGS" > "$tmp"
  mv "$tmp" "$SETTINGS"
  echo "     registered scan blocker globally (PreToolUse/Bash)."
fi

echo "3/3  Self-test..."
if python3 "${SKILL_DIR}/tests/test_block_broad_scan.py" >/dev/null 2>&1; then
  echo "     scan-blocker self-test: PASS (36/36)"
else
  echo "     scan-blocker self-test: FAILED — run it directly to see details:"
  echo "       python3 ${SKILL_DIR}/tests/test_block_broad_scan.py"
fi

echo
echo "Done."
echo "  - Global (settings.json): scan blocker + context-% status line."
echo "  - Skill-scoped (frontmatter): circuit breaker + precompact — load on /portas-em-automatico."
echo "Restart your Claude Code session so settings.json takes effect."
