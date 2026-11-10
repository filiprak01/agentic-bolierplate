# Codex Pause And Resume Artifacts

Codex pause artifacts let local workers stop safely when Codex limits,
container shutdown, or execution failures interrupt work.

They are built on top of the Codex job artifact schema documented in
`docs/codex-job-artifacts.md`.

The implementation lives in:

1. `agentic_boilerplate.domain.codex_pause`
2. `agentic_boilerplate.storage.codex_pause`
3. `agentic_boilerplate.domain.codex_limit_availability`
4. `agentic_boilerplate.storage.codex_limit_availability`

## Durable Folders

`FileCodexPauseStore` stores JSON files below the configured Codex jobs durable
directory.

Default folders:

1. `data/codex-jobs/paused-assignments`
2. `data/codex-jobs/failed-requests`
3. `data/codex-limits/limit-availability`
4. `data/agent-state/detached-worker-checkpoints`

Related artifacts may live in:

1. `data/context-packs`
2. `data/codex-results`
3. `data/agent-logs`

Workers must mount these folders as Docker volumes before doing Codex-backed
work.

## Pre-Request Limit Gate

Before a Docker worker accepts a queued assignment or the host-side runner
issues a Codex-backed request, the agent checks the latest Codex limit
availability record.

Closed gate actions:

1. `wait`
2. `downgrade_model`
3. `ask_product_owner`

When the gate is closed, workers do not mutate the queued assignment and the
host-side runner pauses jobs before the executor is called. Gate output includes
`resume_after` when a reset timestamp is known, so a Codex app automation,
thread reminder, or external scheduler can wake the process later.

## Limit Availability Record

Codex limit availability records capture the two quota windows that matter for
resume decisions:

1. Short rolling working window.
2. Broader weekly or monthly quota window.

Each window stores:

1. Availability status.
2. Remaining percent.
3. Reset datetime.
4. Observation source.
5. Observation timestamp.

Supported statuses:

1. `available`
2. `limited`
3. `unknown`

Supported sources:

1. `operator`
2. `codex_cli`
3. `browser_check`
4. `unknown`

The record also stores a recommended scheduler action:

1. `resume`
2. `wait`
3. `downgrade_model`
4. `ask_product_owner`

## Paused Assignment Artifact

A paused assignment captures the scheduler-visible state needed to resume work.

It includes:

1. Assignment ID.
2. Jira story or bug key.
3. Worker role.
4. Codex job ID.
5. Worker ID.
6. Branch name.
7. Context pack path.
8. Failed request path.
9. `paused_limit` status.
10. Pause reason.
11. Resume plan.
12. Pause and update timestamps.
13. Attempt count.
14. Linked partial outputs, logs, checkpoints, or failed request files.

Paused assignments must use `paused_limit` status and an attempt count of at
least `1`.

## Resume Plan

The resume plan identifies the minimum information needed to continue safely:

1. Original story key.
2. Worker role.
3. Codex job ID.
4. Context pack path.
5. Next action.
6. Optional note.

Supported next actions:

1. `retry_same_request`
2. `rebuild_context`
3. `ask_product_owner`
4. `manual_review`

The resume plan must point back to the same story, worker role, Codex job, and
context pack as the paused assignment. This prevents a scheduler from resuming
the wrong work after a container restart.

## Failed Request Artifact

A failed request artifact is the durable redacted summary of what failed.

It includes:

1. Failed request ID.
2. Codex job ID.
3. Jira issue key.
4. Worker role.
5. Pause/failure reason.
6. Failure timestamp.
7. Redacted request summary.
8. Redacted error summary.
9. Redacted field list.
10. Next action.
11. Optional raw request path.

Failed request summaries are redacted before persistence. The current redaction
rules mask obvious Authorization headers, token/API token assignments,
password/secret assignments, OpenAI-style `sk-...` keys, and standalone GitHub
PAT-like values such as `github_pat_...` or `ghp_...`.

Failed request artifacts also carry retry and restart visibility metadata:

1. `stage_id` - the durable worker or runner stage that failed.
2. `stdout_snippet` - redacted partial output useful for recovery.
3. `stderr_snippet` - redacted error output useful for recovery.
4. `retry_policy` - the retry rule, such as retry after limit reset or manual
   review before retry.
5. `suggested_next_role_action` - the next role handoff, such as scheduler
   retry, developer recovery, or operator configuration change.
6. `side_effect_idempotency_key` - the replay guard used to avoid duplicate
   Jira comments, GitHub PRs, transitions, or other external writes.

If an older artifact does not include an explicit idempotency key, operators
and workers derive a replay guard from Jira issue key, Codex job id, stage id,
and next action.

Validation and error messages must report field names and rule failures only.
They must not echo raw prompt text, token values, Product Owner answers, or
secret-like file names.

## Worker Pause Flow

When a worker detects a recoverable Codex limit:

1. Stop issuing new Codex requests.
2. Write any partial output to `data/codex-results`.
3. Write relevant logs to `data/agent-logs`.
4. Create a redacted failed request artifact.
5. Create a paused assignment artifact linked to the failed request, partial
   output, logs, and latest context pack.
6. Leave the Jira story or bug in its current development lane unless the work
   needs Product Owner input.
7. Persist enough context for the scheduler to resume later.

No live Codex execution is required to create or test these artifacts.

Detached worker checkpoints are defined in
`docs/detached-worker-checkpoints.md`. Pause artifacts reference checkpoints as
linked artifacts, while checkpoint records provide the broader assignment,
project, sprint, branch, worktree, stage, last command, failed request, and
resume recommendation needed for a worker or scheduler to resume after restart.

## Scheduler Resume Flow

When limits reset or the operator resumes workers:

1. Read the latest Codex limit availability record.
2. List paused assignments.
3. Check Jira dependency and status eligibility again.
4. Read the failed request artifact.
5. Read linked partial output, logs, and checkpoints.
6. Follow the limit availability recommendation and resume plan next action.
7. Update or replace the Codex job artifact before retrying.
8. If the next action is `ask_product_owner`, create a Product Owner inbox item
   and do not resume silently.

## Failed Request Status View

Operators and future UI shells can inspect failed requests without opening raw
artifact files:

```bash
agentic worker failed-requests
```

Use a mounted or isolated Codex jobs root when needed:

```bash
agentic worker failed-requests --codex-jobs-root data/codex-jobs
agentic worker failed-requests --codex-jobs-root data/codex-jobs --json
```

The text view lists failed request id, Jira issue, role, reason, next action,
retry policy, stage id, replay guard key, suggested next role action, and
failure timestamp. JSON output includes the same fields plus redacted snippets
for UI/runtime status views.

## Minimal Store Usage

```python
from agentic_boilerplate.storage import FileCodexPauseStore

store = FileCodexPauseStore("data/codex-jobs")
store.ensure_directories()

store.create_failed_request(failed_request)
store.create_paused_assignment(paused_assignment)

paused = store.read_paused_assignment("paused-AGENT-17-001")
```

## Testing Contract

The pause/resume implementation is local-only for this MVP stage.

Required validation:

1. Domain artifacts round trip to JSON-compatible data.
2. Paused assignments enforce `paused_limit` status and resume cross-references.
3. Failed request summaries are redacted before persistence.
4. Failed request metadata survives a new store/CLI read after restart.
5. Replay guard keys are stable for retry planning and can be explicit or
   derived for older artifacts.
6. Limit availability records cover available, limited, and unknown windows.
7. Limit availability recommendation logic covers resume, wait, downgrade, and
   ask-PO outcomes.
6. Store reads and lists durable JSON artifacts.
7. Invalid IDs and invalid schema files are rejected.
8. Tests do not require live Codex, Jira, GitHub, Confluence, or AgileTest.
