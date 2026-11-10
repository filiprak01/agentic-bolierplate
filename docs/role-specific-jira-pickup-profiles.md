# Role-Specific Jira Pickup Profiles

Status: Release 1.2 policy

The Scheduler and Orchestrator own Jira polling. Role workers do not invent JQL
or scan the board freely. A worker receives a durable assignment only after the
scheduler evaluates the role-specific pickup profile, active sprint scope,
dependency state, assignment locks, Codex limits, required artifacts, and
handoff signals.

This document is agent-facing operating context. It defines deterministic pickup
paths so work continues without Product Owner intervention unless a real
business decision or missing requirement blocks execution.

## Shared Rules

1. Work starts only from configured Jira statuses and issue types.
2. `READY TO START` is the Product Owner approval gate for new work.
3. Active sprint membership is required for delivery, review, testing,
   documentation publication, security, and release-manager work.
4. Future-sprint or unsupported-status candidates are skipped and logged as
   ineligible, not treated as actionable blockers.
5. Blocking gates produce durable skip/block logs with the role, issue key,
   status, decision, and machine-readable reasons.
6. A role worker polls durable assignments. It must not silently change role,
   project, sprint, repo, branch, or status selection.
7. Project-specific labels are optional configuration. If configured, the
   scheduler includes them in JQL and gates assignment on their presence.
8. Excluded-label JQL must keep unlabeled candidates visible with
   `(labels not in (...) OR labels is EMPTY)`.
9. The `Blocks` Jira link direction is prerequisite first: if X depends on Y,
   then Y blocks X.
10. Tester pickup of a `TEST COMPLETED` issue requires an explicit retest or
    regression signal. Otherwise the issue is skipped as already tested.

## Default Role Profiles

| Role | Statuses | Issue types | Required signals |
| --- | --- | --- | --- |
| Product Planning | `FUNNEL`, `READY TO START` | Epic, Story, Bug, Task | Codex limit available and no active assignment lock. |
| Architecture | `FUNNEL`, `READY TO START` | Epic, Story, Bug, Task | Codex limit available, no active lock, no secret exposure. |
| UI/UX | `READY TO START` | Story, Task | Active sprint, no lock, Codex limit available, and no secret exposure. Produces accepted design evidence for Frontend. |
| Developer | `READY TO START`, `DEV COMPLETED` | Story, Bug, Task | Active sprint, dependency graph clear, dependencies clear, no lock, Codex limit available, DOR pass, no unrelated blocking bugs, and rework signal when status is `DEV COMPLETED`. |
| Frontend Developer | `READY TO START`, `DEV COMPLETED` | Story, Bug, Task | Developer gates plus accepted design reference. |
| Review | `DEV COMPLETED` | Story, Bug, Task | Active sprint, no lock, Codex limit available, PR URL, PR branch, current PR head SHA, open PR state, development evidence, CI success, and clean mergeability. |
| Tester | `DEV COMPLETED`, explicit `TEST COMPLETED` retest/regression | Story, Bug, Task, Test | Active sprint, no lock, Codex limit available, merged main SHA, test request, development evidence, and acceptance criteria. `TEST COMPLETED` candidates are skipped unless explicit retest/regression is set. |
| Release Manager | `READY TO START`, `TEST COMPLETED` | Story, Bug, Task, Test | Active sprint, Codex limit available, sprint delivery ready, no unresolved bugs, and regression manifest ready. |
| Docs/GitHub Pages/Confluence | `READY TO START` | Story, Task | Active sprint, Codex limit available, evidence exists, and publication target is enabled. |
| Security/DevSecOps | `READY TO START`, `DEV COMPLETED` | Story, Bug, Task | Active sprint, Codex limit available, security scope defined, and no secret exposure. |

## JQL Generation

Generate JQL from configuration, not hardcoded project data. Example developer
profile for project `AP` and sprint `R1 S4`:

```text
project = "AP" AND status in ("READY TO START", "DEV COMPLETED") AND issuetype in ("Story", "Bug", "Task") AND sprint = "R1 S4" ORDER BY priority DESC, updated ASC
```

When project-specific labels are configured, include them explicitly:

```text
project = "AP" AND status in ("READY TO START", "DEV COMPLETED") AND issuetype in ("Story", "Bug", "Task") AND labels in ("agent-developer") AND sprint = "R1 S4" ORDER BY priority DESC, updated ASC
```

When excluded labels are configured, preserve unlabeled stories:

```text
(labels not in ("do-not-pick") OR labels is EMPTY)
```

If no active sprint name is provided and the role requires sprint scope, use
`sprint in openSprints()`.

## Rework Paths

### Review Fails

1. Review Agent keeps the story in `DEV COMPLETED`.
2. Review Agent records findings as `changes_requested` with PR reference,
   affected files, risk, and requested change summary.
3. Developer Agent may pick the same `DEV COMPLETED` story only because the
   review-change gate is present.
4. Developer Agent performs the smallest viable change, commits, pushes, and
   updates the PR.
5. Review Agent re-checks CI, diff, mergeability, open PR state, and prior
   findings against the current PR head SHA.

Review failures do not create bugs by default.

### Testing Fails

1. Tester Agent creates or updates a Bug.
2. The Bug blocks the original story using the correct directional Jira link.
3. Tester Agent records failed evidence and moves the original story back to
   `DEV COMPLETED`.
4. Developer Agent may pick the `DEV COMPLETED` story because a linked testing
   bug is present.
5. After the bug fix merges to `main`, Tester Agent retests using the evidence
   and acceptance criteria.

### Regression Fails

1. Release Manager or Tester creates/links a Bug to the failing story or
   regression scope.
2. The Bug blocks sprint/release closure until fixed and retested.
3. Regression continues only for independent scope where it is safe to do so.
4. Product Owner input is required only when the failure changes requirements,
   acceptance criteria, release scope, or business priority.
5. Tester Agent may re-pick a `TEST COMPLETED` issue only when the regression
   or retest signal is explicit in assignment metadata.

### Requirements Change

1. Product Planning or Architecture creates a new Story or updates a draft.
2. Current work stops only when the changed requirement invalidates an active
   implementation path.
3. Product Owner acceptance is required before new work moves to
   `READY TO START`.

## Skip Versus Block

Use `skip` for candidates the role should ignore:

1. Wrong project.
2. Unsupported status.
3. Unsupported issue type.
4. Future sprint.
5. Missing project-configured role label.
6. Excluded label.
7. Already completed testing with no explicit retest or regression signal.

Use `blocked` for candidates that are in scope but cannot start yet:

1. Dependency graph problem or unresolved prerequisite.
2. Active assignment lock.
3. Codex limits unavailable or below threshold.
4. Definition of Ready failure.
5. Missing PR metadata, closed PR state, stale PR head metadata, or CI not
   successful for Review.
6. Missing merge/test request/evidence for Tester.
7. Unresolved bugs blocking release/regression.
8. Missing publication target for docs work.
9. Missing accepted design reference for frontend work.
10. Missing security scope or detected secret exposure.

## Durable Logs

Every pickup evaluation should emit a line shaped like:

```text
role=developer issue=AP-29 project=AP status=READY TO START decision=pick reasons=none
```

Blocked/skipped examples:

```text
role=developer issue=AP-30 project=AP status=READY TO START decision=skip reasons=future_sprint
role=review issue=AP-33 project=AP status=DEV COMPLETED decision=blocked reasons=missing_artifact,ci_not_success,dirty_mergeability
role=tester issue=AP-34 project=AP status=TEST COMPLETED decision=skip reasons=explicit_retest_not_requested
```

These logs are used by the PO inbox UI, runtime status views, and sprint
performance analysis.
