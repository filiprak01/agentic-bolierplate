# Worker Instruction And Context Loading

Status: Release 1.2 worker gate contract

This document defines how Docker workers and session-mode agents load the same
role instructions and story context without reconstructing prompts from chat.

## Required Instruction Bundle

Before a worker accepts an assignment, it must validate that these files are
available from the configured instruction root:

1. `AGENTS.md`, or `docs/reference/platform-agent-instructions.md` when the
   public-main auto-discovery entrypoint is absent
2. `ai_agents/roles/{role}.md`
3. `ai_agents/session_starters/README.md`
4. `docs/context-pack-generator.md`
5. `.agents/skills/codex-quota-guard/SKILL.md`
6. `docs/templates/target-project-AGENTS.md`

The public-main external-tool exception changes only automatic instruction
discovery. Explicit worker startup loads the resolved platform file and still
fails validation when both locations are missing. The original entrypoints
remain in `release/1.2.0` and `v1.2.0`; see
[external-tool mode](reference/external-tool-mode.md).

The worker log includes a redacted instruction checklist. It reports file
availability and path labels only. It must not read file contents into the log.

## Assignment Context Pack

When a queued assignment exists, the worker also validates
`assignment.paths.context_pack_path`.

Path resolution is deterministic:

1. Absolute paths are used as provided.
2. `data/context-packs/...` resolves under `DURABLE_CONTEXT_PACKS_PATH`.
3. `context-packs/...` also resolves under `DURABLE_CONTEXT_PACKS_PATH`.
4. Other relative paths resolve under the instruction root.

Missing context packs block the assignment before the worker claims it. The
assignment remains queued and the worker stays paused.

## Blocked Behavior

If any required instruction or context file is missing:

1. The worker registers itself as paused.
2. The queued assignment is left unchanged.
3. The worker log records `instruction_gate_allowed=false`.
4. The worker log records `instruction_gate_reason` with the missing check
   names.
5. The runtime result and JSON output expose the same fields for the CLI or UI.

This gate runs before the Codex limit gate for assignment work. That order
prevents spending or reserving Codex capacity when the worker lacks executable
context.

## Repository-Scoped Skills

The Codex quota guard is part of the platform instruction root, not the target
project checkout. Sessions running in separate target-project worktrees must
load `<PLATFORM_REPO>/.agents/skills/codex-quota-guard/SKILL.md` explicitly
after `AGENTS.md` and the role file. Skill discovery inside a target repository
does not automatically discover shared platform skills in unrelated checkouts.

Workers must keep the guard decision scoped to the assignment's configured
project identity, durable limit store, account scope, and bucket. Loading the
shared skill must not copy Codex login folders, tokens, browser profiles,
target-project secrets, unresolved assumptions, or project-specific memory into
another project.

## Target Project AGENTS.md

New target projects should copy:

```text
docs/templates/target-project-AGENTS.md
```

to:

```text
${TARGET_PROJECT_PATH}/AGENTS.md
```

and replace the project placeholders before workers start. The platform setup
validator reports whether the template is available.

The target-project `AGENTS.md` is project-specific guidance. It does not replace
the platform `AGENTS.md` or role files. Workers load the platform instruction
bundle and use the target-project file as project context when operating inside
the target checkout.
