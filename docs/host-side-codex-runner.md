# Host-Side Codex Runner Boundary

Status: implemented for `AGENT-43`, extended for bounded subprocess execution in `AGENT-964`, and supervised through `RUN03` in `AGENT-966`

The host-side runner boundary lets local or Docker workers request Codex-backed
work through durable job files. The MVP boundary is fakeable in tests, and
Release 1.2 adds a concrete host-side subprocess executor for one bounded Codex
stage while keeping detached Docker execution outside the worker container.

## Components

`FileCodexJobStore` stores one `job.json` per Codex job under the configured
Codex jobs root.

It supports:

1. Creating new job artifacts.
2. Reading existing jobs.
3. Updating job status and metadata.
4. Listing all jobs.
5. Listing queued jobs ready for the runner.

`HostSideCodexRunner` reads queued jobs from the store and passes one job at a
time to a `CodexRunnerExecutor` protocol implementation.

`HostSideCodexExecutionBridge` is the worker-facing adapter. A Docker worker
uses it after assignment, context, credential, and limit gates pass. The bridge
creates a queued `CodexJobArtifact`, updates the `AgentAssignment` with the
worker id and Codex job id, and leaves actual Codex execution to the host-side
runner.

The executor request includes:

1. Jira issue key.
2. Worker role.
3. Target repository path.
4. Branch name.
5. Context pack path.
6. Model.
7. Reasoning.
8. Speed.
9. Effort mode.
10. Output path.
11. Attempt count.

## Bounded Subprocess Executor

`SubprocessCodexRunnerExecutor` is the first concrete implementation behind the
`CodexRunnerExecutor` protocol. It executes one host-side Codex CLI stage using
structured subprocess arguments, not shell string interpolation.

The subprocess executor:

1. Runs in the configured target repository working directory.
2. Passes model, reasoning, sandbox, approval policy, role, Jira issue, branch,
   context pack, and output path into the Codex invocation.
3. Requires host ChatGPT subscription authentication by default.
4. Removes inherited OpenAI API-key style environment variables from the child
   process and blocks explicit API-key overrides when subscription mode is
   required.
5. Applies a per-stage timeout and cancellation boundary, then terminates or
   kills the child process before returning a result.
6. Supports an optional structured output marker:
   `AGENTIC_CODEX_RESULT_JSON: {"status":"completed","summary":"..."}`.
7. Redacts secret-like values before returning output, logs, or error summaries
   to durable runner storage.

The executor distinguishes these result categories:

1. `completed`
2. `quota_exhausted`
3. `authentication_blocked`
4. `permission_blocked`
5. `timeout`
6. `cancelled`
7. `malformed_output`
8. `process_failed`

A process exit code alone is not enough to mark Jira work accepted, tested, or
merged. Jira transitions still follow the story lifecycle, PR review, CI, and
Tester Agent evidence gates.

## Job Outcomes

On success, the runner:

1. Marks the job `running`.
2. Writes the executor result JSON.
3. Writes the runner log.
4. Marks the job `completed`.

On a configured limit marker, the runner:

1. Writes partial result and log files.
2. Creates a redacted failed request artifact with stage id, stdout/stderr
   snippets, retry policy, suggested next role action, failure category, and
   side-effect idempotency key.
3. Creates a paused assignment artifact.
4. Marks the job `paused_limit`.
5. Records resume metadata, including checkpoint path and optional retry time.

On a non-limit execution failure, the runner:

1. Writes partial result and log files.
2. Creates a failed request artifact with replay guard metadata and failure
   category.
3. Marks the job `failed`.

## Release 1.2 Boundary

The boundary now supports executing one bounded host-side Codex subprocess from
a queued job. It still does not mount Codex login folders into worker
containers, copy ChatGPT session secrets, or let a Docker worker spend Codex
quota directly.

Tests use transcript fakes for success, timeout, malformed output, quota
exhaustion, expired authentication, denied permission, cancellation, and
redaction. A live Codex execution must still be separately evidenced in a story
or operator run, because transcript tests prove classification and persistence,
not external Codex availability.

## Quota Guard Relationship

The session-mode `codex-quota-guard` skill is a best-effort stage ritual for
human-supervised Codex sessions. Mandatory runtime enforcement remains here and
in the scheduler: before the runner calls a `CodexRunnerExecutor`, it must use
the durable limit store's selected latest record and fail closed when the gate
is missing, stale, invalid, limited, or ambiguous.

A host runner with Codex authentication may perform the live refresh before it
selects the gate. A Docker or hosted worker without that auth must request the
host-owned guard decision and wait for the durable result instead of mounting
Codex login folders or copying tokens into the worker.

After a job completes, fails, or checkpoints, the runner saves result, log,
failed-request, or pause artifacts first. A post-stage refresh failure records
quota as unknown and blocks the next Codex request, but it does not invalidate
or replay the completed side effects.

## Host Execution Preflight

`HostCodexPreflightRequest` and `evaluate_host_codex_preflight` live in
`agentic_boilerplate.runtime.host_execution_preflight`. They provide the
fail-closed launch/resume decision introduced by `AGENT-965`.

The preflight validates explicit host path mappings, isolated checkout
existence, repository identity, feature branch, Jira project/issue, role,
permitted output roots, current workflow eligibility, dependency and bug gates,
PO blockers, accepted UI design if required, context freshness, assignment-lock
ownership, and fresh `account/rateLimits/read` quota evidence from the host App
Server.

A generated workspace provisioning plan is not enough to start execution. If the
preflight blocks, no Codex subprocess, model call, repository mutation, or Jira
success transition may occur. `RUN03` owns wiring this preflight into launch and
resume orchestration.

Full contract: `docs/host-execution-preflight.md`.

## Host Supervisor

`HostCodexSupervisor` is the `RUN03` service layer documented in
`docs/host-codex-supervisor.md`. It wraps `HostSideCodexRunner` with assignment
claiming, duplicate-consumer rejection, assignment-lock ownership, RUN02
preflight enforcement, graceful stop handling, checkpoint persistence,
post-stage quota refresh, and durable orchestration event emission.

Operator entrypoints live in `scripts/runtime/run_host_codex_supervisor.py`:

```bash
PYTHONPATH=src python scripts/runtime/run_host_codex_supervisor.py run-once --json
PYTHONPATH=src python scripts/runtime/run_host_codex_supervisor.py run-loop --json --max-iterations 10
PYTHONPATH=src python scripts/runtime/run_host_codex_supervisor.py status --json
```

A supervisor result means one runtime stage reached a durable stop point. It is
not a Jira acceptance decision, a PR approval, a merge approval, or Tester
sign-off.

## Worker Request Flow

When a worker accepts an assignment in live mode:

1. The worker validates startup, role, instruction/context, dependency, and a
   fresh quota guard decision from the configured durable limit store.
2. The worker calls `HostSideCodexExecutionBridge` in `host_side` mode.
3. The bridge creates or reuses a queued job under the configured Codex jobs
   durable root.
4. The bridge updates the assignment to `assigned` with the worker id and Codex
   job id.
5. The host supervisor processes the queued job and writes result, log, failed
   request, pause, checkpoint, completion artifact, or blocked status.
6. Follow-up agents resume only from durable orchestration events and Jira state.

Direct in-container Codex execution is explicitly unsupported in this release.
If selected, the bridge writes a failed request artifact, marks the assignment
`failed`, and returns an operator-readable reason that explains the host-side
boundary.

Before promoting a role into this runner boundary, validate the role in
session mode with `docs/session-mode-validation-playbook.md`. The playbook keeps
role prompts, expected outputs, stop conditions, and Docker requirement findings
visible while live Codex execution remains Product Owner supervised.
