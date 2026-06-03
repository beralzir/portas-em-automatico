# portas-em-automatico

> Claude Code skill — supervised autonomous execution. Runs an **approved** plan on its own, but hard *cross-checks* (and real harness hooks) force a pause before irreversible actions, broad filesystem scans, doom loops, and context blow-ups.

*By **[Renato Beralzir](https://github.com/beralzir)** — independent authorship.*

## What the name means

**"Portas em automático"** (Portuguese for *"doors to automatic"*) comes from commercial aviation. **"Doors to automatic and cross-check"** is the command cabin crew run before pushback:

- **Doors to automatic** — each flight attendant arms their door's evacuation slide. Once *automatic*, opening the door deploys the slide by itself. The action now carries an automatic consequence.
- **Cross-check** — each attendant then verifies a *colleague's* door. A second, deliberate human check stands between a routine action and a catastrophic one.

That is exactly the posture this skill encodes for autonomous runs: you are **armed** to execute without re-asking for every step (*doors to automatic*), and a small set of **cross-checks** gates the few actions that are irreversible or ambiguous. English speakers can invoke it with **"doors to automatic"**, **"doors at automatic"**, or **"cross-check"**.

## Why it exists

Letting an agent run unattended fails in four well-documented ways. Plain prompt instructions barely help with two of them — *"prompts are suggestions; hooks are enforcement."* This skill pairs **instructions** (the cross-checks) with an **enforcement layer** (hooks) so the dangerous cases are actually blocked, not just discouraged:

| Failure mode | Instruction (SKILL.md) | Enforcement (hook) |
|---|---|---|
| Widening a failed search to the whole machine (`find /`) | cross-check #3 | **`block-broad-scan.py`** hard-blocks it |
| Irreversible delete (`rm -rf ~`) | cross-check #2 | **`block-broad-scan.py`** hard-blocks it |
| Doom loop (same error, retried forever) | cross-check #4 | **`error-circuit-breaker.sh`** trips after N |
| Context fills up and quality silently rots | context discipline | **`precompact-checkpoint.sh`** + **statusline %** |

## What the skill does (the cross-checks)

Once a plan is approved and you "release" execution, Claude keeps going **without** re-asking for each approved step — but it must **stop and bring you back in** when any of these countable conditions is true:

1. **Plan drift** — reality diverges from the approved plan.
2. **Destructive / irreversible** — before deleting/overwriting outside the project, deploying, migrating, force-pushing, or sending anything external.
3. **Path not found → do not widen scope** — never escalate a missing path to a whole-machine `find /`.
4. **Repeated error** — same class of error 3× on one sub-task → stop, don't keep trying variants.
5. **Genuine fork** — 2+ reasonable approaches where picking wrong costs rework.

Vague self-states ("if unsure") decay over a long session; these are written as **checkable conditions** on purpose.

## Relationship to daquele-jeito

Complementary, not a replacement:

- [`daquele-jeito`](https://github.com/beralzir/daquele-jeito) governs the **before** — plan-first, clarifying questions, 4-axis audit.
- `portas-em-automatico` governs the **after** — how Claude behaves once the plan is approved and it executes on its own.

Use them together: plan *daquele jeito*, then put the *doors to automatic*.

## The harness layer (hooks)

Three guardrail hooks are **bundled in `SKILL.md`'s frontmatter**, so they load automatically when the skill is engaged and are scoped to it — no global hook config. Only the always-on status line lives in `~/.claude/settings.json` (added by `install.sh`). Scripts live in [`hooks/`](hooks/):

| Hook | Event | What it does |
|---|---|---|
| `block-broad-scan.py` | `PreToolUse` (Bash) | Hard-blocks `find /`, `find ~`, broad recursive greps, `rm -r` on top-level roots, fork bombs, pipe-to-shell. Runs **before** the permission mode, so it holds even under `acceptEdits`/bypass. Fails **open**. |
| `error-circuit-breaker.sh` | `PostToolUse` + `PostToolUseFailure` (Bash) | Uses the dedicated failure event to count consecutive failures per session; trips after `PORTAS_ERROR_THRESHOLD` (default 4). `PORTAS_DEBUG=1` logs raw payloads to confirm the schema on your version. |
| `precompact-checkpoint.sh` | `PreCompact` | Snapshots the transcript right before automatic compaction (does **not** block it). |
| `statusline-context.sh` | `statusLine` (settings.json) | Surfaces the live context % (⚠️ at ≥80%) — the real gauge for context discipline. Added by `install.sh`. |

The block list is **defense-in-depth against common, high-cost mistakes**, not a security boundary against a determined adversary. The hard safety boundary is still a sandbox. The block logic is covered by [`tests/test_block_broad_scan.py`](tests/test_block_broad_scan.py) (36 cases: dangerous patterns blocked, look-alikes like `git commit -m "fix rm -rf / bug"` allowed).

## Installation

### 1. Clone the skill

```bash
git clone https://github.com/beralzir/portas-em-automatico.git ~/.claude/skills/portas-em-automatico
```

Update later with `cd ~/.claude/skills/portas-em-automatico && git pull`.

### 2. Run the installer

```bash
~/.claude/skills/portas-em-automatico/install.sh
```

The **guardrail hooks load automatically** from the skill's frontmatter when you engage the skill — no global hook config needed. `install.sh` only adds the always-on context-% status line to `~/.claude/settings.json` (idempotent, backs it up first, never clobbers an existing `statusLine`). Requires `python3` and `jq` on `PATH`.

### 3. Verify

```bash
python3 ~/.claude/skills/portas-em-automatico/tests/test_block_broad_scan.py   # expect pass=36 fail=0
echo '{"tool_input":{"command":"find / -name x"}}' | python3 ~/.claude/skills/portas-em-automatico/hooks/block-broad-scan.py; echo "exit=$? (expect 2)"
```

In a Claude Code session, type `/` and confirm `/portas-em-automatico` appears in autocomplete.

## How to invoke

- **Slash command:** `/portas-em-automatico`
- **Release phrase (PT):** after approving a plan — *"portas em automático"*, *"põe as portas em automático"*, *"pode soltar em automático"*
- **Release phrase (EN):** *"doors to automatic"*, *"doors at automatic"*, *"doors to automatic and cross-check"*, or *"cross-check and go"*

It announces itself on first activation with *"Doors to automatic and cross-check — running in supervised autonomous mode."*

## Uninstallation

```bash
rm -rf ~/.claude/skills/portas-em-automatico
```

Then remove the `statusLine` entry from `~/.claude/settings.json` (or restore the `~/.claude/settings.json.bak-portas` backup that `install.sh` wrote). The guardrail hooks need no cleanup — they lived in the skill folder you just deleted.

## Author & License

**Author / NOTICE** — Created and maintained by **Renato Beralzir** (independent authorship · *pessoa pública / observador de mercado*). Please keep this attribution in copies and derivatives.

MIT — © 2026 Renato Beralzir. See [LICENSE](LICENSE).
