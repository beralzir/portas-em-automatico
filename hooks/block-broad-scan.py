#!/usr/bin/env python3
"""
PreToolUse hook (matcher: Bash) for the portas-em-automatico skill.

Hard-blocks the two autonomous-mode failure modes the skill exists to prevent:
  - broad filesystem scans  (cross-check #3: "path not found -> do NOT widen scope")
  - destructive deletes on top-level roots (cross-check #2: irreversible action)
plus two always-dangerous classics (fork bomb, pipe-to-shell).

Mechanics: reads the hook JSON from stdin. To BLOCK, it writes a reason to stderr and
exits 2 — Claude Code feeds that back to the model, which then surfaces it and pauses.
Hooks run BEFORE the permission mode, so this holds even under acceptEdits / bypass.

Approach: instead of regex-matching the raw string (which would wrongly block
`git commit -m "fix rm -rf / bug"`), it splits the command into command-position
segments and only inspects the *invoked verb* of each. So `find /` blocks, but `find /`
sitting inside an echo/commit-message/argument does not.

Design rule: FAIL OPEN. Any parsing uncertainty -> exit 0 (allow). A guardrail must
never break a legitimate session; the hard safety boundary is still a sandbox. This is
defense-in-depth against common, high-cost mistakes — not a determined adversary.
"""
import json
import re
import sys

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)

raw = ((data.get("tool_input") or {}).get("command") or "")
if not raw.strip():
    sys.exit(0)

# Newlines act as command separators; collapse remaining whitespace.
norm = re.sub(r"[\r\n]+", " ; ", raw)
norm = " ".join(norm.split())

# Break into command-position segments so each segment's first token is the verb invoked.
segments = re.split(r"(?:\|\||&&|\$\(|[;|&()`])", norm)

# A "broad root": scanning or deleting from here means "the whole machine".
# Anchored to the WHOLE token, so a deep path like /Users/me/Workspaces/proj is NOT broad.
BROAD = re.compile(
    r"^(?:/|~|~/|\$HOME/?|/Users|/Users/[^/]+/?|/etc|/usr|/var|/System"
    r"|/Library|/bin|/sbin|/opt|/private|/Applications)(?:/?\*?)?$"
)

# Command prefixes that wrap the real command.
WRAPPERS = {"sudo", "doas", "command", "env", "nice", "nohup", "time", "stdbuf", "ionice"}


def is_broad(tok):
    t = tok.strip().strip('"').strip("'")
    return bool(BROAD.match(t))


def effective_tokens(tks):
    """Strip leading wrappers (sudo ...), their flags, and env assignments."""
    i, n = 0, len(tks)
    while i < n:
        t = tks[i]
        if t in WRAPPERS:
            i += 1
            while i < n and tks[i].startswith("-"):
                i += 1
        elif "=" in t and not t.startswith("-") and "/" not in t.split("=", 1)[0]:
            i += 1  # FOO=bar env assignment
        else:
            break
    return tks[i:]


def has_recursive_flag(args):
    return any(re.match(r"-{1,2}[A-Za-z]*[rR]", a) or a == "--recursive" for a in args)


reason = None
for seg in segments:
    tks = effective_tokens(seg.split())
    if not tks:
        continue
    verb, args = tks[0], tks[1:]
    nonflag = [a for a in args if not a.startswith("-")]

    if verb == "find":
        if nonflag and is_broad(nonflag[0]):
            reason = ("Broad filesystem scan blocked: never `find` from a top-level root "
                      "(/, ~, /Users, ...). If a path is missing, STOP and ask — do not search "
                      "the whole machine (cross-check #3).")
    elif verb in ("grep", "egrep", "fgrep", "rg"):
        recursive = (verb == "rg") or has_recursive_flag(args)
        if recursive and any(is_broad(a) for a in nonflag):
            reason = ("Broad recursive grep from a top-level root blocked. Narrow the scope to "
                      "the project (cross-check #3).")
    elif verb == "rm":
        if has_recursive_flag(args) and any(is_broad(a) for a in nonflag):
            reason = ("Destructive recursive delete on a top-level root blocked (rm -r on /, ~, "
                      "/Users, ...). Irreversible — STOP and cross-check (cross-check #2).")
    if reason:
        break

if reason is None:
    if re.search(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:", norm):
        reason = "Fork bomb blocked."
    elif re.search(r"(?:curl|wget)\b.*\|\s*(?:sudo\s+)?(?:ba)?sh\b", norm):
        reason = ("Piping a remote download into a shell is blocked — download, inspect, then "
                  "run (cross-check #2).")

if reason:
    sys.stderr.write("BLOCKED by portas-em-automatico: " + reason + "\n")
    sys.exit(2)
sys.exit(0)
