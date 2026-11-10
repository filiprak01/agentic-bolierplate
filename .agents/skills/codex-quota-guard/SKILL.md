---
name: codex-quota-guard
description: Use the repository-scoped Codex quota guard before and after quota-spending agent work, using the existing agentic codex-limits refresh/latest contract without parsing percentages by hand.
metadata:
  short-description: Guard Codex quota before and after agent work
---

# Codex Quota Guard

Use this skill before a role starts or resumes a Jira assignment, role switch, bounded stage, retry, or other action that can spend Codex quota. Use it again after completion, failure, or a checkpoint once work/results are saved.

This skill is a thin adapter over the repository's existing `agentic codex-limits refresh` and `agentic codex-limits latest` contract. It must not become another hand-written percentage parser. Do not parse `/status`, `/usage`, browser text, percentages, reset banners, or raw App Server payloads by hand inside the skill. Let the shared CLI refresh, normalize, persist, select, and decide.

Model and reasoning selection is a separate companion decision. Pair this skill with `docs/codex-model-routing.md`, `CodexAppServerModelReader`, and `select_codex_model_route` when an agent needs to choose or verify a model route. The quota guard decides whether the selected bucket can spend; the model router decides whether the requested model and reasoning are available, configured, and safe for the role. Do not implement model discovery through copied prompt text, undocumented gRPC calls, UI scraping, or ad hoc parsing in this skill.

## Before Work

Run a live host-owned refresh when the session has host Codex auth:

```bash
agentic codex-limits refresh \
  --codex-limits-root <durable-codex-limits-root> \
  --account-scope-id <account-scope-id> \
  --bucket-id <bucket-id-if-configured>
```

Treat the refresh result as the gate. Exit code `0` means the selected fresh gate allows work. Exit code `2` means refresh succeeded but the selected gate blocks. Exit code `1` means refresh/protocol/persistence failed and an UNKNOWN observation was written; quota-spending work stays blocked.

If refresh is unavailable and a recent record must be checked, use `agentic codex-limits latest --json` with the same root, account scope, bucket, stale threshold, and clock settings. Inspect the exact returned `record.id`, `record.account_scope_id`, selected window or bucket identity, `gate.allowed`, `gate.action`, `gate.reason`, and `gate.resume_after`. Do not treat the command's zero exit code by itself as permission.

Hosted or Docker workers without host Codex authentication must ask the host-owned guard, scheduler, or Product Owner session for a fresh decision. They may read durable records and write checkpoints, but they must not mount `CODEX_HOME`, browser profiles, access tokens, or other Codex login folders into generic workers.

## Gate Rules

Missing, stale, invalid, limited, ambiguous account or bucket, or failed-refresh observations block quota-spending work. At or below the configured 10% remaining checkpoint, save state and wait. `resume_after` or reset time is only a recheck time, not permission to continue.

Do not automatically downgrade models, call another API surface, buy credits, consume reset credits, or reroute to a different account. Read-only quota rechecks and durable checkpoint/evidence writes are allowed while blocked. The quota reader itself must not recursively require quota admission.

Use unique generated record ids for retries unless replaying the exact same explicit id and payload for idempotency. Do not hide gate failures behind shell chaining, ignored return codes, or fallback `latest` reads that skip freshness and selector checks.

## After Work

After completion, failure, or a checkpoint, save the actual work and validation/result artifacts first. Then refresh again with the same configured root, account scope, and bucket. Persist a durable evidence note containing:

1. Observation or decision id and source.
2. UTC timestamp.
3. Environment, durable store path, account scope id, bucket/window identity, and selected record path when available.
4. Remaining percentage and reset/recheck time for the selected applicable window.
5. Gate action, allowed state, and reason.
6. Project, Jira issue, role, stage, workspace, branch, and commit/result references.

If the after-stage refresh fails, keep the completed work and evidence. Mark quota status as unknown, record the failure decision id, and block only the next quota-spending stage. Do not replay completed side effects just to refresh quota.

## Scope Boundaries

Session-mode checks are best-effort checkpoints performed between visible stages. They cannot interrupt every internal model request inside an already-running Codex turn, reserve quota for a whole story, or guarantee that remaining quota will last through the next stage.

Mandatory runtime enforcement still belongs in the host-side runner and scheduler gates that execute before a Codex request is issued. Background wakeups remain outside this skill and belong to `AGENT-966` and related runtime stories, not this skill alone.

## Cross-Workspace Loading

This is a repository-scoped shared skill. Sessions working in target-project worktrees must load it from the platform repository path, for example `<PLATFORM_REPO>/.agents/skills/codex-quota-guard/SKILL.md`, after loading `AGENTS.md` and the role file. Skill discovery in one repository does not automatically cross into unrelated repositories.

When moving between projects, keep only shared role/process instructions. Do not copy Codex credentials, target-project secrets, local account identifiers, unresolved assumptions, or project-specific memory with this skill. Reload the new project's context pack, durable roots, account scope, bucket configuration, Jira issue, and workspace identity before making a guard decision.
