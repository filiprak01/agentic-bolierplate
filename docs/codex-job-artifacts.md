# Codex Job Artifacts

Codex jobs are durable JSON-compatible records used by local workers to hand
work to a host-side Codex runner and recover safely when a session, container,
or subscription limit interrupts execution.

The schema is implemented in
`agentic_boilerplate.domain.codex_job`.

## Purpose

Use Codex job artifacts when a worker needs Codex to perform implementation,
review, testing support, documentation, or recovery work.

The artifact is not the prompt itself. It is the durable envelope around the
request:

1. Which Jira issue owns the work.
2. Which agent role requested the work.
3. Which repository and branch should be used.
4. Where the context pack is stored.
5. Where outputs and checkpoints should be written.
6. Which model, reasoning, speed, and effort mode should be used.
7. Whether the job is queued, running, paused, failed, completed, or cancelled.
8. How the job can resume after a limit pause or failure.

## Storage

Default durable folders:

1. Job request envelopes: `data/codex-jobs`
2. Context packs: `data/context-packs`
3. Results and checkpoints: `data/codex-results`
4. Agent logs and test evidence: `data/agent-logs`

These paths are configured through the normal settings layer and should be
mounted as Docker volumes for local workers.

## Required Fields

Every job artifact must include:

1. `id`
2. `jira_issue_key`
3. `role`
4. `target_repo_path`
5. `branch_name`
6. `context_pack_path`
7. `output_path`
8. `model`
9. `reasoning`
10. `speed`
11. `effort_mode`
12. `status`
13. `created_at`
14. `updated_at`

`attempt_count` defaults to `0` and cannot be negative.

## Statuses

Supported statuses:

1. `queued`
2. `running`
3. `paused_limit`
4. `failed`
5. `completed`
6. `cancelled`

Terminal statuses:

1. `failed`
2. `completed`
3. `cancelled`

## Pause And Resume

When Codex reaches a usage limit, the worker must persist the job as
`paused_limit` before stopping.

Paused limit jobs must include:

1. `failed_request_path`
2. `resume.resumable = true`
3. Optional `resume.resume_after` when the next safe retry window is known.
4. Optional `resume.last_checkpoint_path` when partial output exists.
5. Optional `resume.last_error` with a concise failure summary.
6. Optional `resume.paused_at` timestamp.

The failed request artifact should contain enough non-secret context to retry
or explain the failed attempt. It should not contain raw tokens, credentials, or
unnecessary Product Owner answers.

## Failure Handling

Jobs with status `failed` must reference `failed_request_path`.

The failed request artifact should be durable and should include:

1. The failed operation summary.
2. The Jira issue key.
3. The worker role.
4. The last safe checkpoint path when one exists.
5. The next suggested action.

Validation messages must report field names and rule failures only. They must
not echo prompt content, Product Owner answers, token values, or secret-like
paths.

## Effort Modes

Supported effort modes:

1. `simple`
2. `standard`
3. `complex`
4. `audit`

Workers should choose effort mode from story complexity and current project
risk:

1. `simple` for low-risk setup or mechanical changes.
2. `standard` for normal implementation.
3. `complex` for cross-module behavior, harder debugging, or architecture
   implications.
4. `audit` for explicit broad review, security, or release-quality checks.

Do not increase Codex speed by default. Speed should remain `normal` unless the
Product Owner explicitly accepts the quota tradeoff.

## Minimal Example

```json
{
  "id": "codex-job-001",
  "jira_issue_key": "AGENT-16",
  "role": "developer",
  "target_repo_path": "/workspace/sample-project",
  "branch_name": "feature/AGENT-16-codex-job-artifact-schema",
  "context_pack_path": "data/context-packs/AGENT-16/context.json",
  "output_path": "data/codex-results/AGENT-16/result.json",
  "model": "gpt-5.5",
  "reasoning": "medium",
  "speed": "normal",
  "effort_mode": "standard",
  "status": "queued",
  "created_at": "2026-06-17T12:00:00Z",
  "updated_at": "2026-06-17T12:00:00Z",
  "attempt_count": 0,
  "failed_request_path": "",
  "resume": {
    "resumable": true,
    "resume_after": "",
    "last_checkpoint_path": "",
    "last_error": "",
    "paused_at": ""
  }
}
```

## Recovery Flow

1. Worker creates a queued job under `data/codex-jobs`.
2. Runner validates the artifact before execution.
3. Runner marks the job `running` and increments attempt metadata.
4. Runner writes outputs and checkpoints under `data/codex-results`.
5. If work completes, runner marks the job `completed`.
6. If a recoverable limit is reached, runner marks the job `paused_limit` and
   stores failed request metadata.
7. When limits reset, scheduler reloads paused jobs, checks Jira eligibility,
   and resumes from the latest checkpoint or context pack.
8. If the job cannot resume, runner marks it `failed` and references the failed
   request artifact.

The Product Owner inbox remains the source for business questions. Codex job
artifacts are operational records, not a replacement for PO decisions.
