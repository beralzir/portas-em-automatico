#!/usr/bin/env bash
# statusLine command — surfaces the live context % (the real gauge for the skill's
# context-discipline cross-check) plus model and current dir. Defensive: if a field
# is absent in this Claude Code version, it is simply omitted.

input="$(cat)"
command -v jq >/dev/null 2>&1 || { printf 'portas'; exit 0; }

dir="$(printf '%s' "$input" | jq -r '.workspace.current_dir // .cwd // empty' 2>/dev/null)"
dir="${dir##*/}"
model="$(printf '%s' "$input" | jq -r '.model.display_name // .model.id // empty' 2>/dev/null)"
pct="$(printf '%s' "$input" | jq -r '
  ( .context_window.used_percentage
    // .context.used_percentage
    // .context_window.used_pct
    // empty )' 2>/dev/null)"

out=""
[ -n "$model" ] && out="$model"
[ -n "$dir" ] && out="${out:+$out · }📁 $dir"

if [ -n "$pct" ] && [ "$pct" != "null" ]; then
  pint="$(printf '%.0f' "$pct" 2>/dev/null || echo "")"
  if [ -n "$pint" ]; then
    flag=""
    if [ "$pint" -ge 80 ] 2>/dev/null; then flag="⚠️ "; fi
    out="${out:+$out · }${flag}ctx ${pint}%"
  fi
fi

printf '%s' "${out:-portas-em-automatico}"
exit 0
