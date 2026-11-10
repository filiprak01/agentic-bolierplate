# Host Codex Supervisor

Status: Release 1.2 `RUN03` implementation contract for `AGENT-966`.

The Host Codex Supervisor is the host-side service boundary that processes one
queued Codex job at a time without requiring a pasted prompt in an active chat.
It sits above the `RUN01` host runner and below orchestration. It does not make
Product Owner, Jira acceptance, PR approval, merge, or Tester decisions.

## Responsibilities

The supervisor may:

1. Reject duplicate active host consumers when a Codex job is already running.
2. Claim one queued assignment and acquire one active assignment lock.
3. Refresh quota through `account/rateLimits/read` before dispatch when the
   operator entrypoint is used.
4. Re-run the `RUN02` host execution preflight before launch or resume.
5. Dispatch exactly one queued job through `HostSideCodexRunner`.
6. Persist runner result, logs, failed request, pause, checkpoint, and status
   artifacts before emitting a handoff event.
7. Block the next job if post-stage quota refresh fails or returns unknown
   state.
8. Report a redacted status snapshot for operator APIs and CLI wrappers.
9. In `run-loop` mode, keep polling on the configured interval after idle turns
   until stopped, blocked, or a bounded iteration limit is reached.

The supervisor must not:

1. Accept Jira issues, move work to `ACCEPTED/DONE`, approve PRs, merge PRs, or
   bypass Tester Agent evidence.
2. Resolve Product Owner questions through agent-to-agent messages.
3. Reuse a stale lock, foreign lock, stale context pack, blocked dependency, or
   missing accepted UI design reference.
4. Continue when quota evidence is missing, stale, ambiguous, limited, or not
   sourced from the host Codex App Server.
5. Mount or copy ChatGPT subscription credentials into worker containers.

## Entry Points

Run one bounded supervisor turn:

```bash
PYTHONPATH=src python scripts/runtime/run_host_codex_supervisor.py run-once --json
```

Run a bounded service loop:

```bash
PYTHONPATH=src python scripts/runtime/run_host_codex_supervisor.py run-loop --json --max-iterations 10
```

Run a continuous service loop that wakes at least every five minutes by default:

```bash
PYTHONPATH=src python scripts/runtime/run_host_codex_supervisor.py run-loop --json
```

Read the initial process status without claiming work:

```bash
PYTHONPATH=src python scripts/runtime/run_host_codex_supervisor.py status --json
```

The script reads `.env` by default and uses these configured roots unless an
explicit CLI override is provided:

1. `DURABLE_AGENT_STATE_PATH` for assignments, locks, checkpoints, and events.
2. `DURABLE_CODEX_JOBS_PATH` for queued Codex job envelopes.
3. `DURABLE_CODEX_RESULTS_PATH` for runner results and pause artifacts.
4. `DURABLE_CODEX_LIMITS_PATH` for quota observations.
5. `DURABLE_AGENT_LOGS_PATH` for supervisor and runner logs.
6. `AGENTIC_WORKSPACES_ROOT` for isolated assignment workspaces.

Use `--path-mapping source=host` when a container-visible durable path differs
from the host filesystem path. Execution fails closed when any output path or
workspace path cannot be resolved through explicit mappings.

## Codex CLI Compatibility

The child Codex process returns a structured final marker. The host runner
captures stdout/stderr and writes the durable result, logs and checkpoints.
Do not ask the child to write the host-owned result path outside its isolated
workspace or widen its sandbox merely to persist a result. Target-project
artifact permissions remain an explicit, separate execution boundary.

The host executor uses `codex exec --model ... --sandbox workspace-write`
and TOML configuration overrides for `model_reasoning_effort`,
`approval_policy`, and `forced_login_method="chatgpt"`. The default invocation
must not use obsolete `exec --reasoning` or `exec --ask-for-approval` flags.
The argument parser was checked against Codex CLI 0.162.1 without model
inference as part of AGENT-1045.

A successful exit uses the structured result marker when required; ordinary
discussion of quota/authentication is not a failure. Nonzero exits cannot be
overridden by a completed marker. A quota/authentication/permission failure is
classified from a failed process or an explicit structured failure result.

Keep subscription authentication on the host. `codex login status` confirms
the login mode, but only a successful live `account/rateLimits/read` establishes
that the cached credentials still work. If a matching Windows host cache is
used to repair WSL authentication, back up the old cache and protect both with
private permissions; never publish either or mount them into worker containers.

When using explicit account/bucket scopes, pass the same scope to refresh and
latest commands. A different account's unknown or stale record is not evidence
that the selected account is unavailable.

## Limit Flow

Before non-status work, the entrypoint calls the host Codex App Server and
normalizes `account/rateLimits/read` into a durable limit availability record.
If the app-server read fails, the script writes an `explicit_failure` unknown
record. RUN02 then blocks the job before any Codex subprocess launch.

After successful job reconciliation, the supervisor reads the App Server again.
If that post-stage refresh fails, it preserves the completed result and blocks
new work with `post_stage_limit_refresh_failed`. This prevents the service from
starting a second job using stale quota assumptions.

## Preflight Flow

Each launch or resume builds a `HostCodexPreflightRequest` and calls
`evaluate_host_codex_preflight`. The request includes:

1. The durable assignment.
2. The generated isolated workspace plan.
3. Observed checkout identity from the assignment/job scope.
4. Jira scope gates supplied by the orchestrator or operator wrapper.
5. The latest fresh quota observation.
6. Explicit host path mappings.
7. Permitted durable output roots.

When preflight blocks, the supervisor keeps the owned lock and records a
checkpoint with `RECHECK_GATES`. This lets the next pass re-check the same
assignment instead of reporting a false lost lease.

## Recovery Semantics

On startup, the supervisor reads persisted stores instead of trusting in-memory
state. It blocks when it sees:

1. Another running Codex job.
2. A queued Codex job without a matching assignment.
3. An assignment in progress without an active owned lease.
4. A foreign lock.
5. A failed or unsupported preflight decision.
6. Executor exception before a structured result.
7. Post-stage quota refresh failure.

Graceful stop before dispatch releases the owned lock with a cancelled reason
and writes a checkpoint. Work can resume only after gates are rechecked.

## Operator Status

`host_codex_supervisor_status_to_dict` exposes:

1. Service state and machine-readable reason.
2. Active job, assignment, worker, and child-session identifiers.
3. Heartbeat, next poll time, and latest blocking reason.
4. Preflight result and blocking reasons.
5. Pre-stage and post-stage quota observation IDs.
6. Checkpoint, event, result, log, and failed-request paths.

Status values are redacted before serialization and are safe for the local UI,
operator API, and Jira comments.

## Validation Scope

`tests/test_host_codex_supervisor.py` covers:

1. Claim, execute, reconcile, lock release, and event emission.
2. Duplicate active job rejection.
3. Preflight block retention of the owned lock for recheck.
4. Lost lease detection.
5. Executor exception persistence and redacted failure status.
6. Graceful stop after preflight before executor launch.
7. Post-stage quota refresh failure blocking follow-up work.
8. Continuous loop polling again after an idle turn until a stop, block, or
   bounded iteration limit occurs.

Live Codex availability still needs operator evidence because unit tests use a
fake executor and fake App Server payloads.
