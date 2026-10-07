#!/usr/bin/env python3
"""
SessionStart hook (matcher "compact"): re-anchor the session right after a compaction.

Why it exists: PreCompact output never reaches the model, and it fires when there is no
turn left to act on it, so "write the checkpoint before compacting" cannot be enforced
there. What the harness does guarantee is that SessionStart hooks matching the `compact`
source run after compaction and their stdout is added to the compacted context. This hook
uses that moment to put the state back: where the full history lives, the project's
checkpoint (SESSION.md, inlined up to a cap), which registry files to re-read, and the
instruction to hand off to a fresh session instead of carrying on half-blind.

The transcript on disk keeps every line from before the compaction; only the model's
working context was summarized. That is why the hook points to it instead of copying it.

Inside a subagent (agent_id present): silent. FAILS OPEN: any doubt exits 0 silently.
"""
import json
import os
import sys

SESSION_CAP = 6000      # stay well under the 10,000-character cap on hook output


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    if not isinstance(data, dict) or data.get("agent_id"):
        return 0
    if data.get("hook_event_name") != "SessionStart" or data.get("source") != "compact":
        return 0
    cwd = data.get("cwd") or os.getcwd()
    tp = data.get("transcript_path") or ""

    found = [n for n in ("CLAUDE.md", "HANDOFF.md", "SESSION.md")
             if os.path.isfile(os.path.join(cwd, n))]
    out = ["[compact-reanchor] This session was just auto-compacted: most of the conversation "
           "was replaced by a summary, and decisions made early may be missing from it."]
    if tp:
        out.append("Full history is still on disk at %s (search it with grep for a specific "
                   "decision; do not read it whole)." % tp)
    if found:
        out.append("Before the next step, re-read from %s: %s." % (cwd, ", ".join(found)))
    else:
        out.append("No HANDOFF.md or SESSION.md in %s: write SESSION.md now, from the summary "
                   "and the transcript, before the next step." % cwd)
    out.append("Then tell the user that compaction happened and hand off now: update "
               "SESSION.md, commit and push only the registry files if the user's rules say "
               "so, and open the fresh session (a session chip with a self-contained resume "
               "prompt where a tool spawns one, otherwise that prompt in a block to paste).")

    sp = os.path.join(cwd, "SESSION.md")
    if os.path.isfile(sp):
        try:
            with open(sp, encoding="utf-8", errors="replace") as f:
                text = f.read(SESSION_CAP + 1)
        except OSError:
            text = ""
        if text:
            cut = len(text) > SESSION_CAP
            out.append("\n--- SESSION.md (as on disk%s) ---\n%s" % (
                ", truncated" if cut else "", text[:SESSION_CAP]))
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
