# Jira Dependency Eligibility Checker

The scheduler uses the dependency eligibility checker before assigning a Jira
story to a worker.

## Input

The checker consumes `JiraIssueDependencyLinks` from the Jira adapter.

The adapter preserves:

1. Blocks / is blocked by issue keys.
2. Linked blocker issue snapshots when Jira returns summary, type, status, and
   labels.
3. Linked Bug issue snapshots from Jira issue links.
4. Downstream issues blocked by the current issue.

Only Jira `Blocks` links decide prerequisite order. Other link types can still
surface linked Bugs, but they do not become prerequisite links.

## Jira Blocks Direction Contract

For `blocker_key blocks blocked_key`, Jira Cloud issue-link payloads use:

```json
{
  "type": {"name": "Blocks"},
  "inwardIssue": {"key": "blocker_key"},
  "outwardIssue": {"key": "blocked_key"}
}
```

Raw Jira readback is interpreted from the issue being queried:

1. `inwardIssue` is a prerequisite that blocks the current issue.
2. `outwardIssue` is a downstream issue blocked by the current issue.

Canonical example for all agents and scripts:

```text
If X depends on Y, create Y blocks X.
```

Do not invert this to `X blocks Y`. If a link looks reversed, report the exact
link direction and proposed correction; do not perform a blanket reversal.

Cloud fixtures must model raw Jira responses directly. Do not generate parser
fixtures with the same link-creation implementation because matching direction
errors can hide each other. The mock adapter exposes the same blocker and
downstream semantics as the cloud adapter.

Support tasks for regression, retro intake, closure, release documentation, or
finalization can use `Blocks` links for closure sequencing. Those links must not
silently make delivery stories look development-blocked. When a blocker issue
has the configured support-task label, the checker flags it as a support-task
warning and does not count it as a delivery prerequisite.

## Sprint Graph Audit

Single-issue eligibility is not enough for sprint closure. Before scheduler
assignment and before sprint regression/closure, the Orchestrator or Release
Manager should audit the whole active sprint dependency graph using canonical
`blocker -> blocked` notation.

The audit must stop the process when it finds:

1. A reciprocal `Blocks` relationship such as `A -> B` and `B -> A`.
2. A longer dependency cycle such as `A -> B -> C -> A`.
3. A likely reversed live link where the story description, sprint plan, or
   dependency table says `X depends on Y` but Jira stores `X -> Y` instead of
   `Y -> X`.

When a graph issue exists, the affected agent must write a durable blocker or
PO inbox item and avoid guessing the intended direction. Historical links are
corrected one-by-one only after explicit evidence or Product Owner
confirmation.

Sprint regression and closure stay blocked while unresolved dependency cycles
or reversed live `Blocks` links remain in the active sprint scope.

## Eligibility Rules

A story is normally eligible when:

1. All prerequisite blockers are in a satisfied development-unblocking status.
2. No linked Bug remains unresolved.
3. Jira status and PO approval rules have already allowed the story into the
   schedulable scope.

Default satisfied prerequisite statuses:

```text
TEST COMPLETED
ACCEPTED/DONE
```

Default resolved Bug statuses:

```text
TEST COMPLETED
ACCEPTED/DONE
```

Unknown prerequisite status is treated as blocked so the scheduler does not
start work from incomplete Jira data.

## Override

The checker supports an explicit override for exceptional Product Owner or
Release Manager decisions.

An override is valid only when:

1. `allow_override` is true.
2. A non-empty override reason is provided.

The durable note records that assignment was overridden and keeps the reason.

## Durable Notes

Before assignment, the scheduler should write the result with
`write_dependency_eligibility_note`.

The note records:

1. Issue key.
2. Eligibility result.
3. Override use and reason.
4. Blocking items.
5. Satisfied prerequisites.
6. Support-task link warnings.
7. Sprint graph audit status when the assignment came from an active sprint
   queue.

These notes belong in durable worker storage so a stopped container can resume
without losing the dependency decision that led to assignment.