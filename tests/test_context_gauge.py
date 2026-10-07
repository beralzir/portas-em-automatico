#!/usr/bin/env python3
"""
Test matrix for hooks/context-gauge.py and hooks/compact-reanchor.py.

Runs each hook as a subprocess with synthetic transcripts and payloads, and asserts what
reaches the model (stdout) and the exit code (always 0: both hooks fail open and never
block). Each case gets its own TMPDIR so the per-session band state never leaks.

Run:  python3 tests/test_context_gauge.py
"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAUGE = os.path.join(ROOT, "hooks", "context-gauge.py")
REANCHOR = os.path.join(ROOT, "hooks", "compact-reanchor.py")


def assistant(tokens, sidechain=False):
    # Split the way the API reports it: mostly cache reads, a little cache creation.
    return {"type": "assistant", "isSidechain": sidechain,
            "message": {"usage": {"input_tokens": 2,
                                  "cache_creation_input_tokens": 1000,
                                  "cache_read_input_tokens": tokens - 1002}}}


def transcript(d, entries):
    p = os.path.join(d, "t.jsonl")
    with open(p, "w") as f:
        for e in entries:
            f.write((e if isinstance(e, str) else json.dumps(e)) + "\n")
    return p


def run(hook, payload, tmp, env_extra=None):
    env = dict(os.environ, TMPDIR=tmp)
    env.pop("PORTAS_HANDOFF_PCT", None)
    env.pop("PORTAS_CONTEXT_WINDOW", None)
    env.update(env_extra or {})
    stdin = payload if isinstance(payload, str) else json.dumps(payload)
    r = subprocess.run([sys.executable, hook], input=stdin, capture_output=True,
                       text=True, env=env, timeout=30)
    return r.returncode, r.stdout.strip()


def gauge_payload(tp, event="UserPromptSubmit", **kw):
    p = {"hook_event_name": event, "session_id": "s1", "transcript_path": tp}
    p.update(kw)
    return p


results = []


def check(name, cond):
    results.append((name, bool(cond)))


def ctx(out):
    return json.loads(out)["hookSpecificOutput"]["additionalContext"] if out else ""


with tempfile.TemporaryDirectory() as d:
    # 1. below the delegate band: silent
    tp = transcript(d, [{"type": "user"}, assistant(200000)])
    rc, out = run(GAUGE, gauge_payload(tp), d)
    check("20% -> silent", rc == 0 and out == "")

    # 2. delegate band: one discreet line on prompts, nothing on tool calls
    tp = transcript(d, [assistant(350000)])
    rc, out = run(GAUGE, gauge_payload(tp), d)
    c = ctx(out)
    check("35% prompt -> delegate line only",
          rc == 0 and "35%" in c and "Orchestrate" in c and "Handoff window" not in c)
    check("delegate line is short", 0 < len(c) < 300)
    rc, out = run(GAUGE, gauge_payload(tp, "PostToolUse"), d)
    check("35% tool call -> silent (delegate band is prompt-only)", rc == 0 and out == "")

    # 3. info band: the handoff window opens, the model picks the cut point
    tp = transcript(d, [assistant(100000), assistant(650000)])
    rc, out = run(GAUGE, gauge_payload(tp), d)
    c = ctx(out)
    check("65% -> handoff window open, ceiling named",
          rc == 0 and "65%" in c and "Handoff window open" in c and "before 80%" in c
          and "CEILING" not in c)
    check("info line keeps the orchestrate reminder", "Orchestrate" in c)
    check("info names the event", out and json.loads(out)["hookSpecificOutput"]
          ["hookEventName"] == "UserPromptSubmit")

    # 4. ceiling band
    tp = transcript(d, [assistant(850000)])
    rc, out = run(GAUGE, gauge_payload(tp), d)
    check("85% -> ceiling reached", rc == 0 and "CEILING REACHED" in ctx(out))
    check("ceiling line stays under 1,200 chars", len(ctx(out)) < 1200)

    # 5. inside a subagent: silent even at the ceiling
    rc, out = run(GAUGE, gauge_payload(tp, agent_id="a1"), d)
    check("subagent -> silent", rc == 0 and out == "")

    # 6. sidechain lines are ignored; the main-thread line decides
    tp = transcript(d, [assistant(200000), assistant(900000, sidechain=True)])
    rc, out = run(GAUGE, gauge_payload(tp), d)
    check("sidechain ignored", rc == 0 and out == "")

    # 7. compaction newer than the last usage: silent (reanchor hook owns that moment)
    tp = transcript(d, [assistant(967000),
                        {"type": "system", "subtype": "compact_boundary"},
                        {"type": "user"}])
    rc, out = run(GAUGE, gauge_payload(tp), d)
    check("after compact_boundary -> silent", rc == 0 and out == "")

    # 8. a line that merely mentions compact_boundary does not count as one
    tp = transcript(d, [{"type": "user", "content": "grep compact_boundary x.jsonl"},
                        assistant(700000),
                        {"type": "user", "content": "grep compact_boundary again"}])
    rc, out = run(GAUGE, gauge_payload(tp), d)
    check("mention of compact_boundary is not a boundary", rc == 0 and "70%" in out)

with tempfile.TemporaryDirectory() as d:
    # 9. PostToolUse: once per band per session (info, then ceiling)
    tp = transcript(d, [assistant(650000)])
    rc1, out1 = run(GAUGE, gauge_payload(tp, "PostToolUse"), d)
    rc2, out2 = run(GAUGE, gauge_payload(tp, "PostToolUse"), d)
    tp = transcript(d, [assistant(820000)])
    rc3, out3 = run(GAUGE, gauge_payload(tp, "PostToolUse"), d)
    rc4, out4 = run(GAUGE, gauge_payload(tp, "PostToolUse"), d)
    check("PostToolUse first info crossing -> info", rc1 == 0 and "Handoff window" in out1)
    check("PostToolUse same band -> silent", rc2 == 0 and out2 == "")
    check("PostToolUse ceiling crossing -> ceiling", rc3 == 0 and "CEILING" in out3)
    check("PostToolUse ceiling again -> silent", rc4 == 0 and out4 == "")
    # UserPromptSubmit keeps reminding regardless of the band state
    rc5, out5 = run(GAUGE, gauge_payload(tp), d)
    check("UserPromptSubmit always reminds", rc5 == 0 and "CEILING" in out5)

with tempfile.TemporaryDirectory() as d:
    # 10. tunables
    tp = transcript(d, [assistant(130000)])
    rc, out = run(GAUGE, gauge_payload(tp), d, {"PORTAS_CONTEXT_WINDOW": "200000"})
    check("200K window: 130k -> 65% info", rc == 0 and "65%" in out and "Handoff window" in out)
    tp = transcript(d, [assistant(650000)])
    rc, out = run(GAUGE, gauge_payload(tp), d, {"PORTAS_HANDOFF_PCT": "60"})
    check("ceiling 60: 65% -> ceiling", rc == 0 and "CEILING" in out)
    tp = transcript(d, [assistant(450000)])
    rc, out = run(GAUGE, gauge_payload(tp), d, {"PORTAS_HANDOFF_INFO_PCT": "40"})
    check("info 40: 45% -> info", rc == 0 and "Handoff window" in out)
    rc, out = run(GAUGE, gauge_payload(tp), d, {"PORTAS_HANDOFF_INFO_PCT": "abc"})
    check("bad tunable falls back to defaults: 45% -> delegate only",
          rc == 0 and "Orchestrate" in out and "Handoff window" not in out)
    tp = transcript(d, [assistant(150000)])
    rc, out = run(GAUGE, gauge_payload(tp), d, {"PORTAS_DELEGATE_PCT": "10"})
    check("delegate 10: 15% -> delegate line", rc == 0 and "Orchestrate" in out)
    tp = transcript(d, [assistant(850000)])
    rc, out = run(GAUGE, gauge_payload(tp), d, {"PORTAS_HANDOFF_INFO_PCT": "90"})
    check("info above ceiling is clamped: 85% -> ceiling", rc == 0 and "CEILING" in out)

    # 11. fail open
    rc, out = run(GAUGE, "not json", d)
    check("garbage stdin -> exit 0 silent", rc == 0 and out == "")
    rc, out = run(GAUGE, gauge_payload(os.path.join(d, "missing.jsonl")), d)
    check("missing transcript -> exit 0 silent", rc == 0 and out == "")
    tp = transcript(d, ["{broken", "", "[]"])
    rc, out = run(GAUGE, gauge_payload(tp), d)
    check("no usage lines -> exit 0 silent", rc == 0 and out == "")
    rc, out = run(GAUGE, gauge_payload(tp, "Stop"), d)
    check("other event -> silent", rc == 0 and out == "")

with tempfile.TemporaryDirectory() as d:
    # 12. compact-reanchor
    proj = os.path.join(d, "proj")
    os.makedirs(proj)
    pay = {"hook_event_name": "SessionStart", "source": "compact", "cwd": proj,
           "transcript_path": "/x/t.jsonl", "session_id": "s1"}
    rc, out = run(REANCHOR, pay, d)
    check("reanchor without SESSION.md asks to write it",
          rc == 0 and "write SESSION.md now" in out and "/x/t.jsonl" in out)
    with open(os.path.join(proj, "SESSION.md"), "w") as f:
        f.write("# SESSION\n## O fio aberto\nfase 2, passo 3\n")
    with open(os.path.join(proj, "HANDOFF.md"), "w") as f:
        f.write("# Handoff\n")
    rc, out = run(REANCHOR, pay, d)
    check("reanchor lists files and inlines SESSION.md",
          rc == 0 and "HANDOFF.md, SESSION.md" in out and "fase 2, passo 3" in out)
    check("reanchor hands off now, chip or paste block",
          "hand off now" in out and "session chip" in out and "block to paste" in out)
    with open(os.path.join(proj, "SESSION.md"), "w") as f:
        f.write("x" * 20000)
    rc, out = run(REANCHOR, pay, d)
    check("reanchor output stays under the 10,000-char hook cap",
          rc == 0 and "truncated" in out and len(out) < 10000)
    rc, out = run(REANCHOR, dict(pay, source="startup"), d)
    check("reanchor ignores non-compact starts", rc == 0 and out == "")
    rc, out = run(REANCHOR, dict(pay, agent_id="a1"), d)
    check("reanchor silent in subagent", rc == 0 and out == "")
    rc, out = run(REANCHOR, "not json", d)
    check("reanchor garbage stdin -> exit 0 silent", rc == 0 and out == "")

fails = [n for n, ok in results if not ok]
for n, ok in results:
    print(("PASS " if ok else "FAIL ") + n)
print("pass=%d fail=%d" % (len(results) - len(fails), len(fails)))
sys.exit(1 if fails else 0)
