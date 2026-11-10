# Host Execution Preflight

Status: implemented for `AGENT-965`

This document defines the fail-closed preflight that must run before any
host-side Codex executor launch or resume. It is intentionally separate from the
runner wiring so `RUN03` can attach it to the dispatcher without changing the
contract.

## Purpose

A generated workspace plan is not execution proof. Before Codex spends quota or
modifies a checkout, the host must confirm that the selected assignment still
matches the repository, branch, Jira scope, context, lock, PO/design gates and
fresh quota state.

## Required Inputs

`HostCodexPreflightRequest` contains:

1. The durable `AgentAssignment`.
2. The validated `AssignmentWorkspacePlan`.
3. The observed `HostCheckoutState` for an already provisioned host checkout.
4. The current `HostScopeState` from Jira, inbox, design, context and lock gates.
5. Fresh `HostCodexLimitRefreshEvidence` from the authenticated host App Server.
6. Explicit `HostPathMapping` entries for runtime path prefixes.
7. Permitted durable output roots.
8. Current UTC time and quota freshness policy.

## Fail-Closed Rules

The preflight blocks execution when any of these are true:

1. Workspace provisioning plan has unresolved issues.
2. Workspace path cannot be resolved through an explicit mapping.
3. Mapped path escapes its configured host prefix.
4. Resolved checkout is missing or lacks Git metadata.
5. Execution would reuse the shared source checkout instead of an isolated one.
6. Observed repository, branch, project, Jira issue or role does not match the assignment.
7. Output, Codex job, evidence or failed-request paths are missing mappings or outside permitted durable roots.
8. Jira status is no longer execution eligible.
9. Dependencies, blocking bugs, PO blockers or required UI design acceptance are unresolved.
10. Context revision is stale.
11. Assignment lock is absent or owned by another worker.
12. Quota evidence was not refreshed for this launch or resume.
13. Quota evidence did not come from `account/rateLimits/read` through the host App Server.
14. Quota record is missing, stale, malformed, ambiguous, provider-blocked or at/below the configured stop threshold.

No executor, model call, repository mutation or Jira success transition may run
from a blocked decision.

## Limit Evidence

The expected quota source is `CodexLimitObservationSource.CODEX_APP_SERVER`.
The decision persists the observation id, source, observed-at UTC value, account
scope, bucket id and resulting gate decision. This supports one-window and
multi-window plans; it does not assume a five-hour window.

## Output

`evaluate_host_codex_preflight` returns `HostCodexPreflightDecision` with:

1. `allowed`
2. structured issue list
3. resolved host workspace path
4. quota gate decision
5. quota observation metadata
6. assignment and PO inbox references

`render_host_codex_preflight_decision` renders the same data for durable logs,
PO inbox blockers, Jira comments or operator diagnostics.

## Runner Wiring Responsibility

`AGENT-965` provides the contract and focused tests. `RUN03` is responsible for
calling the preflight before launch and before resume, and for preventing the
host-side executor from running when the preflight is blocked.
