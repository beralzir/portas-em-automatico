#!/usr/bin/env python3
"""
Static guard for the hooks declared in SKILL.md frontmatter.

Frontmatter hooks run from the session's working directory, not from this folder, so a
relative "./hooks/..." path fails silently (exit 127) in every other project. Claude Code
hands skill hooks this folder as ${CLAUDE_PLUGIN_ROOT}, substituted into command and args
(exec form) and exported to the hook's environment. ${CLAUDE_SKILL_DIR} is never set for
hooks, and a path pinned to one install location breaks wherever else the skill lives.
Some events never run skill hooks at all (checked on Claude Code 2.1.286 and 2.1.289), so
a hook declared on them is dead code.

Run:  python3 tests/test_frontmatter_paths.py
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
front = ROOT.joinpath("SKILL.md").read_text(encoding="utf-8").split("\n---", 1)[0]
block = front.split("\nhooks:", 1)[1] if "\nhooks:" in front else ""

# Events whose hooks Claude Code collects without the session registry, where skill
# hooks live.
SKIPS_SKILL_HOOKS = {"PreCompact", "PostCompact", "Notification", "ConfigChange",
                     "InstructionsLoaded", "Elicitation", "ElicitationResult",
                     "DirectoryAdded", "WorktreeCreate", "WorktreeRemove"}

events = re.findall(r"^  ([A-Za-z]+):\s*$", block, re.M)
values = re.findall(r"^\s*(?:command|args):\s*(.+)$", block, re.M)
scripts = re.findall(r"\$\{CLAUDE_PLUGIN_ROOT\}/hooks/([\w.-]+)", "\n".join(values))

fails = []
if not values:
    fails.append("no hook command found in frontmatter")
for v in values:
    if "./hooks/" in v:
        fails.append(f"relative hook path: {v}")
    elif "CLAUDE_SKILL_DIR" in v:
        fails.append(f"CLAUDE_SKILL_DIR is never set for hooks: {v}")
    elif "hooks/" in v and "${CLAUDE_PLUGIN_ROOT}/hooks/" not in v:
        fails.append(f"hook script not referenced through ${{CLAUDE_PLUGIN_ROOT}}: {v}")
for s in scripts:
    if not ROOT.joinpath("hooks", s).is_file():
        fails.append(f"missing script: hooks/{s}")
for e in events:
    if e in SKIPS_SKILL_HOOKS:
        fails.append(f"Claude Code never runs skill hooks on {e}")

print(f"frontmatter hook paths: {'PASS' if not fails else 'FAIL'} "
      f"({len(values)} entries, {len(scripts)} script refs, events: {', '.join(events) or 'none'})")
for f in fails:
    print("  -", f)
sys.exit(1 if fails else 0)
