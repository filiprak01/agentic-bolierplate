# Scheduler Approved Scope Assignment Workflow

The scheduler assignment workflow creates durable worker assignments only for
approved, unblocked sprint-scope work.

## Inputs

The workflow uses:

1. A `ReleaseScope`.
2. A sprint ring number.
3. Jira issue candidates.
4. Dependency and acceptance gate decisions.
5. Durable context, Codex job, and output paths.
6. Definition of Ready decisions.

Release Manager scope selection should run before this scheduler workflow. The
Release Manager records selected issues, rejected issues, metadata plans, and
worker-role assignment decisions. The scheduler then creates durable worker
assignments for the selected, approved, unblocked work.

Before assignment, sprint scope must also pass the recursive dependency
co-scheduling guard documented in `docs/sprint-dependency-coscheduling.md`.
Sprint assignment alone does not make a blocker executable.

When the next selected issue requires a different Codex model, reasoning, or
speed than the current session, the scheduler must emit a Product
Owner-visible manual switch checkpoint instead of starting work silently.

## Selection Rules

The scheduler assigns an issue only when:

1. The issue is in the selected sprint ring.
2. The issue status is `READY TO START`.
3. The dependency gate passed.
4. Required durable paths are provided.
5. An assignment lock can be acquired for the Jira key and role.
6. Codex limit records allow the planned role/model route.
7. Predicted file-scope conflict risk is acceptable for parallel work.
8. A per-assignment workspace can be allocated.
9. Any required Codex settings switch has been acknowledged by the Product Owner.
10. The Definition of Ready gate passes.
11. Live integration readiness has no blocking failure.

The `READY TO START` rule still applies to co-scheduled blockers. If a blocker
must be added to the sprint but is not approved by the Product Owner, the
scheduler reports the planning issue and waits instead of starting work.

Rejected issues are kept in the plan with a reason:

1. Issue is not `READY TO START`.
2. Issue is outside the approved sprint ring.
3. Issue has unresolved prerequisites.
4. Definition of Ready failed with machine-readable blocker codes.
5. Definition of Ready decision is missing.

The Definition of Ready gate is documented in
`docs/definition-of-ready-gate.md`. It requires accepted scope, context pack,
role/model routing, target repository and workspace, dependency state, setup
validation, fresh limit state, and design references for UI-facing
implementation.

Live integration readiness is documented in
`docs/live-integration-readiness.md`. The scheduler should run it before worker
assignment and store the redacted report with the assignment decision when a
required integration blocks execution.

For UI-facing implementation stories, the scheduler must also apply
`docs/ui-design-gate.md`: the accepted design story, design artifact, Product
Owner acceptance or override, and Jira `Blocks` dependency must be present
before assignment.

## Product Owner Override

Out-of-scope assignment requires an explicit override flag and a non-empty
Product Owner override reason.

Without that override, the scheduler does not assign work outside the approved
sprint ring.

## Future Sprint Candidates

A candidate can be dependency-safe and still not assignable.

If a candidate belongs to a future sprint while the current sprint is still
open, the scheduler must not silently assign it. The scheduler records the
candidate as held and asks the Product Owner, through the PO inbox, to choose
one of these paths:

1. Start the next sprint through Release Manager lifecycle synchronization.
2. Defer the candidate until its sprint becomes active.
3. Approve an explicit out-of-sprint override with a durable reason.

The held candidate should include the completed prerequisite keys that made it
dependency-safe, the current sprint state, the target sprint state, and any open
current-sprint regression or closure work. This gives the Product Owner enough
context to decide without reverse-engineering dependency links.

When the Product Owner chooses to start the next sprint, Release Manager owns
the sprint lifecycle action. Scheduler resumes assignment only after Jira shows
the target sprint as active.

## Durable Assignments

Accepted candidates become queued `AgentAssignment` records.

The assignment includes:

1. Jira issue key.
2. Worker role.
3. Assignment status.
4. Context pack path.
5. Codex job path.
6. Output path.
7. Branch name.
8. Project identity fields: `project_id`, `project_name`, `project_root`,
   `repository`, and `jira_project_key`.
9. Durable PO inbox namespace.
10. Isolated workspace path.

For pooled multi-project workers, scheduler assignment is project-scoped. A
worker can receive only one project identity and one Jira issue per active
assignment. Before the scheduler routes the same worker to another project, it
must confirm that the previous assignment is complete, paused, cancelled, or
handed off and that project-specific context was released or reset.

If a pooled worker still has unresolved assumptions, open PO inbox questions,
project credentials, local paths, repository state, or conversation-derived
context from another project, the scheduler must reject assignment and either
choose another eligible worker or create a Product Owner blocker.

`persist_assignment_plan` writes assignments through `FileAgentAssignmentStore`
so worker containers can stop and resume without losing scheduler decisions.

## Assignment Locks

Before a session or worker starts a Jira issue, it must acquire an assignment
lock for the Jira key and role.

The lock model records:

1. Jira issue key.
2. Agent role.
3. Worker or Codex session id.
4. Lock status.
5. Acquired and updated timestamps.
6. Dependency gate result.
7. Release reason and release timestamp when the lock is released.

The scheduler may create an active lock only after dependency gates pass. If an
active lock already exists for another worker/session, parallel work is blocked
unless the existing lock is stale.

Default stale policy: a lock is stale after four hours without an update. A
stale lock may be replaced only after the replacement decision is logged so the
Product Owner can see why two sessions did not work the same issue
concurrently.

Locks are released at durable stop points:

1. Assignment completed.
2. Work paused because Codex limits are unavailable.
3. Worker failed and saved handoff state.
4. Assignment was cancelled.
5. Stale lock was intentionally replaced.

Parallel sessions may work different Jira issues at the same time. They must
not work the same Jira issue unless the lock is owned by the same session or a
stale replacement decision has been made.

Detailed Codex-session rules are documented in
`docs/parallel-session-safety-policy.md`.

Detailed workspace allocation, shared durable folders, isolated per-worker
folders, and Git worktree/fresh clone/snapshot defaults are documented in
`docs/parallel-agent-workspaces.md`.

Detailed project identity fields are documented in
`docs/multi-project-identity.md`.

## Trigger-Driven Reassignment

When a worker emits a completion, blocked, limit, or Product Owner question
event, the scheduler must re-read Jira state, re-run dependency eligibility,
check assignment locks, check Codex limit availability, re-run Definition of
Ready, and queue the next eligible role only when all gates pass.

If the preferred story remains blocked, the scheduler scans the same approved
sprint for another eligible `READY TO START` issue. It must not pull work from
another sprint without Product Owner override.

The executable fallback policy is `build_scheduler_fallback_plan`. It evaluates
the preferred story first, records the exact machine-readable skip reason, and
then scans the remaining same-sprint candidates for the same role. Supported
skip categories are:

1. `status_not_ready`
2. `out_of_scope`
3. `dependency_blocked`
4. `assignment_locked`
5. `codex_limit_blocked`
6. `po_blocked`
7. `conflict_blocked`
8. `linked_bug_blocked`
9. `definition_of_ready_missing`
10. `definition_of_ready_failed`
11. `role_mismatch`
12. `missing_preferred`

`render_scheduler_fallback_plan` must be used for durable logs, Jira comments,
or PO-visible evidence. It records preferred issue, selected fallback issue,
fallback-used flag, skipped issue reasons and details, assignment paths, and
the pause reason when no eligible fallback exists.

If the preferred issue is missing from the scheduler candidate snapshot, the
scheduler may only scan fallback work when the triggering event also provides
the preferred role. Without that role context, the scheduler pauses with
`Preferred issue was not present and no preferred role was provided.`

When no same-role issue in the approved sprint can run, the scheduler pauses
with this reason instead of asking the worker to improvise:
`No eligible READY TO START issue exists for the same role in the approved
sprint ring.`

Detailed trigger event and handoff rules are documented in
`docs/docker-worker-triggering.md`.
