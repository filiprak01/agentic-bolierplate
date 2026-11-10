# Docker Worker Triggering And Handoff Design

Status: Release 1.1 design baseline for `AGENT-547`.

This document defines the future trigger-driven handoff model for Docker
workers and host-side runners. Release 1.1 remains requirements/design scope;
it does not implement live detached Codex execution.

## Goals

The trigger mechanism must:

1. Start the next eligible role as soon as a role finishes a durable stop
   point.
2. Preserve the Product Owner `READY TO START` gate before development begins.
3. Re-check Jira dependencies, linked bugs, assignment locks, and Codex limit
   state before assigning follow-up work.
4. Avoid duplicate processing when multiple workers are running.
5. Keep blocked stories visible and choose another eligible story from the
   same approved sprint when possible.
6. Persist every trigger, wait reason, and resume point.

## Trigger Events

Required durable events are implemented as the queue vocabulary documented in
`docs/orchestration-event-queue.md`.

Every handoff, rework loop, regression request, retro request, closure
readiness trigger, and Product Owner resume route must also create a durable
communication message defined in `docs/agent-communication-channels.md`, or
store an explicit no-message reason in the trigger payload. This keeps the
Product Owner able to inspect why a role was or was not notified.

Release 1.2 provides an executable handoff publication path through:

```bash
agentic agent-messages publish-handoff
```

Workers and Orchestrator should use `publish-handoff` when a known story-path
event occurs. The command validates the canonical route, required identity
fields, context pack reference, evidence path, PR or merge data, and route
specific artifacts before writing the durable message. If validation fails, the
command records a durable `blocked` message targeted to Orchestrator so the
handoff is visible and replayable after restart.

Core handoff events:

1. `development_completed`
2. `review_completed`
3. `review_blocked`
4. `testing_completed`
5. `testing_failed`
6. `regression_completed`
7. `limit_paused`
8. `po_question_created`

Release 1.2 adds these explicit event types for trigger routing and sprint
closure:

1. `assignment_completed`
2. `pr_ready`
3. `pr_merged`
4. `test_requested`
5. `test_passed`
6. `test_failed`
7. `bug_created`
8. `regression_requested`
9. `retro_requested`
10. `retro_response_received`
11. `po_blocked`
12. `worker_idle`

Each event records event id, source assignment id, Jira issue key, source role,
recommended next role, Jira status snapshot, dependency gate result, limit gate
result, evidence/output paths, and creation timestamp.

## Handoff Rules

Developer completion queues Review for the same Jira issue after PR and local
validation evidence exist.

Review blocked queues Developer follow-up with conflict, failed check, security
finding, or required-change context. Review does not resolve conflicts.

Review completed confirms merge to `main`, moves or confirms `DEV COMPLETED`,
emits `test_requested`, and queues Tester. Review Agent does not move the story
to `IN TESTING`; Tester Agent owns that transition when validation starts.

Testing failed creates or links a Bug, moves the story back to `DEV COMPLETED`,
and queues Developer bug-fix follow-up. The original story remains blocked by
the unresolved linked Bug.

Testing completed moves the story to `TEST COMPLETED`, records reusable test
metadata, and notifies Release Manager that sprint readiness changed.

Regression completed notifies Release Manager closure logic and records
release/sprint evidence paths.

Limit paused leaves the assignment unchanged or `paused_limit`, records
`resume_after`, and waits for a fresh operator-entered availability record.

Product Owner question created must call the worker PO blocker contract
(`agentic worker pause-for-po`) so the assignment moves to `paused_po`, stores
the inbox item id, and writes resume context. The orchestrator may call
`agentic worker resume-po-inbox` only after the item is answered or approved
and normal Jira dependency, design, limit, and assignment-lock gates still pass.
Rejected or scope-changing answers remain paused and route to Product Planning
or Architecture follow-up instead of continuing silently.

Each handoff rule emits the matching `agent-messages` record:

1. Developer completion emits `review_requested`.
2. Review blocked emits `changes_requested`.
3. Review completed emits `test_requested`.
4. Testing failed emits `bug_fix_requested`.
5. Regression readiness emits `regression_requested`.
6. Retro collection emits `retro_requested` and waits for `retro_response`.
7. Closure readiness emits `closure_ready`.

## Blocked Story Fallback

When the preferred next story is blocked, the scheduler must:

1. Persist the blocked decision and blocker keys.
2. Re-check whether blockers are merged to `main`, `TEST COMPLETED`, and free
   of unresolved linked Bugs.
3. Scan the same approved sprint for another `READY TO START` issue whose
   dependency gate passes.
4. Queue the eligible issue for the correct role.
5. Wait and create a PO inbox item only when Product Owner action is required.

The scheduler must not pull work from another sprint without explicit Product
Owner override.

Release 1.2 implements the deterministic fallback decision through
`build_scheduler_fallback_plan` and renders the durable evidence with
`render_scheduler_fallback_plan`.

The fallback path is:

1. Evaluate the preferred story first.
2. If the preferred story is eligible, queue it and do not use fallback.
3. If it is blocked, record one skip entry with a machine-readable kind and
   human-readable reason.
4. Scan the same approved sprint for another candidate with the same role.
5. Reject candidates that are not `READY TO START`, outside the sprint, blocked
   by dependencies, locked by another worker, blocked by Codex limits, waiting
   for Product Owner input, conflicted, blocked by unresolved linked Bugs, or
   missing Definition of Ready.
6. Queue the first eligible fallback candidate.
7. If none is eligible, pause with the no-eligible-work reason:
   `No eligible READY TO START issue exists for the same role in the approved
   sprint ring.`

Fallback evidence must include preferred issue, selected issue or `None`,
fallback-used flag, skipped issues, skip categories, blocker details, assignment
paths, and pause reason. This gives the Product Owner and Orchestrator enough
context to understand why a worker moved to another story or stopped.

## Idempotency And Replay

Trigger handling must support:

1. At-least-once delivery.
2. Idempotent processing by event id and assignment id.
3. Duplicate-trigger protection for active assignments.
4. Assignment lock checks before queueing work.
5. Durable replay after worker or container restart.
6. Observable last processed event per worker.

Redis streams, database queues, filesystem event records, or a hybrid model are
allowed when they satisfy the requirements above.

## Acceptance Guardrails

Future implementation must prove:

1. Developer completion queues Review.
2. Review merge queues Tester.
3. Failed testing queues Developer bug follow-up.
4. Blocked stories do not stall the sprint when another approved story is
   eligible.
5. Duplicate trigger delivery does not create duplicate active assignments.
6. Limit-paused assignments are not started until a fresh availability record
   allows work.
7. PO-inbox paused assignments emit `po_resume_instruction` only after the
   matching inbox item is answered or approved and the Jira issue is still
   eligible.
8. Trigger decisions leave durable evidence for the Product Owner.
