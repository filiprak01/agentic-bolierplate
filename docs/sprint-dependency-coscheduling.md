# Sprint Dependency Co-Scheduling Guard

Status: implemented for MVP Sprint 9

The scheduler must prevent a dependent story from being planned into a sprint
while unresolved prerequisite stories are outside that sprint.

## Rule

For every proposed sprint story, the scheduler walks Jira blocker links
recursively.

A blocker is acceptable when:

1. It is already completed in a configured technical completion status such as
   `TEST COMPLETED` or `ACCEPTED/DONE`.
2. It has explicit merged-to-main evidence in the scheduler snapshot.
3. It is assigned to the same sprint label as the dependent story.

If an unresolved blocker is not completed and not assigned to the same sprint,
the scheduler emits a blocking planning error.

## Recursive Chains

The guard checks blockers of blockers. If `A` depends on `B` and `B` depends on
`C`, planning `A` requires either:

1. `B` and `C` completed, or
2. `B` and `C` co-scheduled in the same sprint, or
3. a corrected sprint scope before `A` remains in scope.

## Correction Plan

The correction plan lists prerequisite issue keys that must be added to the
sprint or completed before the dependent issue can remain in scope.

The rendered planning note includes:

1. Planned issue keys.
2. Dependency-aware execution order, with blockers listed before dependents
   when both are intentionally co-scheduled.
3. Blocking dependency chains.
4. Required prerequisite issue keys.

## Product Owner Approval

Sprint assignment is not execution approval.

Even if a blocker must be co-scheduled, agents may only start work when the
Product Owner has moved that Jira issue to `READY TO START`.

If a required blocker is not `READY TO START`, the scheduler should report the
planning problem and wait for Product Owner action instead of silently starting
or changing the issue.

## Next-Sprint Dependency-Safe Work

Dependency-safe work in a future sprint is not automatically executable while
the current sprint is still open.

When a story becomes dependency-safe but belongs to the next planned sprint,
agents must use this decision order:

1. If the next sprint is active and the story is `READY TO START`, normal
   assignment can proceed after dependency and Codex-limit gates pass.
2. If the next sprint is future and the current sprint is still closing, the
   worker must pause and ask the Product Owner to start the next sprint, defer
   the story, or explicitly approve an out-of-sprint override.
3. If the Product Owner starts the next sprint, Release Manager must run Jira
   sprint lifecycle synchronization before workers begin the next-sprint story.
4. If the Product Owner defers the story, it remains planned but unassigned.
5. If the Product Owner approves an override, the scheduler must record the
   override reason and keep the story visible as an exception.

This keeps dependency readiness separate from sprint execution approval. A
completed prerequisite can make a future story technically safe, but the
Product Owner still controls when the next sprint starts or whether a story may
cross the sprint boundary.

## Product Owner Question Shape

When a dependency-safe story is in the next sprint while the current sprint is
still open, create a durable PO inbox item instead of asking only in chat.

Use `blocking_question` when no work may start until the Product Owner chooses a
path. Use `approval_request` only when the Release Manager or Scheduler has
already prepared a concrete override plan for the Product Owner to approve or
reject.

The question should include:

1. Current sprint id, name, and state.
2. Next sprint id, name, and state.
3. Candidate story key, summary, status, and sprint label.
4. Completed prerequisite keys that made the story dependency-safe.
5. Whether regression or closure work is still open in the current sprint.
6. The recommended option: start the next sprint, defer the story, or approve a
   named override.
7. Business impact of each option.

The durable question should explicitly ask whether to start the next sprint, defer the story, or explicitly approve an out-of-sprint override.

Recommended title format:

```text
Choose start/defer/override for {STORY_KEY} in next sprint
```

Recommended message format:

```text
{STORY_KEY} is dependency-safe because {PREREQUISITE_KEYS} are technically
complete, but it belongs to next sprint {SPRINT_ID}/{SPRINT_NAME}. Current
sprint {CURRENT_SPRINT_ID}/{CURRENT_SPRINT_NAME} is still {CURRENT_STATE}.
Should Release Manager start the next sprint, should Scheduler defer the story,
or do you approve an explicit out-of-sprint override?
```
