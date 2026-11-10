# Live Codex Operator Status API

`AGENT-978` exposes the Codex subscription auth and quota state through the
local operator API. This is the agent-facing contract for the UI and workers
that need an up-to-date gate before starting Codex-backed work.

## Scope

The operator API owns live access to Codex. Generic workers read the operator
API and durable records. Workers must not mount host Codex login folders,
browser sessions, or raw Codex credentials.

The implementation keeps two paths:

1. `POST /codex-limits/refresh` performs a live host-owned refresh.
2. `GET /codex-limits` reads the cached/latest durable record.

The cached path remains valid when live refresh fails. A failed live refresh
writes a fresh UNKNOWN record and blocks new quota-spending work.

## Live Refresh

`POST /codex-limits/refresh` starts the configured Codex App Server command and
uses JSON-RPC in this order:

1. `initialize`
2. `initialized`
3. `account/read`
4. `account/rateLimits/read`

The response is accepted only when `account/read` confirms ChatGPT
subscription-backed authentication. API-key, missing, expired, signed-out, or
ambiguous auth fails closed.

A successful refresh persists a normalized `codex_app_server` limit record and
returns the selected gate. A blocked provider window, stale or unsupported
payload, ambiguous bucket, or gateway failure returns a safe blocked response
with a persisted UNKNOWN record.

## Returned Fields

Consumers must read the gate from the returned body, not only the HTTP status.

Required body fields:

1. `latest_record`
2. `gate.allowed`, `gate.action`, `gate.reason`, and optional
   `gate.resume_after`
3. `canStartWork`
4. `blocking_reason`
5. `windows[]`
6. `live_refresh.status`, `source`, `record_id`, and `observed_at`
7. `auth.subscription_auth`, `auth.account_type`, `auth.plan_type`, and
   `auth.reason`
8. `provider.bucket_id`, `provider.plan_type`, provider reached state,
   spend-control state, and reset-credit count when supplied by Codex
9. `location.record_id` and safe durable record path

Each window should include:

1. `bucket_id`
2. `window_id`
3. `window_name`
4. `window_duration_minutes` and `windowDurationMins`
5. `remaining_percent` and `remainingPercent`
6. `usedPercent`
7. `reset_at` and `resetsAt`
8. `observation_source`
9. `observed_at`

## UI Behavior

The operator UI displays cached data by default and exposes a separate live
check action. It must show blocked live responses as operator-readable state,
not as a generic fetch failure, when the API returns a safe snapshot.

Manual atomic updates stay available as fallback when the live gateway cannot
read Codex. Manual values must still be saved as durable records and selected
through the same gate.

## Worker Behavior

Before starting a story, stage, review, test pass, regression, or release task
that may spend Codex quota, a worker must:

1. Ask the operator API for a fresh live refresh when the configured worker mode
   supports it.
2. Fall back to `GET /codex-limits` only when live refresh is unavailable or
   the worker is intentionally cache-only.
3. Stop when `canStartWork` is false or `gate.allowed` is false.
4. Record the selected record id, gate action, reason, bucket/window identity,
   remaining percent, reset time, model, reasoning, and Jira issue in evidence.

Workers may continue read-only inspection and durable checkpoint writes while
blocked. They must not start a new quota-spending request until a newer allowed
record exists.

## Configuration

The live API uses the existing Codex limit settings:

```text
CODEX_LIMIT_APP_SERVER_COMMAND=codex app-server
CODEX_LIMIT_ACCOUNT_SCOPE_ID=default
CODEX_LIMIT_BUCKET_ID=
CODEX_LIMIT_GUARD_CUTOFF_PERCENT=90
CODEX_LIMIT_STALE_AFTER_SECONDS=300
CODEX_LIMIT_FUTURE_TOLERANCE_SECONDS=30
```

Use `CODEX_LIMIT_BUCKET_ID` when the App Server exposes multiple buckets and
the active Codex bucket cannot be inferred safely.
