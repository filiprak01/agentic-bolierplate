# Delivery State Consistency Guard

The delivery state consistency guard protects sprint regression and closure
from Jira, GitHub, review, testing, and Product Owner acceptance drifting out
of sync.

## Purpose

The guard checks that a sprint Story or Bug is not shown as more complete than
the implementation and testing evidence supports.

It also checks the reverse problem: a pull request can be merged to `main`
while Jira still shows the Story or Bug before the review handoff status.

## Inputs

For each Story or Bug in the sprint, the Release Manager or orchestration layer
collects:

1. Jira issue key, issue type, summary, and current status.
2. Linked pull request URL and pull request lifecycle state.
3. Review approval state.
4. Tester validation outcome.
5. Durable test evidence paths.
6. Product Owner batch acceptance state.
7. Optional documented blocker when a temporary mismatch is intentional.

## Blocking Findings

The guard blocks sprint closure when it finds:

1. `accepted-before-merge`
2. `accepted-without-review-approval`
3. `accepted-without-test-completion`
4. `accepted-without-test-evidence`
5. `accepted-without-po-batch-acceptance`
6. `test-completed-before-merge`
7. `test-completed-without-evidence`
8. `merged-but-jira-not-advanced`
9. `merged-without-approved-review`

## Closure Rule

`ACCEPTED/DONE` requires:

1. The linked pull request is merged.
2. Review approval is recorded.
3. Tester validation passed.
4. Durable test evidence exists.
5. Product Owner batch acceptance is recorded.

Merge to `main` should leave or move the Story or Bug at `DEV COMPLETED` with a
`test_requested` handoff. Tester Agent then moves it to `IN TESTING` when
validation starts. If the issue stays in `READY TO START` or `IN PROGRESS`,
the guard reports `merged-but-jira-not-advanced`.

## Outputs

The guard produces:

1. A sprint-level report with clean issues and blocking findings.
2. A Jira-ready comment for regression or retro/closure Tasks.
3. A durable Markdown report through
   `write_delivery_state_consistency_report`.

## Sprint 11 Use

AGENT-362 implements this guard and blocks:

1. AGENT-244 - Sprint 11 regression overview.
2. AGENT-245 - Sprint 11 retro and closure publication.

Before AGENT-244 and AGENT-245 proceed, the guard should run against Sprint 11
delivery stories and report no blocking mismatches, or every mismatch must have
a documented blocker approved by the Product Owner.
