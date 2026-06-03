---
name: portas-em-automatico
description: |
  Use this skill to run an APPROVED plan in supervised autonomous mode — Claude keeps executing without re-asking for each step, but hard cross-checks force it to PAUSE before irreversible actions, on genuine forks, on repeated errors, and to checkpoint state before the context degrades. Complements (does not replace) daquele-jeito: that one is plan-first + audit; this one governs the execution phase after you "release" the plan. Pairs with the harness hooks shipped in this skill's hooks/ folder.

  TRIGGER when: (1) the user invokes `/portas-em-automatico`; OR (2) after a plan is approved, the user attaches a release phrase as a final/standalone instruction. Release phrases (case-insensitive): Portuguese "portas em automático" / "põe as portas em automático" / "pode soltar em automático"; English "doors to automatic" / "doors at automatic" / "doors to automatic and cross-check". The bare word "cross-check" triggers ONLY when used as a command to engage the mode (e.g. "cross-check and go"), not when it is part of a data task.

  DO NOT TRIGGER when: the phrase is negated ("não põe em automático"), past tense, a meta-question ("o que é doors to automatic?"), or when "cross-check" means a literal data-reconciliation task ("faça o cross-check dessas duas planilhas"). When in doubt, prefer the slash command.
hooks:
  PreToolUse:
    - matcher: Bash
      hooks:
        - type: command
          command: "./hooks/block-broad-scan.py"
  PostToolUse:
    - matcher: Bash
      hooks:
        - type: command
          command: "./hooks/error-circuit-breaker.sh"
  PostToolUseFailure:
    - matcher: Bash
      hooks:
        - type: command
          command: "./hooks/error-circuit-breaker.sh"
  PreCompact:
    - hooks:
        - type: command
          command: "./hooks/precompact-checkpoint.sh"
---

# Portas em automático — supervised autonomous execution

Apply this when the user has approved a plan and released execution. You keep going without re-asking for each approved step — but the **cross-checks** below override "keep going". Honoring them is the entire point of this mode.

**Activation announcement:** the first time this activates in a conversation, open with a short line — *"Doors to automatic and cross-check — running in supervised autonomous mode."* Don't repeat on later activations in the same conversation.

## What the name means

**"Portas em automático"** (PT) comes from commercial aviation. **"Doors to automatic and cross-check"** is the command cabin crew run before pushback: each flight attendant arms their door's evacuation slide — *doors to automatic*, so opening the door now deploys the slide automatically — and then **cross-checks** a colleague's door to confirm it was armed correctly. It is a two-person, deliberate verification standing between a routine action and a catastrophic one.

Two ideas carry straight into this mode:

- **Doors to automatic** = you are armed for autonomous execution. Actions now have automatic consequences, so you move deliberately, not casually.
- **Cross-check** = nothing consequential is taken on trust. A second, deliberate verification gates every irreversible step. The cross-checks below *are* that verification.

(English invocation: "doors to automatic", "doors at automatic", or "cross-check".)

## Relationship to daquele-jeito

Complementary, not a replacement:

- `daquele-jeito` governs the **before** — plan-first, clarifying questions, 4-axis audit.
- `portas-em-automatico` governs the **after** — how you behave once the plan is approved and you are executing on your own.

If both are active: follow daquele-jeito for planning and the final audit, and these cross-checks during execution.

## The contract

You are past approval. Do **not** re-ask permission for steps already in the approved plan — that is what "doors to automatic" means; asking again defeats the mode. But the plan is a contract: if reality diverges from it, you are **not** authorized to improvise silently. The cross-checks are the precise, limited exceptions that bring the human back in.

## Cross-checks — PAUSE and bring the human back in

Stop and use `AskUserQuestion` (or report and wait for a reply) when ANY of these is true. They are written as **countable conditions** on purpose: vague self-states ("if you feel unsure") decay and you may not detect them; checkable conditions survive a long, full session.

1. **Plan drift.** An approved step turns out wrong, a dependency does not exist, or scope grows beyond the plan. Do not force the original plan — state the divergence, propose an amendment, validate it, then continue.
2. **Destructive / irreversible — cross-check before acting.** Before ANY command that deletes, overwrites, or moves files *outside the project directory*, and before any outward or irreversible action (deploy, DB migration, network mutation, sending anything external, force-push, publishing). State exactly what will change, then confirm.
3. **Path not found → do NOT widen the scope.** If an expected file or directory is missing, NEVER escalate the search to the whole machine — no `find /`, no `find ~`, no climbing to `/` or the home root. Stop, report "expected X here, found Y instead", and ask. *This is the canonical failure this mode exists to prevent.*
4. **Repeated error.** If the same class of error recurs **3×** on the same sub-task, STOP. Do not keep trying variants — that is a doom loop and it burns context fast. Report the error, your current hypothesis, and what you would need to resolve it.
5. **Genuine fork.** When 2+ reasonable approaches exist AND picking wrong costs rework, stop and ask. State your confidence explicitly; do NOT fabricate an interpretation just to keep moving.

## Context discipline (be honest: you cannot reliably measure context)

You do **not** have a trustworthy gauge of how full the context window is, and these very instructions may be among the first things dropped when it compacts. So do not rely on "I'll notice it filling up":

- Every ~5 completed steps, or before a large sub-task, (re)write a checkpoint file **`SESSION.md`** in the project: current goal · files touched · decisions made · next step. This is your state *outside* the context window — it survives compaction.
- Redirect verbose command output to files; do not dump long logs into the conversation just to read them.
- The real gauge is the human's status line (context %). If asked to `/compact`, write the checkpoint first, then comply.

## Instruction vs enforcement (read this)

Everything above is **instruction** — you will try to honor it, but instruction is not a hard guarantee, especially under a full context or mid-loop. The **enforcement** layer is the hooks **bundled in this skill's frontmatter** — they activate automatically when this skill is engaged and are scoped to it (backed by the scripts in `hooks/`). Only the status line lives in `~/.claude/settings.json`:

- `block-broad-scan.py` (PreToolUse / Bash) — hard-blocks `find /`, `find ~`, broad recursive greps, and `rm -rf` on dangerous targets. Runs *before* the permission mode, so it holds even under acceptEdits / bypass. This is what actually enforces cross-check #3 (and the destructive half of #2).
- `error-circuit-breaker.sh` (PostToolUse + **PostToolUseFailure** / Bash) — uses the dedicated failure event to count consecutive failures per session and trips after a threshold (default 4). Backstop for cross-check #4.
- `precompact-checkpoint.sh` (PreCompact) — snapshots the transcript right before automatic compaction. Backstop for context discipline.
- `statusline-context.sh` — surfaces the live context % to the human (the real gauge for #context discipline).

If the hooks are not installed, treat the cross-checks as best-effort only, and lean toward pausing *more*, not less.

## Self-audit before "done"

Before declaring any step complete, run the four axes from daquele-jeito (functional / regression / hygiene / specification). "Done" is an auditable declaration, not a feeling.
