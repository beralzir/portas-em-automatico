#!/usr/bin/env python3
"""
UserPromptSubmit + PostToolUse hook: context gauge for the handoff rule.

Why it exists: the model has no trustworthy sense of how full its context is, and a written
rule ("hand off before compacting") is read once at session start and fades as the
conversation grows. The harness does not fade. This hook reads the context size the API
reported on the last main-thread call (input + cache creation + cache read, the same
formula the status line uses for used_percentage) and puts one short line into the
conversation, in three bands. It works where the status line is not shown (desktop app),
because it reads the transcript, not the status line.

  - delegate (30%+): reminds the main thread to orchestrate and delegate heavy work.
  - info (50%+): the handoff window is open. The model picks the cut point from what
    comes next (before a long task, when a milestone closes), before the ceiling.
  - ceiling (80%+): prepare the handoff now. The ceiling is a limit, not a target.

  - UserPromptSubmit: injects the line on every prompt while at 30% or more.
  - PostToolUse: injects only when the info or ceiling band is first crossed (once per band
    per session), so a long autonomous run with no user prompts still gets the warning
    without nagging on every tool call. The delegate band is prompt-only.
  - Inside a subagent (agent_id present): silent. The handoff is the orchestrator's job.
  - Right after a compaction (compact_boundary newer than the last usage): silent. The
    SessionStart(compact) hook, compact-reanchor.py, handles that moment.

Tunables (% of the window):
  PORTAS_DELEGATE_PCT      delegate reminder (default 30)
  PORTAS_HANDOFF_INFO_PCT  handoff window opens (default 50)
  PORTAS_HANDOFF_PCT       ceiling, prepare the handoff now (default 80)
  PORTAS_CONTEXT_WINDOW    window in tokens (default 1000000, the native window of Opus
                           4.7+ and Sonnet 5+ on the Anthropic API). Set 200000 for 200K
                           models, or the value you gave /autocompact if you changed it.

The transcript is written asynchronously and may lag one call behind. For a gauge that is
fine. FAILS OPEN: any doubt (bad stdin, missing transcript, no usage yet) exits 0 silently.
"""
import json
import os
import sys

CHUNK = 1 << 20          # start reading the last 1 MB of the transcript
MAX_SCAN = 64 << 20      # never scan more than 64 MB back


def env_int(name, default, lo, hi):
    try:
        v = int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default
    return v if lo <= v <= hi else default


def last_main_usage(path):
    """Context tokens of the last main-thread API call, or None.

    Scans the transcript backwards. Returns None if a compact_boundary is newer than the
    last usage line (the number would describe the pre-compaction context)."""
    size = os.path.getsize(path)
    span = CHUNK
    with open(path, "rb") as f:
        while True:
            start = max(0, size - span)
            f.seek(start)
            lines = f.read(size - start).split(b"\n")
            if start > 0:
                lines = lines[1:]            # first line is probably cut in half
            for raw in reversed(lines):
                if b"compact_boundary" in raw:
                    try:
                        if json.loads(raw).get("subtype") == "compact_boundary":
                            return None
                    except ValueError:
                        pass
                if b'"usage"' not in raw or b'"assistant"' not in raw:
                    continue
                try:
                    e = json.loads(raw)
                except ValueError:
                    continue
                if e.get("type") != "assistant" or e.get("isSidechain"):
                    continue
                u = (e.get("message") or {}).get("usage") or {}
                total = sum(int(u.get(k) or 0) for k in (
                    "input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
                if total > 0:
                    return total
            if start == 0 or span >= MAX_SCAN:
                return None
            span *= 2


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    if not isinstance(data, dict) or data.get("agent_id"):
        return 0
    event = data.get("hook_event_name") or ""
    if event not in ("UserPromptSubmit", "PostToolUse"):
        return 0
    tp = data.get("transcript_path") or ""
    sid = data.get("session_id") or ""
    if not tp or not os.path.isfile(tp):
        return 0

    used = last_main_usage(tp)
    if not used:
        return 0
    window = env_int("PORTAS_CONTEXT_WINDOW", 1000000, 100000, 10000000)
    ceiling = env_int("PORTAS_HANDOFF_PCT", 80, 20, 95)
    info = min(env_int("PORTAS_HANDOFF_INFO_PCT", 50, 10, 95), ceiling)
    delegate = min(env_int("PORTAS_DELEGATE_PCT", 30, 5, 95), info)
    pct = used * 100.0 / window
    if pct < delegate:
        return 0
    level = 3 if pct >= ceiling else 2 if pct >= info else 1

    if event == "PostToolUse":
        if level < 2 or not sid:
            return 0
        state = os.path.join(os.environ.get("TMPDIR", "/tmp"), "portas-gauge-" + sid)
        try:
            with open(state) as f:
                prev = int(f.read().strip() or 0)
        except (OSError, ValueError):
            prev = 0
        if level <= prev:
            return 0
        try:
            with open(state, "w") as f:
                f.write(str(level))
        except OSError:
            pass

    head = "[context-gauge] Context at %d%% of the window (%dk of %dk tokens)." % (
        pct, used // 1000, window // 1000)
    orchestrate = ("Orchestrate: send heavy reads, parallel research and long mechanical work "
                   "to subagents with a full brief, and keep the user dialogue, decisions, git "
                   "and verification in this thread.")
    handoff = ("update SESSION.md (goal, what closed with proof, decisions and why, files "
               "touched, open thread, next step, anchor formats), commit and push only the "
               "registry files if the user's rules say so, then open the fresh session: if a "
               "tool spawns a new session or task (a session chip), create it with a "
               "self-contained resume prompt, otherwise give that prompt in a block to paste.")
    if level == 3:
        msg = (head + " CEILING REACHED: prepare the handoff now, before any other tool call. "
               "Finish only the step in progress, " + handoff +
               " Do not let auto-compaction be the handoff.")
    elif level == 2:
        msg = (head + " Handoff window open: pick the best cut point before %d%% from what "
               "comes next (before a long task, when a milestone closes). %d%% is a ceiling, "
               "not a target. At the cut, finish the step in progress without starting a new "
               "one, " % (ceiling, ceiling) + handoff + " " + orchestrate)
    else:
        msg = head + " " + orchestrate
    print(json.dumps({"hookSpecificOutput": {"hookEventName": event,
                                             "additionalContext": msg}}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
