# Docker Worker Readiness

This matrix answers the Product Owner question: can MVP agents run as Docker
workers with controlled volumes, configuration, and logs?

## Short Answer

Yes for controlled role-specific dry-run workers.

AGENT-404 adds Docker worker services for every MVP role and a shared worker
entrypoint that:

1. Runs startup validation before accepting work.
2. Registers worker state in durable local storage.
3. Polls queued durable assignments for the configured role.
4. Writes role-specific logs under `data/agent-logs`.
5. Reads Codex limit availability records before accepting queued work.
6. Blocks queued assignments when the latest limit gate recommends `wait`,
   `downgrade_model`, or `ask_product_owner`.
7. Leaves assignments unchanged in dry-run mode so no work is lost.
8. Runs continuously in Docker with `AGENTIC_WORKER_POLL_INTERVAL_SECONDS`
   controlling the polling interval.

Polling is the Release 1.1 readiness baseline. Future trigger-driven handoff
requirements are documented in `docs/docker-worker-triggering.md`.

Live Codex-backed execution remains delegated to the host-side Codex runner
boundary. Docker workers prove controlled background startup and assignment
visibility without making live GitHub, Jira, Confluence, AgileTest, or Codex
calls during dry-run validation.

Release 1.2 adds the worker-facing
`HostSideCodexExecutionBridge`. In non-dry-run mode the Docker worker can create
a durable queued Codex job for the host-side runner after gates pass. The worker
still does not mount Codex subscription/session secrets or run unsupported
direct in-container Codex automation.

AGENT-625 adds a bounded one-assignment worker command contract. Each
`agentic worker run-once` invocation exits after at most one assignment and
writes:

1. Assignment and worker state under `data/agent-state`.
2. Detached worker checkpoints under
   `data/agent-state/detached-worker-checkpoints`.
3. Worker logs under `data/agent-logs/<role>/<worker-id>.log`.
4. Assignment evidence under
   `data/agent-logs/<role>/<assignment-id>/worker-run-evidence.json`.
5. Host-side Codex job requests under `data/codex-jobs` when `--execute`
   runs in `host_side` mode.
6. Failed request artifacts when an unsupported execution mode is selected.

Release 1.2 adds assignment-lock enforcement to the worker claim path. Before
live execution creates a host-side Codex job, `agentic worker run-once` checks
the active assignment lock for the Jira issue and role. If another worker owns
an active lock, the worker stays paused, leaves the assignment queued, writes
`assignment_lock_allowed=false` to JSON output, logs, evidence, and checkpoint
context, and exits without creating a Codex job.

Live `--execute` mode creates or reuses one active lock for the claiming worker.
The lock stores Jira issue key, role, worker session id, status, acquired and
updated timestamps, target workspace path, and expiry timestamp derived from
the stale-lock policy. Dry-run mode checks for conflicting active locks but
does not create a new lock, so operator validation cannot accidentally reserve
work.

Release 1.2 also adds assignment workspace provisioning validation before lock
claim and Codex job creation. `agentic worker run-once` builds an isolated
workspace plan for the queued assignment using `AGENTIC_WORKSPACES_ROOT`, the
target project mount, configured repository, assignment branch, and shared
durable paths. If the target repository, Git metadata, repository, credentials,
feature branch, or durable path placement is invalid, the worker stays paused,
leaves the assignment queued, writes `workspace_gate_allowed=false` to JSON
output, logs, evidence, and checkpoint context, and exits without claiming the
assignment.

Stale lock recovery is intentional. Runtime workers do not silently replace
active stale locks. Operators must use:

```bash
agentic worker locks mark-stale --checked-at <timestamp> --stale-after-seconds <seconds>
agentic worker locks release --jira-issue-key <key> --role <role> --worker-session-id <id> --released-at <timestamp> --reason stale_replaced --audit-note <note> --confirm --allow-active
```

The lock listing command is the operator/UI data source:

```bash
agentic worker locks list --lock-store-root data/agent-state
```

It prints the Jira issue, role, owner, status, updated timestamp, workspace
path, expiry, release reason, and audit note.

Future detached worker requirements are documented in
`docs/docker-worker-requirements.md`. The Release 1.2 execution boundary and
safety contract are documented in
`docs/detached-docker-execution-architecture.md`. Together these documents
define role instruction loading, context pack consumption, execution options,
pause behavior, path isolation, external system safety, security constraints,
checkpoint ownership, termination behavior, and resume semantics.

Image registry and Artifactory-compatible publishing rules are documented in
`docs/image-registry-publishing-baseline.md`. Dockerized operator API/UI and
worker-image stories must use that baseline for image names, tags, and
credential safety.

Docker Git SSH authentication for worker-side clone, push, and PR branch update
flows is documented in `docs/docker-git-ssh-auth.md`. Session-mode Codex work
continues to favor HTTPS/token auth, while Docker workers can opt into SSH by
setting `GITHUB_AUTH_MODE=ssh` and providing either a read-only mounted key file
or an environment-provided key value.

The concrete detached worker checkpoint schema and file store are documented in
`docs/detached-worker-checkpoints.md`. Checkpoints are written under
`data/agent-state/detached-worker-checkpoints` and are mirrored by the
`detached_worker_checkpoints` Alembic schema for later database-backed
persistence.

Detached worker credential, logging, volume, and external-write security
constraints are documented in `docs/detached-worker-security-review.md`. Worker
implementation stories that follow this foundation must satisfy that review
before the detached worker pilot runs against a target project.

The executable instruction bundle and assignment context gate are documented in
`docs/worker-instruction-context-loading.md`. Docker workers validate that
`AGENTS.md`, the matching `ai_agents/roles/{role}.md` file, session starters,
the context-pack workflow, the target-project `AGENTS.md` template, and the
queued assignment context pack exist before the assignment can be claimed.

Parallel workspace isolation for session-mode agents and future Docker workers
is documented in `docs/parallel-agent-workspaces.md`. That design defines the
default local Git worktree option, the fresh-clone option for long-running
workers, copied snapshots for non-mutating validation, and the rule that
parallel implementation workers must not share one mutable target-project
checkout.

Session-mode role validation is documented in
`docs/session-mode-validation-playbook.md`. Findings from that playbook feed
future Docker requirements and backlog stories before the behavior is promoted
from supervised Codex sessions into worker automation.

## Current Docker Services

| Service | Status | Purpose | Persistent Data | Notes |
| --- | --- | --- | --- | --- |
| `api` | present | API/runtime shell | `./data:/workspace/data` | Keeps the platform image available for local runtime checks. |
| `worker` | present | Compatibility platform worker | `./data:/workspace/data` | Runs the platform role dry-run worker loop. |
| `worker-product-planning` | present | Product Planning worker | `./data:/workspace/data` | Profile: `workers`, `product-planning`. |
| `worker-architecture` | present | Architecture worker | `./data:/workspace/data` | Profile: `workers`, `architecture`. |
| `worker-developer` | present | Developer worker | `./data:/workspace/data` | Profile: `workers`, `developer`. |
| `worker-review` | present | Review worker | `./data:/workspace/data` | Profile: `workers`, `review`. |
| `worker-tester` | present | Tester worker | `./data:/workspace/data` | Profile: `workers`, `tester`. |
| `worker-release-manager` | present | Release Manager worker | `./data:/workspace/data` | Profile: `workers`, `release-manager`. |
| `worker-scheduler` | present | Scheduler worker | `./data:/workspace/data` | Profile: `workers`, `scheduler`. |
| `worker-platform` | present | Platform worker | `./data:/workspace/data` | Profile: `workers`, `platform`. |
| `worker-frontend` | present | Frontend worker | `./data:/workspace/data` | Profile: `workers`, `frontend`. |
| `worker-ui-ux` | present | UI/UX worker | `./data:/workspace/data` | Profile: `workers`, `ui-ux`. |
| `worker-security` | present | Security worker | `./data:/workspace/data` | Profile: `workers`, `security`. |
| `worker-docs-confluence` | present | Docs/Confluence worker | `./data:/workspace/data` | Profile: `workers`, `docs-confluence`. |
| `worker-devops-platform` | present | DevOps/Platform worker | `./data:/workspace/data` | Profile: `workers`, `devops-platform`. |
| `worker-data-persistence` | present | Data/Persistence worker | `./data:/workspace/data` | Profile: `workers`, `data-persistence`. |
| `postgres` | present | Future relational persistence | `postgres-data` | Health checked. |
| `redis` | present | Future queue/cache layer | `redis-data` | Append-only persistence enabled. |

All agent worker services also mount `${TARGET_PROJECT_PATH:-.}` to
`/workspace/project` so the target project path is configurable per project.

For future parallel implementation workers, `/workspace/project` must point to
the configured target repository source used to provision the assignment's
isolated workspace. The worker writes assignment workspace plans under
`AGENTIC_WORKSPACES_ROOT`, which defaults to
`/workspace/data/agent-workspaces` in Docker Compose. Shared coordination data
remains mounted separately under `/workspace/data`.

## Worker Role Matrix

| Role | Domain workflow implemented | Default worker role | Docker dry-run worker | Live Codex execution in container |
| --- | --- | --- | --- | --- |
| `product_planning` | yes | yes | yes | host-runner delegated |
| `architecture` | yes | yes | yes | host-runner delegated |
| `developer` | yes | yes | yes | host-runner delegated |
| `review` | yes | yes | yes | host-runner delegated |
| `tester` | yes | yes | yes | host-runner delegated |
| `release_manager` | yes | yes | yes | host-runner delegated |
| `scheduler` | yes | yes | yes | host-runner delegated |
| `platform` | yes | yes | yes | host-runner delegated |
| `frontend` | yes | yes | yes | host-runner delegated |
| `ui_ux` | yes | yes | yes | host-runner delegated |
| `security` | yes | yes | yes | host-runner delegated |
| `docs_confluence` | yes | yes | yes | host-runner delegated |
| `devops_platform` | yes | yes | yes | host-runner delegated |
| `data_persistence` | yes | yes | yes | host-runner delegated |

## Required Control Points

Every worker container has:

1. A role set through `AGENTIC_SERVICE_ROLE`.
2. Access to `.env` values.
3. `./data:/workspace/data` mounted for durable recovery.
4. `${TARGET_PROJECT_PATH:-.}:/workspace/project` mounted for target-project
   access.
5. Logs written under `data/agent-logs/<role>/`.
6. Worker registry and assignment state written under `data/agent-state`.
7. Codex job/result paths configured under `data/codex-jobs` and
   `data/codex-results`.
8. Codex limit records read from `data/codex-limits` before Codex-backed work.
9. Platform role instructions and story context packs validated before queued
   assignments are accepted.
10. Detached worker checkpoints written under `data/agent-state` before durable
    resume or handoff points.
11. Redacted Git SSH runtime metadata when `GITHUB_AUTH_MODE=ssh`, including
    selected key source, SSH remote URL, and a redacted `GIT_SSH_COMMAND`.
12. Workspace provisioning gate output containing `workspace_path`,
    `workspace_gate_allowed`, `workspace_gate_reason`, and the redacted
    non-destructive command plan.

Startup validation now requires `TARGET_PROJECT_PATH` to be configured and to
resolve to an existing directory before workers accept assignments. This keeps
the Compose fallback from silently turning the boilerplate repository into the
target project workspace.

## Codex Limit Gate

When a queued assignment exists, the worker reads the latest record from
`data/codex-limits/limit-availability` and computes a gate decision.

If the gate is closed:

1. The worker stays `paused`.
2. The queued assignment remains unchanged.
3. The worker log includes `limit_action`, `limit_gate_reason`, and
   `resume_after`.
4. The assignment evidence records the gate decision.
5. A detached worker checkpoint records the resume action, such as
   `wait_for_limits` or `ask_product_owner`.
6. The scheduler or Product Owner can use `resume_after` to create a Codex app
   automation, reminder, or external wake-up.

If no limit record exists, the MVP gate blocks queued work with
`ask_product_owner`. This makes the absence of quota context visible instead of
starting a new Codex request silently.

## Instruction And Context Gate

Before checking Codex limits for a queued assignment, the worker validates the
instruction bundle and assignment context pack:

```text
AGENTS.md
ai_agents/roles/{role}.md
ai_agents/session_starters/README.md
docs/context-pack-generator.md
docs/templates/target-project-AGENTS.md
assignment.paths.context_pack_path
```

If the gate fails, the worker remains `paused`, leaves the assignment queued,
and writes `instruction_gate_allowed=false` plus a redacted
`instruction_gate_reason` to the worker log, assignment evidence, checkpoint,
and JSON output.

## Workspace Provisioning Gate

After context and Codex limit gates pass, the worker validates the assignment
workspace plan before assignment lock claim:

```text
assignment.paths.workspace_path or {AGENTIC_WORKSPACES_ROOT}/{project_key}/{jira_issue_key}/{role}
assignment.project_root or /workspace/project
assignment.repository or GITHUB_REPOSITORY
assignment.branch_name
shared durable paths under /workspace/data
Git credentials from HTTPS token or SSH runtime
```

If the gate passes, live `--execute` creates the assignment lock and host-side
Codex job against the isolated assignment workspace path, not the shared source
mount. If the gate fails, the worker writes a `workspace_ready` checkpoint with
`recheck_gates` as the resume action and does not create a Codex job.

## Assignment Status Visibility

Operators, schedulers, and future UI shells can inspect paused or blocked
assignments through one shared command:

```bash
agentic worker status
```

Use an explicit store root when checking a mounted or isolated worker state
directory:

```bash
agentic worker status --assignment-store-root data/agent-state
```

The readable output lists only assignments that need action:

1. `paused_limit` assignments are shown as `paused`.
2. `paused_po` assignments are shown as `blocked` with a
   `blocked-by-PO-inbox` reason and inbox item id in JSON output.
3. `failed` assignments are shown as `blocked`.
4. Each row includes Jira issue key, role, assignment status, redacted reason,
   and a recommended next action.
5. Secret-like free text is redacted before it is printed.

Future operator UI work should consume the same payload instead of rebuilding
assignment status rules:

```bash
agentic worker status --assignment-store-root data/agent-state --json
```

The JSON response is shaped as:

```json
{
  "items": [
    {
      "assignment_id": "assignment-AGENT-501",
      "jira_issue_key": "AGENT-501",
      "role": "developer",
      "status": "paused_limit",
      "category": "paused",
      "reason": "5-hour Codex limit below threshold",
      "recommended_next_action": "Record updated Codex limit availability, then rerun or resume the worker assignment.",
      "worker_id": "developer-1",
      "branch_name": "feature/AGENT-501-example",
      "codex_job_id": "codex-job-AGENT-501",
      "attempt_count": 1
    }
  ]
}
```

Failed Codex request artifacts have their own restart visibility command:

```bash
agentic worker failed-requests --codex-jobs-root data/codex-jobs
agentic worker failed-requests --codex-jobs-root data/codex-jobs --json
```

This view exposes redacted stage, retry policy, replay guard, and suggested
next role action data so a retry can avoid duplicating Jira comments, GitHub
PRs, transitions, or other external side effects.

## Product Owner Inbox Pause And Resume

When a worker cannot continue without Product Owner input, it must create a
durable PO inbox blocker and pause the related assignment instead of keeping
the question only in logs or chat:

```bash
agentic --inbox-root data/po-inbox \
  worker pause-for-po \
  --assignment-store-root data/agent-state \
  --assignment-id assignment-AGENT-628 \
  --worker-id developer-1 \
  --project-id AP \
  --question "Which retry behavior should the worker use?" \
  --response-needed "Select retry policy before continuing." \
  --resume-context "Continue from the original context pack after the PO answer."
```

The command records:

1. A `blocking_question` PO inbox item with project id, assignment id, role,
   Jira issue, question, response need, and resume context.
2. A JSON resume context under
   `data/agent-state/po-inbox-resume-contexts/`.
3. The inbox item id and resume context path on the assignment.
4. Assignment status `paused_po`.

After the Product Owner answers or approves the inbox item, the orchestrator
must re-check normal gates before requeueing:

```bash
agentic --inbox-root data/po-inbox \
  worker resume-po-inbox \
  --assignment-store-root data/agent-state \
  --eligible-issue-key AGENT-628
```

The JSON form emits `po_resume_instruction` records for requeued assignments.
Open items, missing items, rejected decisions, and assignments whose Jira issue
is not listed as eligible remain paused with a PO-visible reason. Rejections or
scope-changing answers should create Product Planning or Architecture follow-up
work instead of silently continuing.

## Run Commands

Validate Compose for all worker profiles:

```bash
docker compose --profile workers config --quiet
```

Start the base platform services:

```bash
docker compose up --build -d api worker postgres redis
```

Run one bounded dry-run assignment for a role:

```bash
agentic worker run-once --role developer
```

Create a host-side Codex job request for one assignment after all gates pass:

```bash
agentic worker run-once --role developer --execute --codex-execution-mode host_side
```

The direct container mode is intentionally explicit and fails safely in this
release:

```bash
agentic worker run-once --role developer --execute --codex-execution-mode direct_container
```

Use explicit roots when testing mounted worker data:

```bash
agentic worker run-once \
  --role developer \
  --assignment-store-root data/agent-state \
  --checkpoint-store-root data/agent-state \
  --limit-store-root data/codex-limits \
  --logs-root data/agent-logs
```

Start all role-specific dry-run workers:

```bash
docker compose --profile workers up --build -d
```

Run one worker locally without Docker:

```bash
agentic worker run-once --role developer --worker-id developer-1
```

The local `run-once` command is intentionally single-cycle for validation and
manual debugging. Docker worker containers wrap it in a polling loop.

When `run-once` is executed with live mode in later orchestration stories, it
creates a host-side Codex job instead of executing Codex directly inside the
worker container.

## Release Position

For Release 1.2 handoff:

1. Docker foundation is present and validated.
2. Role-specific Docker worker services exist for all configured roles.
3. Workers can start in dry-run mode, validate startup, register state, poll
   durable assignments, and write evidence logs.
4. Live autonomous Codex execution is intentionally still controlled by the
   host-side runner boundary until Product Owner approves a later containerized
   execution story.
