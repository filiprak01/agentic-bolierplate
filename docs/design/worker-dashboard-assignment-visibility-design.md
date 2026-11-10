# Worker Dashboard And Assignment Visibility Design

Jira story: `AGENT-671`

Implementation references: `AGENT-638`, `AGENT-675`, `AGENT-676`, `AGENT-679`

Selected option: Option A - Split Dashboard With Lifecycle Rail And Timeline

## Purpose

The Product Owner needs a check-oriented operator view that shows whether a
story is done, stuck, waiting, or ready for the next agent. The view must make
parallel work understandable without requiring the Product Owner to monitor live
worker output continuously.

## Target User

Primary user: Product Owner and local operator.

Secondary users: Orchestrator Agent, Release Manager Agent, Tester Agent, and
Developer Agent when they need to inspect durable state before choosing the
next task.

## Routes

The selected design uses existing AGENT-665 shell routes:

1. `Agent Status` for assignments, worker state, locks, limits, and lifecycle.
2. `Agent Messages` for communication timeline and graph.
3. `Logs` for evidence and safe log metadata references.

The dashboard must avoid a scroll-heavy single page. Summary cards stay compact
and the detail area changes based on selected assignment or story.

## Selected Layout

Option A uses three stable regions:

1. Filtered assignment list.
2. Story lifecycle rail.
3. Detail panel with timeline, graph, artifacts, and rescue actions.

The assignment list is optimized for scanning. Each row shows project id, Jira
key, worker role, current status, lock state, waiting reason, and next expected
agent.

The lifecycle rail shows deterministic story processing steps:

1. Product Planning
2. Architecture
3. Development
4. Review
5. Merge
6. Testing
7. Regression
8. Retro
9. Release Acceptance

Each step can be:

1. Not started
2. Done
3. Skipped/not applicable
4. Blocked/stuck
5. Next expected step
6. Waiting for PO input
7. Waiting for dependency
8. Waiting for limit capacity

## Assignment States

The implementation must show:

1. Active worker
2. Blocked assignment
3. Waiting for PO
4. Waiting for dependency
5. Waiting for limit capacity
6. Failed assignment
7. Completed assignment
8. Resumed assignment
9. Lock owned
10. Stale lock
11. No worker available
12. Multi-project collision avoided

## Communication Timeline

The timeline shows durable events in chronological order. It must distinguish:

1. Agent-to-agent status update
2. Orchestrator assignment decision
3. Orchestrator `resume_request`
4. Jira status change
5. Dependency gate decision
6. Limit gate decision
7. PO inbox question
8. PO response
9. PR reference
10. Test evidence reference
11. AgileTest record
12. Documentation publication

Timeline cards must show why the Orchestrator resumed or refused to resume a
story. If a story cannot resume, the blocked reason and next required actor must
be visible.

## Graph View

The graph is intentionally simple for Release 1.2. It is a status map, not a
free-form canvas.

Required node types:

1. Project
2. Jira issue
3. Agent role
4. Worker assignment
5. Durable message
6. Artifact

Required edge labels:

1. assigned to
2. blocks
3. waits for
4. produced
5. reviewed by
6. tested by
7. resumed by
8. asks PO

The graph must have a list fallback for small screens and accessibility.

## Artifacts Per Lifecycle Step

Each lifecycle step can show zero or more safe artifact references:

1. Pull request
2. Merge commit
3. Test evidence file
4. Jira comment
5. AgileTest record
6. Documentation page
7. PO inbox item
8. Limit handoff record
9. Retro item

Only safe relative paths and external URLs are displayed. The UI must not expose
raw absolute host paths, tokens, `.env` values, or log contents.

## Rescue Visibility

AGENT-679 implementation uses this design for stuck worker controls. Rescue
actions must be shown only when safe metadata confirms the operator can act:

1. Release stale lock
2. Mark assignment paused
3. Request worker resume
4. Requeue assignment
5. Open linked PO inbox blocker

Destructive actions require clear confirmation and must show the target
assignment id, project id, and Jira key.

## Multi-Project Identity

Every row, event, graph node, artifact, and rescue action includes project id
and Jira key when available. The design supports filtering by one project or
all projects without mixing local paths or credentials.

## Accessibility

1. Status indicators use icon/text labels, not color alone.
2. Timeline events are keyboard reachable.
3. Graph data has an equivalent list view.
4. Sticky filter controls remain usable at 360 px width.
5. Long Jira summaries wrap without overlapping action buttons.

## PO Acceptance Note

The Product Owner explicitly allowed this sprint to continue without waiting on
per-story visual approval. For AGENT-671, this design is accepted by sprint
execution override and can be used by AGENT-638, AGENT-675, AGENT-676, and
AGENT-679 as their `Design Reference`.

## Design Reference

Implementation stories must copy this reference:

```text
Design Reference:
- Design story: AGENT-671
- Design document: docs/design/worker-dashboard-assignment-visibility-design.md
- Design artifact: docs/design/worker-dashboard-assignment-visibility-options.html
- Selected option: Option A - Split Dashboard With Lifecycle Rail And Timeline
- Acceptance: Product Owner sprint execution override recorded in AGENT-671
```
