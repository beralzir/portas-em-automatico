#!/usr/bin/env bash
# install.sh — finishes setting up portas-em-automatico after a clone into
# ~/.claude/skills/portas-em-automatico/.
#
# The guardrail hooks (scan blocker, error circuit breaker, precompact checkpoint) are
# bundled in SKILL.md frontmatter and load automatically when the skill is engaged, so
# they need NO settings.json changes. This script only:
#   1. makes the hook scripts executable (frontmatter hooks run them by relative path),
#   2. adds the always-on context-% status line to ~/.claude/settings.json (idempotent,
#      never clobbers an existing statusLine),
#   3. runs the self-test.
#
# Safe to re-run. Backs up settings.json before touching it.
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
SETTINGS="${HOME}/.claude/settings.json"
SL_CMD="bash ${SKILL_DIR}/hooks/statusline-context.sh"

command -v jq >/dev/null 2>&1 || { echo "ERROR: jq is required (brew install jq)."; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 is required."; exit 1; }

echo "1/3  Making hook scripts executable..."
chmod +x "${SKILL_DIR}/hooks/"*.sh "${SKILL_DIR}/hooks/"*.py 2>/dev/null || true

echo "2/3  Wiring the context-% status line into settings.json..."
mkdir -p "${HOME}/.claude"
[ -f "$SETTINGS" ] || echo '{}' > "$SETTINGS"
cp "$SETTINGS" "${SETTINGS}.bak-portas"
echo "     backup -> ${SETTINGS}.bak-portas"
if jq -e '.statusLine' "$SETTINGS" >/dev/null 2>&1; then
  echo "     a statusLine already exists — leaving it untouched."
  echo "     (to use ours, set statusLine.command to: ${SL_CMD})"
else
  tmp="$(mktemp)"
  jq --arg cmd "$SL_CMD" '.statusLine = {type:"command", command:$cmd}' "$SETTINGS" > "$tmp"
  mv "$tmp" "$SETTINGS"
  echo "     added context-% status line."
fi

echo "3/3  Self-test..."
if python3 "${SKILL_DIR}/tests/test_block_broad_scan.py" >/dev/null 2>&1; then
  echo "     scan-blocker self-test: PASS (36/36)"
else
  echo "     scan-blocker self-test: FAILED — run it directly to see details:"
  echo "       python3 ${SKILL_DIR}/tests/test_block_broad_scan.py"
fi

echo
echo "Done. The guardrail hooks load automatically when you invoke /portas-em-automatico"
echo "(or a release phrase like \"doors to automatic and cross-check\"). Restart your"
echo "Claude Code session so settings.json (status line) takes effect."
