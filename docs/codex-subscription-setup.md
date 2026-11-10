# Codex Subscription Setup

The MVP uses Codex through a host-side boundary. Workers persist structured job
requests and recovery artifacts locally, while the live Codex subscription and
model/reasoning selection remain controlled by the Product Owner in the active
Codex session.

## Role Routing

Default routing:

| Role | Model | Reasoning |
| --- | --- | --- |
| Orchestrator / PM / scheduler | `gpt-5.5` | high |
| Architecture | `gpt-5.5` | extra-high |
| Story / planning | `gpt-5.5` | extra-high |
| Development | `gpt-5.4` | high |
| Testing / automation | `gpt-5.4-mini` | high |
| Manual QA | `gpt-5.4-mini` | high |
| Code review | `gpt-5.4` | high |
| Release manager | `gpt-5.4-mini` | high |
| Docs/Confluence | `gpt-5.4-mini` | high |
| Frontend | `gpt-5.4` | high |
| UI/UX | `gpt-5.4` | high |
| Security | `gpt-5.5` | extra-high |
| DevOps/Platform | `gpt-5.4` | high |
| Data/Persistence | `gpt-5.4` | high |
| Refactor planner | `gpt-5.5` | high |
| Refactor worker | `gpt-5.4` | high |

No Release 1.1 role defaults to medium reasoning. Medium can be used only as a
Product Owner-approved limit-saving override for a specific story or sprint.

Extra-high reasoning is required for default Product Planning, Architecture,
and Security threat-model work because these roles shape cross-system behavior,
scope, and risk acceptance. Routine Security scan execution may be delegated to
`gpt-5.4` high when the Security Agent records that no threat-model decision or
risk acceptance is needed.

## Manual Switch Checkpoint

Codex cannot switch the active UI/session model automatically.

Before a worker starts a story, compare the story routing with the current
session. If the model or reasoning differs, the worker must ask the Product
Owner to switch manually before continuing.

## Shared Quota Guard Skill

Every role uses `.agents/skills/codex-quota-guard/SKILL.md` from the platform
repository before a quota-spending assignment, role switch, stage, retry, or
resume, and again after completion, failure, or checkpoint. The skill is
instruction-only glue over `agentic codex-limits refresh/latest`; it does not
replace the durable record model or parse subscription percentages itself.

When the current session has host Codex authentication, use live refresh with
the configured durable root, account scope id, and bucket id. Docker or hosted
workers without host auth request a host-owned guard decision and wait for the
fresh durable result. They must not receive `CODEX_HOME`, browser profiles,
access tokens, or other Codex login material.

Guard decisions are scoped to one project assignment and one configured quota
scope. Shared-account multi-project work may use the same account scope and
durable store, but each assignment must record its own project, issue, role,
stage, workspace, and selected bucket/window evidence. Project-specific memory,
credentials, and unresolved assumptions are never copied between projects.

## Runtime Model Discovery

Release 1.2 pairs the quota guard with runtime model discovery. Host-side
sessions and runners can call `CodexAppServerModelReader`, which initializes
Codex App Server over stdio and requests `model/list`. The result is normalized
into a model discovery snapshot and checked by `select_codex_model_route` before
work starts.

Use `docs/codex-model-routing.md` for the route sequence and env keys. The
runtime decision records model ids, display names, supported reasoning efforts,
default reasoning, optional separate limit bucket ids, route source, fallback
reason, and manual-switch requirement. It does not switch the active Codex
session automatically.

Spark (`gpt-5.3-codex-spark`) is optional and disabled by default. Enable it
only through configuration, only for allowlisted low-risk roles/complexities,
and only after `model/list` plus `account/rateLimits/read` confirm both model
support and a usable separate bucket. Product Planning, Architecture, and
Security fail closed when their configured model/reasoning is unavailable.

## Limit Windows

Codex limit displays are plan-dependent. The process supports three modes:

1. `dual_window` for a primary rolling window plus a secondary quota.
2. `single_pool` for one visible agentic usage or credit pool.
3. `dynamic` for app-server or future surfaces that expose labeled windows.

Workers should record observations with:

1. Remaining percent.
2. Reset time when known.
3. Observation source.
4. Recommended scheduler action.
5. Window labels and ids when available.
6. A non-secret account scope id and provider bucket id when multiple
   authenticated accounts or metered products share durable storage.

Recommended actions:

1. `resume` when the authoritative visible pool or both dual windows are
   available.
2. `wait` when the authoritative single pool or primary window is limited.
3. `downgrade_model` when secondary quota is low but primary work capacity is
   still available.
4. `ask_product_owner` when the authoritative visible value is unknown.

Use the current Codex product surface as the source of truth. If Pro shows one
agentic usage pool, record `--plan-mode single_pool` instead of inventing a
missing 5-hour window. Older Release 1.1 setups can mirror that same visible
pool into both legacy fields and include an operator note.

## False Unavailable Limit States

A missing or unavailable durable limit record is not automatically a subscription
quota problem. Before stopping a sprint for limits, verify the setup path:

1. The session command and Docker/API stack read the same `data/codex-limits`
   root.
2. Codex was opened through a working local path, not a failing WSL UNC path.
3. Python 3.11+ and `PYTHONPATH=src python -m agentic_boilerplate.cli` work
   from the same repository path.
4. The latest durable record source is supported and newer than the configured
   stale threshold.

Use `docs/windows-wsl-codex-runtime-troubleshooting.md` when limit commands look
unavailable but credentials and product usage are healthy. Classify a wrong
path as a `path` or `configuration` blocker, not as exhausted quota.

Official reference pages:

1. [Using Codex with your ChatGPT plan](https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan)
2. [Using Credits for Flexible Usage in ChatGPT](https://help.openai.com/en/articles/12642688-using-credits-for-flexible-usage-in-chatgpt-freegopluspro-sora)
3. [Codex rate card](https://help.openai.com/en/articles/20001106-codex-rate-card)

## Host-Side Limit Sentinel

Release 1.2 supports a safe host-side sentinel mode for limit refresh:

1. Codex stays authenticated on the Product Owner's host machine.
2. The sentinel calls `codex app-server` over stdio.
3. The sentinel reads `account/rateLimits/read`.
4. The response is normalized into durable `data/codex-limits` records.
5. Worker containers only consume durable limit records.

Required setup fields:

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

`CODEX_ACCESS_TOKEN` is optional and belongs only to trusted host-side
automation. Generic Docker workers must not receive Product Owner Codex
credentials.

`CODEX_LIMIT_ACCOUNT_SCOPE_ID` is a label such as `chatgpt-primary`, not an
email, token, account id, or other credential. All workers using the same
authenticated subscription and durable quota root must use the same value.
Use distinct values for distinct authenticated accounts. The selector fails
closed when an account or bucket is ambiguous.

Quota observations are append-only. A repeated explicit record id is accepted
only when its content is identical; conflicting reuse is rejected. Manual
`AVAILABLE` input cannot clear an existing authoritative provider block until
a newer provider observation confirms recovery. Each selected window must have
a valid timezone-aware timestamp, must satisfy the configured stale threshold,
and may be at most 30 seconds in the future by default.

## Pause And Resume

When limits are low or exhausted:

1. Stop issuing new Codex requests.
2. Save partial output.
3. Save logs.
4. Save failed request summary with secrets redacted.
5. Save paused assignment state.
6. Keep the Jira story in the correct lane.
7. Resume only after dependency/status eligibility is checked again.

At or below the configured 10% remaining checkpoint, workers save state and
wait. Reset time is only a suggested recheck time. The platform does not
automatically downgrade models, buy credits, consume reset credits, fall back
to an API key, or switch accounts when the gate is closed.

Use `agentic worker resume-paused` after capacity returns. The command reads
the durable limit gate, requeues resumable paused Codex jobs only when the gate
is open, and preserves checkpoint metadata for the next host-side runner pass.

Durable artifacts live under:

```text
data/codex-jobs
data/codex-results
data/agent-logs
data/context-packs
```

## Subscription Operating Rules

Use expensive routing where it protects quality:

1. Architecture and final release audits.
2. Security threat models.
3. Broad refactor planning.
4. Complex cross-role process decisions.

Use cheaper routing for repeated execution:

1. Test generation and logs.
2. Release notes.
3. Checklist execution.
4. Routine docs research.
5. Manual QA evidence writing.

Do not increase speed by default because it may increase token usage.

## Current AGENT-399 Setting

The Product Owner selected extra-high reasoning for this finalization pass.
That is justified because the work is a final release audit and handoff package
covering Docker readiness, repo orientation, and operational risk.
