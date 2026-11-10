# Codex Limit Availability

`AGENT-284` adds a durable record for Codex quota observations so workers can
distinguish the short rolling working window from the broader subscription
quota before resuming paused work.

`AGENT-409` makes those records enforceable before new Codex-backed work starts.
Workers and host-side runners must check the latest record before accepting a
queued assignment or issuing a Codex request.

`AGENT-666` generalizes those records so they support both legacy two-window
limits and newer subscription surfaces that show one agentic usage pool or
app-server-provided dynamic windows.

`AGENT-977` makes observation history immutable and safe under concurrent host
refreshes and worker reads. All consumers now use one account- and bucket-aware
selector instead of inferring recency from filenames or record ids.

`AGENT-976` adds the repository-scoped
`.agents/skills/codex-quota-guard/SKILL.md` adapter so every role has one
shared preflight and completion-check ritual. The skill does not parse Codex
percentages; it tells agents when and how to invoke the existing
`agentic codex-limits refresh/latest` contract.

## Why This Exists

Codex subscription limit surfaces can change by plan and product surface. Some
operators may see a short rolling window plus a broader quota. Others may see
one visible agentic usage or credit pool for supported agentic features.

Workers persist the visible windows locally because a Codex session can stop
before the next scheduler pass. A missing legacy 5-hour window must not block
work when the current plan exposes one authoritative pool instead.

Release 1.2 adds a host-side sentinel path for automatic refresh. The sentinel
runs on the Product Owner's host, where Codex is already authenticated, and
writes normalized records into durable storage. Generic worker containers read
the records; they do not receive Codex login folders, browser sessions, or raw
Codex credentials.

## Availability Model

Each record contains:

1. Record id.
2. Plan mode: `dual_window`, `single_pool`, or `dynamic`.
3. Legacy-compatible `short_window` and `broad_quota` fields.
4. A labeled `windows` list for the actual visible limit windows.
5. Recommended scheduler action.
6. Optional operator note.
7. A non-secret account scope id that identifies the authenticated Codex
   subscription context without storing login data.

Each window observation captures:

1. Status: `available`, `limited`, or `unknown`.
2. Remaining percent for known states.
3. Reset datetime for known states.
4. Observation source: `operator`, `codex_cli`, `browser_check`, or `unknown`.
5. Observation timestamp.
6. Window id and operator/provider label.
7. Whether the window is authoritative for a single-pool plan.
8. App Server bucket id, window name, and window duration when supplied.

Observation sources include `operator`, `codex_cli`, `codex_app_server`,
`offline_fixture`, `parsed_session_output`, `explicit_failure`,
`browser_check`, and `unknown`.

## Recommended Actions

The current action rules are intentionally conservative:

1. `resume` when the authoritative visible window or both legacy windows are
   available.
2. `wait` when the single pool or primary window is limited or at/below the
   stop threshold.
3. `downgrade_model` when the primary window is available but the secondary
   quota is limited or at/below the downgrade threshold.
4. `ask_product_owner` when the visible authoritative value is unknown.
5. Dynamic App Server records evaluate every window in the selected bucket;
   any limited, unknown, or at-threshold window prevents a new request.

Default thresholds:

1. Primary or single-pool stop threshold: `10%`.
2. Secondary quota downgrade threshold: `10%`.

These recommendations are enforceable gates for worker assignment and host-side
Codex execution. If the action is not `resume`, a worker must not start new
Codex-backed work.

## Pre-Request Gate

Before spending Codex quota, the agent or runner must:

1. Load `.agents/skills/codex-quota-guard/SKILL.md` from the platform
   repository instruction root.
2. Invoke live refresh through `agentic codex-limits refresh` when the current
   session or host runner has authenticated Codex access.
3. Pass the configured durable store, account scope id, and bucket id instead
   of relying on defaults when more than one scope can exist.
4. Treat refresh exit code `0` as allowed, `2` as refreshed-but-blocked, and
   `1` as failed refresh with a persisted UNKNOWN observation.
5. If a latest-record read is used after a refresh, inspect the exact selected
   `record.id`, account scope, bucket/window identity, `gate.allowed`, action,
   reason, reset/recheck time, and freshness result. The `latest` command's
   zero exit code alone is not permission to spend quota.
6. Stop when the gate says `wait`, `downgrade_model`, or
   `ask_product_owner`.

If no availability record exists, the MVP gate returns `ask_product_owner` and
blocks queued work. This prevents silent work starts when the Product Owner has
not confirmed the current Codex quota state.

When a stale threshold is supplied, the gate also blocks records whose latest
window observation is older than that threshold. Every selected window is
validated independently, so a fresh auxiliary window cannot hide a stale
authoritative window. Invalid timestamps and timestamps more than the
configured clock-skew tolerance in the future fail closed even when stale
checking is disabled. The default future tolerance is 30 seconds.

The latest-record selector applies these rules:

1. Filter by `CODEX_LIMIT_ACCOUNT_SCOPE_ID`, then by
   `CODEX_LIMIT_BUCKET_ID` when configured.
2. Preserve compatibility with legacy records that have the default account
   scope and no bucket metadata.
3. Reject ambiguous multi-account or multi-bucket data instead of choosing by
   map, filename, or write order.
4. Order observations by the oldest authoritative window timestamp in each
   snapshot.
5. Resolve equal-time observations toward the more restrictive action.
6. Do not let manual or offline `AVAILABLE` data clear an authoritative
   provider block. Recovery requires a newer authoritative provider read.
7. Treat a failed authoritative refresh as a scoped `UNKNOWN` observation so
   an older `AVAILABLE` snapshot cannot be reused.

The host-side Codex runner applies the same gate. If a job reaches the runner
while the gate is closed, the runner pauses the job before calling the Codex
executor and writes failed-request plus paused-assignment artifacts.

When a limit store is supplied, the host-side runner also writes a structured
limit-decision log before spending quota. The log includes model, reasoning,
speed, selected action, reset time, and the visible limit windows. This is the
evidence operators use to verify that a worker intentionally paused instead of
silently consuming the Product Owner's remaining capacity.

## Host-Side Sentinel Refresh

The safe automatic path is:

1. Product Owner logs into Codex on the host with subscription access.
2. The host sentinel starts or connects to `codex app-server`.
3. The sentinel calls `account/rateLimits/read` over JSON-RPC.
4. The response is normalized into labeled durable windows.
5. Session-mode agents and host runners use the quota guard skill to refresh
   and inspect the selected gate before and after visible quota-spending
   stages.
6. Generic workers without host authentication request a host-owned guard
   decision and read the durable result; they do not mount Codex login folders.

The stdio reader uses a live JSON-RPC session rather than an EOF batch. It:

1. Starts the configured executable and arguments directly without shell
   evaluation.
2. Sends `initialize` and waits for its correlated success response.
3. Sends the `initialized` notification, then sends
   `account/rateLimits/read` with a separate correlation id.
4. Keeps stdin open while it accepts interleaved notifications and waits for
   the matching result or error.
5. Applies bounded initialization, read, and total timeouts, supports caller
   cancellation, captures only bounded redacted diagnostics, and terminates and
   reaps only the child process created for that refresh.

The normalizer selects one applicable metered bucket without relying on map
order:

1. `--bucket-id` or `CODEX_LIMIT_BUCKET_ID` wins when explicitly set.
2. Otherwise, `rateLimits.limitId` identifies the App Server's
   backward-compatible active bucket.
3. A single map bucket is accepted when no other identity is available.
4. Multiple buckets without a verified identity, or a configured id that is
   absent, fail closed with an actionable configuration error.

Unselected buckets never participate in the gate. Within the selected bucket,
all returned window objects participate. Provider
`rateLimitReachedType`, `rateLimitReached`, and `spendControlReached`
signals block independently of percentage. A zero credit balance or available
reset credit does not change subscription-quota eligibility and never
authorizes reset redemption.

`usedPercent` must be a finite non-boolean number in `0..100`. Known
windows require a valid reset timestamp, and observation timestamps require a
timezone. Invalid or unsupported data produces a new sanitized UNKNOWN record;
it is never clamped or replaced by older AVAILABLE data.
Provider bucket ids, labels, and durable failure notes are bounded and passed
through the platform redactor before persistence.

Quoted executable paths are supported for Windows and WSL host commands. A
pre-split argument sequence is preferred for programmatic callers because it
does not require command-line parsing.

Configure the sentinel with:

```text
CODEX_LIMIT_SENTINEL_ENABLED=false
CODEX_LIMIT_SENTINEL_MODE=host_app_server
CODEX_LIMIT_APP_SERVER_COMMAND=codex app-server
CODEX_LIMIT_APP_SERVER_TRANSPORT=stdio
CODEX_LIMIT_ACCOUNT_SCOPE_ID=default
CODEX_LIMIT_BUCKET_ID=
CODEX_LIMIT_GUARD_CUTOFF_PERCENT=90
CODEX_LIMIT_STALE_AFTER_SECONDS=300
CODEX_LIMIT_FUTURE_TOLERANCE_SECONDS=30
CODEX_LIMIT_REFRESH_BEFORE_STAGE=true
CODEX_LIMIT_RECORD_SOURCE=codex_app_server
CODEX_ACCESS_TOKEN=
```

`CODEX_ACCESS_TOKEN` is optional and only for trusted host-side automation.
Do not mount it or `CODEX_HOME` into generic worker containers unless a later
security story explicitly approves that mode.

Refresh from the configured host-side app-server:

```bash
agentic codex-limits refresh
```

Select a non-default metered bucket explicitly when the active product cannot
be established from `rateLimits.limitId`:

```bash
agentic codex-limits refresh --bucket-id codex
```

Offline diagnostic refresh from a captured app-server-style payload:

```bash
agentic codex-limits refresh \
  --id availability-20260714T094500Z \
  --payload-json data/codex-limits/sample-rate-limits.json \
  --observed-at 2026-07-14T09:45:00Z
```

Offline payloads are stored with observation source `offline_fixture`;
they are distinguishable from live `codex_app_server` observations.

If app-server reading is unsupported, times out, or returns no usable windows,
the command writes an `ask_product_owner` unknown record and exits non-zero.
That preserves the manual fallback and prevents a worker from silently starting
with unverified capacity.

Machine-usable refresh exit codes are:

1. `0`: refreshed successfully and the resulting gate allows work.
2. `2`: refreshed successfully but the resulting limit gate blocks new work.
3. `1`: protocol, process, timeout, cancellation, payload, or persistence input
   failed; a sanitized UNKNOWN record was written and work remains blocked.

Refresh is the preferred preflight because it atomically reads the host-owned
App Server surface, writes the observation, re-selects through the common
account/bucket selector, and returns the selected gate. If an operator falls
back to `latest --json`, they must use the same account scope, bucket, stale,
and clock-tolerance configuration and must check the returned gate fields
explicitly. Do not shell-chain quota commands in a way that ignores non-zero
refresh results.

## Completion And Checkpoint Evidence

After a role completes, fails, or checkpoints a stage, save the actual work,
validation output, result artifact, or paused-state artifact first. Then refresh
Codex quota again with the same durable root, account scope, and bucket. Persist
a durable evidence note under the assignment's configured evidence path with:

1. Observation or decision id and source.
2. UTC timestamp.
3. Environment, durable store path, account scope id, bucket id, selected
   window id or label, and selected record path when available.
4. Remaining percentage and reset/recheck time for the selected applicable
   window.
5. Gate action, allowed state, and reason.
6. Project id/name/root, repository, Jira issue, role, stage, workspace,
   branch, and commit or result references.

If this after-stage refresh fails, the completed work stays saved. Record the
UNKNOWN observation or failure decision id, mark quota status unknown, and block
only the next quota-spending stage. Do not replay completed side effects simply
to obtain a later quota observation.

Read-only quota rechecks and durable checkpoint/evidence writes remain allowed
while quota is blocked. The quota reader itself is not subject to recursive
quota admission. Reset times are recheck times only; they are never permission
to resume without a fresh allowed gate plus normal Jira, dependency, PO inbox,
and lock checks.

## Durable Storage

The file-backed store writes JSON files below:

```text
data/codex-limits/limit-availability
```

Each file is an immutable observation event. Different generated observations,
including observations completed in the same second, receive collision-resistant
ids. Retrying the exact same explicit id and payload is idempotent; reusing that
id with different content is rejected. Atomic create semantics prevent
concurrent writers from silently replacing one another.

This lets the scheduler recover the newest applicable operator- or
provider-reported availability state after a container restart. Multiple
workers that share one authenticated account must use the same account scope
and durable root. Workers backed by different accounts or metered buckets must
use distinct scope values.

## Official Limit Context

The official Codex App Server contract documents
`account/rateLimits/read`, the backward-compatible `rateLimits` view,
`rateLimitsByLimitId`, bucket identity and labels, window duration and reset
fields, server-classified reached state, credits, and earned reset credits.

Reference pages:

1. [Codex App Server](https://learn.chatgpt.com/docs/app-server)

Treat the visible product surface as authoritative. Do not invent an absent
5-hour window when the current subscription exposes only one agentic pool.

## Usage

The platform supports operator-entered records such as:

1. A single visible agentic usage pool.
2. A primary rolling window and a secondary subscription quota.
3. App-server dynamic windows with operator labels.
4. Unknown reset time represented by `unknown` status rather than a guessed date.

Use Codex `/status` in the app or `/usage` in the CLI/TUI for an operator
view. Release 1.2 can read the authenticated host's values through App Server
and store them durably. Operator records remain the explicit fallback when the
automatic path fails closed.

Example low primary-window record:

```bash
agentic codex-limits record \
  --id availability-20260707T100000Z \
  --short-status available \
  --short-remaining 5 \
  --short-reset-at 2026-07-07T15:00:00Z \
  --broad-status available \
  --broad-remaining 80 \
  --broad-reset-at 2026-07-14T10:00:00Z \
  --note "PO observed Codex short window near exhaustion."
```

Operator-friendly aliases are also supported:

```bash
agentic codex-limits record \
  --id availability-20260711T080000Z \
  --five-hour-status available \
  --five-hour-remaining 95 \
  --five-hour-reset-at 2026-07-11T13:00:00Z \
  --weekly-status available \
  --weekly-remaining 99 \
  --weekly-reset-at 2026-07-18T08:00:00Z
```

Use the visible values for the active subscription. If Codex shows one
authoritative agentic usage pool, record it as a single-pool plan:

```bash
agentic codex-limits record \
  --id availability-20260714T094500Z \
  --plan-mode single_pool \
  --short-status available \
  --short-remaining 88 \
  --short-reset-at 2026-07-14T10:00:00Z \
  --short-window-id agentic_pool \
  --short-label "Agentic usage pool" \
  --source codex_cli \
  --note "PO observed one visible Codex agentic usage pool."
```

If a reset time or remaining percentage is not visible, record the
corresponding authoritative window as `unknown` instead of guessing.

## Release 1.1 Compatibility Workaround

Release 1.1 deployments that only understand `short_window` and `broad_quota`
can mirror a single visible agentic pool into both legacy fields and add an
operator note explaining that one pool was observed. Do not set an absent
5-hour window to `unknown` when that would incorrectly block work for a
single-pool Pro setup.

Check the latest gate:

```bash
agentic codex-limits latest --json
```

Select an explicit account and bucket when one durable root contains multiple
quota scopes:

```bash
agentic codex-limits latest \
  --account-scope-id chatgpt-primary \
  --bucket-id codex \
  --json
```

Check the latest gate with stale detection:

```bash
agentic codex-limits latest --stale-after-seconds 300
```

Read the latest capacity in an operator-friendly format:

```bash
agentic codex-limits status
```

Expected behavior for the example above:

1. Recommended action is `wait`.
2. Worker assignment gate is blocked.
3. `resume_after` is `2026-07-07T15:00:00Z`.
4. Product Owner or automation can schedule a wake-up for that timestamp.

## Alarm And Resume Scheduling

The boilerplate stores the resume/check time as `resume_after` in gate output
and pause artifacts. For the local Codex app, the Product Owner can create a
thread automation or reminder for that timestamp. For external schedulers, use
the same timestamp to restart worker polling or run a small resume command.

Release 1.2 adds a local resume scheduler command:

```bash
agentic worker resume-paused
```

The command:

1. Reads the latest durable Codex limit availability record.
2. Blocks and reports `next_check_at` when the gate is closed.
3. Requeues resumable `paused_limit` Codex jobs when the gate is open.
4. Preserves checkpoint metadata so the host runner can continue from the
   paused request rather than starting the story from scratch.
5. Can receive dependency-eligible Jira issue keys so blocked stories remain
   paused until their prerequisites are still valid.

Example with explicit eligibility:

```bash
agentic worker resume-paused \
  --eligible-issue-key AGENT-627 \
  --stale-after-seconds 300
```

Until an automatic Codex limit observer is implemented, alarm scheduling is
based on the operator-entered reset timestamp. Do not invent reset times when
Codex reports the window as unknown; record `unknown` and let the gate ask the
Product Owner.

The CLI does not scrape Codex status, browser UI, or subscription pages. The
operator reads those values manually and records them into the durable limit
store.
