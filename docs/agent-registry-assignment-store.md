# Agent Registry And Assignment Store

The agent registry and assignment store tracks worker instances, Jira
assignments, and durable work state for scheduler and recovery workflows.

## Domain Objects

`WorkerInstance` represents one worker process or container.

Important fields:

1. `id`
2. `role`
3. `status`
4. `container_name`
5. `workspace_path`
6. `current_assignment_id`

`AgentAssignment` represents one Jira issue assignment to one role.

Important fields:

1. `jira_issue_key`
2. `role`
3. `status`
4. `worker_id`
5. `codex_job_id`
6. `branch_name`
7. `paths`
8. `stack_metadata`

`stack_metadata` is optional for normal stories. For stacked PR stories it
persists the scheduler's resolved execution path so workers do not reinterpret
the sprint graph independently.

Required stacked assignment fields:

1. `stack_id`
2. `lane_id`
3. `stack_mode`
4. `resolved_path_version`
5. `current_layer`
6. `expected_next_agent`

Operational state:

1. `stale_state` records why a stacked assignment needs refresh, such as parent
   branch rebased, parent PR merged, or child branch behind expected base.
2. `rebase_required` is true when the next worker must rebase or recreate the
   branch before continuing.

If `rebase_required` is true, `stale_state` must be present. If stack metadata
is absent, empty, or all fields are blank/default, the assignment remains a
normal non-stacked assignment.

`AssignmentPaths` keeps durable locations needed for resume and audit:

1. `context_pack_path`
2. `codex_job_path`
3. `output_path`
4. `evidence_path`
5. `failed_request_path`

## Assignment Lifecycle

Supported assignment statuses:

```text
queued
assigned
in_progress
paused_limit
failed
completed
cancelled
```

Normal scheduler flow:

1. Create a queued assignment after Jira dependency and status checks pass.
   Copy stack metadata from the approved context pack when the story is
   `stacked-dependent`.
2. Assign a worker and Codex job id.
3. Move the assignment into progress when the worker starts.
4. Complete the assignment with output and evidence paths.

Limit pause flow:

1. Move an assigned or in-progress assignment to `paused_limit`.
2. Record `pause_reason`.
3. Record `failed_request_path`.
4. Keep assignment state durable so a later worker window can resume.

Failure flow:

1. Move assignment to `failed`.
2. Record `failure_reason`.
3. Keep output, failed request, or evidence paths when available.

## File Store

`FileAgentAssignmentStore` writes JSON artifacts under a durable root:

```text
agent-registries/
agent-assignments/
agent-workers/
```

The store supports:

1. Create, save, read, and list registries.
2. Create, save, read, and list assignments.
3. Create, save, read, and list workers.
4. Deterministic safe file paths.
5. Duplicate-create protection.
6. Missing artifact errors.
7. Atomic JSON writes.

The file-backed store is the MVP durability layer. It is intentionally shaped so
the same domain objects can later be persisted by a database-backed store.
