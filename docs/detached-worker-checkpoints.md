# Detached Worker Checkpoints

Status: Release 1.2 implementation contract for `AGENT-622`.

Detached worker checkpoints are durable resume snapshots. They let a worker,
scheduler, or operator understand exactly where a role stopped without reading
chat history or reconstructing state from memory.

## Storage Boundary

Release 1.2 writes checkpoints to the configured agent state durable root:

```text
data/agent-state/detached-worker-checkpoints/{checkpoint_id}.json
```

The file store is the executable default because it works in local Docker
Compose with mounted volumes and survives container restart. A database schema
mirror is created in Alembic as `detached_worker_checkpoints` so a later
database-backed store can preserve the same contract without changing worker
or scheduler semantics.

## Required Fields

Every checkpoint stores:

1. Checkpoint id.
2. Assignment id.
3. Worker id.
4. Role.
5. Project id.
6. Sprint.
7. Jira issue key.
8. Branch name.
9. Worktree path.
10. Stage.
11. Last command summary.
12. Resume action.
13. Resume recommendation.
14. Created and updated timestamps.

Optional but supported fields:

1. Codex job id.
2. Context pack path.
3. Failed request path.
4. Output path.
5. Evidence path.
6. Resume-after timestamp.
7. Redacted field list.

## Stages

Supported stages:

1. `assignment_claimed`
2. `instructions_loaded`
3. `context_loaded`
4. `workspace_ready`
5. `limit_checked`
6. `codex_job_created`
7. `external_write_performed`
8. `handoff_emitted`
9. `paused_limit`
10. `blocked_po`
11. `failed`
12. `completed`

Workers must write a new checkpoint at each durable stop point that can affect
resume behavior. They must not silently skip from assignment claim to external
write without an intermediate checkpoint for context, workspace, and limit
gates.

## Resume Actions

Supported resume actions:

1. `none`
2. `recheck_gates`
3. `retry_last_command`
4. `rebuild_context`
5. `wait_for_limits`
6. `ask_product_owner`
7. `manual_recovery`

When the resume action is `wait_for_limits`, the checkpoint must include
`resume_after`. When the resume action is `ask_product_owner`, the checkpoint
must include an evidence path that points to the related inbox or handoff
artifact.

## Secret Handling

The file store redacts obvious Authorization headers, token/API token
assignments, password/secret assignments, OpenAI-style `sk-...` keys, and
standalone GitHub PAT-like values such as `github_pat_...` or `ghp_...` from
the last command and resume recommendation before writing JSON. Validation
messages only name the failing field and rule. They must not echo command text,
prompt content, Product Owner answers, token values, or raw `.env` data.

## Restart Flow

After a container restart, the worker or scheduler:

1. Reads the latest assignment.
2. Lists checkpoints for the assignment id.
3. Selects the newest checkpoint by `updated_at`.
4. Re-checks Jira status, dependency links, PO inbox blockers, workspace
   availability, credentials, context pack freshness, and Codex limits.
5. Applies the checkpoint resume action.
6. Writes a new checkpoint before the next external write or Codex request.

Workers must not resume under a different project id, Jira key, role, branch,
or context pack unless the Scheduler creates a new assignment.

## Database Mirror

The Alembic revision
`migrations/versions/20260809_0001_detached_worker_checkpoints.py` creates the
`detached_worker_checkpoints` table with the same fields as the file schema.

Database-backed persistence must remain a mirror of the domain schema:

1. Same checkpoint id.
2. Same assignment and worker identity.
3. Same project, sprint, Jira key, branch, and workspace fields.
4. Same resume action and recommendation.
5. Same redaction rules before persistence.

The database table does not replace the file store in this story. It prepares
the relational persistence path for later scaling and reporting work.

## Minimal Store Usage

```python
from agentic_boilerplate.storage import FileDetachedWorkerCheckpointStore

store = FileDetachedWorkerCheckpointStore("data/agent-state")
store.ensure_directories()

store.create(checkpoint)
latest_for_assignment = store.list_for_assignment("assignment-AGENT-622")[-1]
```

## Validation Contract

Required validation:

1. Domain checkpoints round trip to JSON-compatible data.
2. Paused or failed checkpoints require a failed request path.
3. Limit-wait checkpoints require a resume-after timestamp.
4. Store writes survive a new store instance, matching container restart
   behavior.
5. Store writes redact secret-like command and resume text.
6. Invalid checkpoint ids cannot escape the configured durable root.
7. The Alembic migration includes the same required checkpoint fields.
