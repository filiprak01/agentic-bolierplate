# Docker Worker Requirements

Status: Release 1.1 requirements baseline for `AGENT-440`.

This document defines what future Docker workers need before the platform can
move from Codex session-mode execution to detached worker automation.

Release 1.1 documents and validates the requirements. Release 1.1 does not
implement fully autonomous detached Docker workers that spend Codex quota
without an active Product Owner-supervised Codex session boundary.

## Current Boundary

Release 1.1 supports:

1. Docker Compose services for API/runtime, Redis, Postgres, and role-specific
   dry-run workers.
2. Worker startup validation.
3. Durable worker registration and assignment polling.
4. Codex limit gate checks from durable operator-entered records.
5. Dry-run worker logs and assignment visibility.
6. Host-side Codex runner job/result/pause artifacts.

Release 1.1 does not support:

1. Detached in-container Codex UI or subscription automation.
2. Live autonomous Jira, GitHub, Confluence, AgileTest, or Codex writes from a
   Docker worker without a reviewed host/session boundary.
3. Shared mutable target-project checkouts for parallel implementation
   workers.

## Role Instruction Loading

Every worker must load instructions in this order:

1. Root `AGENTS.md`.
2. Role-specific instruction document.
3. Story context pack.
4. Assignment metadata.
5. Latest durable PO inbox answers and assumptions relevant to the story.

The instruction bundle must include:

1. Product Owner control rules.
2. Jira workflow and dependency rules.
3. Git branch and PR rules.
4. PO inbox stop conditions.
5. Codex limit gate behavior.
6. Evidence and documentation publication requirements.

Workers must treat instructions as read-only input. Runtime state belongs in
durable data folders, not in the instruction bundle.

## Context Pack Consumption

Each assignment must provide a context pack path.

The context pack should include:

1. Jira issue key, summary, type, status, labels, and acceptance criteria.
2. Dependency snapshot and linked bug snapshot.
3. Sprint and release metadata.
4. Role, model, reasoning, speed, and effort metadata.
5. Required source docs and architecture references.
6. Target repository path and branch name.
7. Durable output, evidence, failed request, and resume paths.
8. PO inbox references and answered decisions.

Workers must fail safe when the context pack is missing, malformed, stale, or
does not match the assignment Jira key.

## Execution Options

### Option A - Host-Side Codex Runner

The Docker worker creates durable Codex job files and waits for a host-side
runner to execute the Codex-backed work.

Use this option while Codex work depends on a Product Owner-supervised session
or local subscription boundary.

Required behavior:

1. Worker writes job request.
2. Host-side runner executes or simulates Codex work.
3. Runner writes result, partial result, pause, or failure artifact.
4. Worker resumes from durable artifacts.

### Option B - In-Container Execution Bridge

The Docker worker executes Codex work through a container-accessible execution
bridge.

This is later-release scope and requires separate Product Owner approval.

Required prerequisites:

1. Credential and subscription boundary approved.
2. No-secret logging verified.
3. Quota gate enforced before every Codex request.
4. PO inbox pause behavior verified.
5. Target workspace isolation verified.
6. Recovery after container restart verified.

### Option C - Dry-Run Worker

The Docker worker validates startup, assignment visibility, limit gates, and
logs without mutating assignments or external systems.

This remains the Release 1.1 validation baseline.

## Pause Conditions

A worker must pause safely when:

1. A blocking Product Owner question is created.
2. Codex limits are missing, stale, low, or unavailable.
3. Jira dependency checks fail.
4. A linked unresolved bug blocks the story.
5. A PR conflict or review-required change is detected.
6. Required configuration or credentials are missing.
7. Context pack or assignment data is invalid.
8. Target workspace cannot be allocated.
9. A worker lock is already active for the same Jira issue and role.

Pause behavior must preserve:

1. Assignment id and status.
2. Worker id and role.
3. Current Jira issue key.
4. Resume reason and recommended next action.
5. Failed request or partial output path when applicable.
6. Evidence and log paths.
7. Product Owner inbox item id when PO input is required.

## Shared And Isolated Paths

Shared durable coordination paths:

1. `data/po-inbox`.
2. `data/agent-logs`.
3. `data/agent-state`.
4. `data/codex-limits`.
5. `data/codex-jobs`.
6. `data/codex-results`.
7. `data/context-packs`.

Isolated per-assignment paths:

1. Target project workspace or Git worktree.
2. Assignment output path.
3. Assignment evidence path.
4. Failed request path.
5. Temporary tool output.

Parallel implementation workers must not share the same mutable target-project
checkout.

## External System Safety

Future live workers must use explicit adapters for:

1. Jira.
2. GitHub.
3. Confluence.
4. AgileTest.
5. Codex job execution.

Every adapter call must be traceable to:

1. Assignment id.
2. Jira issue key.
3. Worker id.
4. Role.
5. Product Owner-approved scope.
6. Evidence path.

No worker may silently create, transition, merge, publish, or delete external
state outside the configured project and assignment scope.

## Requirement Decisions

Open Product Owner decisions before live detached workers:

1. Whether the Codex execution bridge can use subscription-backed sessions or
   must use API-backed execution.
2. Whether each role needs a separate GitHub/Jira identity.
3. Whether workers may auto-start after Codex limit reset or only notify the
   Product Owner.
4. Whether parallel workers use Git worktrees by default or fresh clones by
   default.
5. How Confluence publication should be approved for client-facing reports.

These decisions do not block Release 1.1 dry-run validation.

Credential categories, mounted path categories, no-secret logging rules, target
repository boundaries, and Product Owner decisions are detailed in
`docs/docker-credential-volume-safety.md`.

Container image families, tag rules, registry variables, Artifactory-compatible
publishing, and local build-only behavior are detailed in
`docs/image-registry-publishing-baseline.md`.

The Release 1.2 architecture contract that turns these requirements into a
detached worker boundary is documented in
`docs/detached-docker-execution-architecture.md`.
