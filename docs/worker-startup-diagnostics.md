# Worker Startup Diagnostics

Worker startup diagnostics are the deterministic preflight run before a role worker registers, claims, resumes, or creates a host-side Codex job. The check is intentionally conservative: a worker may create known durable directories, but it must not repair credentials, Git history, Jira workflow, Product Owner decisions, or unknown project paths.

## Startup Readiness States

| State | Meaning | Worker action |
| --- | --- | --- |
| `ready` | All blocking checks passed. | Register, check assignment eligibility, then continue through instruction, limit, workspace, and lock gates. |
| `degraded` | Non-blocking warnings exist, such as skipped live connector probes. | Continue only when the requested worker mode allows skipped live probes; record the warning in logs. |
| `blocked` | One or more blocker checks failed. | Do not claim or resume assignments. Write redacted diagnostics and wait for operator or Product Owner action. |

The startup payload must remain redaction-safe. It may include check names, categories, remediation text, and repair action names. It must not include token values, private key values, cookies, raw authorization headers, or full secret-bearing command lines.

## Diagnostic Categories

Startup diagnostics classify failures into stable categories so the Orchestrator, operator UI, and PO inbox can route them consistently:

| Category | Examples | Automatic repair allowed |
| --- | --- | --- |
| `authentication` | Jira 401, GitHub credential missing, Codex API token configured where subscription auth is required. | No. Requires credential or login action. |
| `authorization` | GitHub org SSO missing, Jira permission denied, connector 403. | No. Requires scope, SSO, or app authorization action. |
| `connector_state` | Connector not installed, stale connector session, live probe skipped. | No direct repair; reconnect or reinstall connector. |
| `network` | Timeout, DNS failure, temporary service connection error. | Bounded retry only. Persist diagnostic if still failing. |
| `configuration` | Missing env value, unsupported documentation provider, invalid worker role. | No silent business-default repair. Update config. |
| `path` | Missing target project path, UNC WSL helper failure, symlink durable path, mismatched PO inbox root, mismatched Codex limit root, unwritable volume. | Only create configured missing durable directories under validated roots. |
| `schema_migration` | Runtime store layout missing or migration needed. | Only run approved idempotent migrations. |
| `service_health` | Local CLI/module unavailable, wrong Python executable, unsupported Python version, service probe failed. | No secret or system package repair unless explicitly implemented as safe setup. |
| `role_bootstrap` | Missing role files, AGENTS.md, context-pack workflow, session starters. | No. Fix the repo or mounted instruction bundle. |
| `repository` | Target project is not a Git checkout, unknown repo, wrong branch base, alias resolves to copied repo instead of canonical checkout. | No. Clone/mount/open the correct repository. |
| `codex_gateway` | Unsupported gateway mode, missing app-server command, wrong transport, host App Server unavailable. | No. Fix host-side Codex setup. |
| `assignment_recovery` | Stale lock, interrupted assignment, checkpoint mismatch. | Only after ownership checks and explicit release/mark-stale commands. |

## Windows WSL Path And Python Checks

On Windows, a Codex session opened directly from a WSL UNC path can fail before
local shell startup. The Product Owner validated that opening Codex through a
Windows directory alias/junction path can unblock the same repository without
moving it.

Before startup diagnostics report Jira, GitHub, Codex quota, or PO inbox as
unavailable, workers and operators should verify the path layer described in
`docs/windows-wsl-codex-runtime-troubleshooting.md`:

1. Codex is opened through the validated Windows alias path when UNC execution
   fails.
2. `git rev-parse --show-toplevel` resolves to the canonical target checkout.
3. `git remote -v` matches the configured repository.
4. Python 3.11+ is available to the session command used for `agentic`.
5. Source-mode commands use `PYTHONPATH=src` when the package is not installed.
6. `data/po-inbox` and `data/codex-limits` resolve to the same durable mount as
   the Docker/API stack.

A false missing-limit record caused by reading the wrong durable path must be
classified as `path` or `configuration`, not as exhausted Codex quota.

## Allowlisted Startup Repairs

The startup validator may perform only these bounded idempotent repairs:

1. Create configured missing durable directories under the validated durable roots.
2. Create PO inbox status directories under the configured PO inbox root.
3. Ensure runtime state-store directories for assignments, locks, and Codex limit records.
4. Retry transient dependency checks with bounded backoff when a caller provides live probes.
5. Clear stale process metadata only through dedicated ownership-aware recovery commands.

All repairs must be recorded as repair actions in the diagnostic payload. If a repair fails, the worker stops before claiming work.

## Manual Repair Blockers

A worker must stop and create a durable PO inbox or operator diagnostic for these cases:

1. Jira, GitHub, Confluence, Figma, AgileTest, registry, or connector 401/403 failures.
2. Missing token scopes, GitHub organization SSO authorization, or invalid app installation state.
3. Unknown repository, missing Git metadata, unexpected default branch, or unsafe Git history changes.
4. Unapproved Jira workflow/status changes or unsupported issue-type mappings.
5. Missing Product Owner decision, rejected design, missing acceptance criteria, or ambiguous target path.
6. Symlink escapes, durable path outside the approved mount, or arbitrary host-path repair.
7. Any action that would write credentials, rotate secrets, alter branch protection, or bypass review gates.
8. UNC WSL helper failures that require the operator to reopen Codex through a Windows alias path.
9. Python runtime upgrades or PATH changes required to run the platform CLI.

## Startup Message Construction

Docker workers and host-side runner requests must construct the first role message from deterministic inputs:

1. Root `AGENTS.md`.
2. Matching `ai_agents/roles/{role}.md` file.
3. Assignment context pack path.
4. Project identity and Jira project key.
5. Jira issue key and repository.
6. Worker id/session id.

The Product Owner should not need to paste role instructions into each worker. If the worker cannot build this message from configured files, it creates a PO inbox blocker instead of inventing missing process rules.

## Operator Commands

Validate setup before starting workers:

```bash
agentic setup validate --project-root . --codex-limits-root data/codex-limits
```

Check the durable Codex limit record used by workers:

```bash
agentic codex-limits latest
```

When running from source without installing the package:

```bash
PYTHONPATH=src python -m agentic_boilerplate.cli setup validate --project-root . --codex-limits-root data/codex-limits
PYTHONPATH=src python -m agentic_boilerplate.cli codex-limits latest --json --codex-limits-root data/codex-limits
```

Run one worker loop with startup diagnostics:

```bash
agentic worker run-once --role developer --check-integrations
```

Inspect blocked or paused assignments:

```bash
agentic worker status --assignment-store-root data/agent-state --json
```

Inspect PO inbox blockers:

```bash
agentic po-inbox list --status open
```

## Subscription Codex Boundary

Workers must use ChatGPT subscription-backed Codex through the host-side boundary, not an API token, unless a future release explicitly enables API-paid execution for a project.

Host setup:

```bash
codex login
codex login status
codex app-server
```

The limit sentinel reads `account/rateLimits/read` from the local Codex App Server and writes a durable Codex limit availability record before workers spend Codex quota. If `CODEX_ACCESS_TOKEN` is set while subscription gateway mode is enabled, startup blocks because the worker would be configured for the wrong billing/auth boundary.

## Evidence Expectations

For each startup-gated story, evidence should include:

1. Startup diagnostic pass/fail summary.
2. Any repair actions performed.
3. Limit gate decision before Codex work.
4. Instruction/context gate result.
5. Workspace and assignment-lock gate result.
6. Redacted connector/auth diagnostics if a probe fails.
7. Path alias, canonical repository, Python executable, PO inbox root, and Codex limit root evidence when running on Windows/WSL.
8. Command or CI evidence that tests covered clean startup, safe repair, idempotent rerun, missing CLI/path, connector 401/403, unavailable PO inbox/API, transient recovery, stale metadata, interrupted assignment recovery, and secret redaction.
