# Retro Follow-Up Roadmap

Status: active dogfooding process

Purpose: make sprint retro follow-ups visible as either immediate process
changes, MVP backlog stories, or later-release roadmap candidates. Retro notes
should not stay as untracked discussion when they change how the boilerplate
agents should behave.

## Policy

At sprint close, Release Manager records each retro follow-up as one of:

1. Current-process update under the sprint retro/closure Task.
2. Existing Jira story mapping when the backlog already owns the behavior.
3. New Jira backlog candidate in `FUNNEL` for Product Owner review.
4. Later-release roadmap note when the item is valuable but not MVP scope.
5. Intentionally rejected or deferred item with the reason documented.

Current-process updates may change documentation under the sprint
retro/closure Task. Boilerplate code or agent behavior changes still require a
story, branch, PR, review, test evidence, and Product Owner acceptance.

## Sprint 5 Mapping

| Follow-up | Decision | Jira |
| --- | --- | --- |
| Dependency-direction validation for closure/planning tasks | MVP, existing scheduler/dependency backlog | AGENT-39, AGENT-131 |
| Jira sprint lifecycle synchronization | MVP, new Sprint 6 candidate | AGENT-197 |
| Regression artifact publication helper | MVP, new Sprint 9 candidate | AGENT-198 |
| Completed worktree cleanup/archive workflow | MVP process hardening, new Sprint 11 candidate | AGENT-199 |
| AgileTest Test Case consistency validator | MVP, new Sprint 10 candidate | AGENT-200 |
| PR-to-Jira publication visibility | MVP, existing review/process backlog | AGENT-48, AGENT-138 |
| Confluence report publication for tests, regressions, retros, and partner reports | MVP, new Sprint 11 candidate | AGENT-201 |

## Sprint 6 Mapping

| Follow-up | Decision | Jira |
| --- | --- | --- |
| Jira sprint lifecycle synchronization | MVP, already in backlog | AGENT-197 |
| Regression artifact publication helper | MVP, already in backlog | AGENT-198 |
| Confluence report publication for reports and partner-facing summaries | MVP, already in backlog | AGENT-201 |
| PR-to-Jira publication visibility | MVP, already in backlog | AGENT-48, AGENT-138 |
| Worktree cleanup/archive workflow | MVP process hardening, already in backlog | AGENT-199 |
| Medium reasoning for clear C3 implementation after contracts exist | Current-process update | Sprint 6 retro decision |

## Release 1.1 Deferred Retro Closure Routing

AGENT-618 triaged the deferred Release 1.1 retro/closure Tasks into Release
1.2 scope. These tasks stay as historical deferred source items; they do not
need separate implementation work after their routing comments are posted.

| Deferred item | Accepted Release 1.2 scope | Jira routing | Exclusion |
| --- | --- | --- | --- |
| AGENT-463 - R11 Sprint 4 Retro And Closure | Operator UI visibility, multi-project inbox/status, design-gated UI work, and documentation publication moved into R1.2. | AGENT-636, AGENT-637, AGENT-638, AGENT-643, AGENT-660, AGENT-664, AGENT-665, AGENT-667, AGENT-668, AGENT-669, AGENT-670, AGENT-671, AGENT-672, AGENT-675, AGENT-676, AGENT-679, AGENT-695, AGENT-696, AGENT-697, AGENT-698 | The old R1.1 Sprint 4 closure Task will not be executed as a new sprint item; it remains a source retro record. |
| AGENT-465 - R11 Sprint 5 Retro And Closure | Session-mode validation follow-ups, detached worker safety, host-side execution bridge, durable pause/resume, limit wait/resume, and orchestration handoff moved into R1.2. | AGENT-619, AGENT-622, AGENT-624, AGENT-626, AGENT-627, AGENT-628, AGENT-629, AGENT-630, AGENT-631, AGENT-632, AGENT-646, AGENT-674 | Fully autonomous detached Docker execution remains gated by safety, orchestration, and pilot evidence before broader use. |
| AGENT-467 - R11 Sprint 6 Retro And Closure | Parallel-work safety, assignment locks, isolated workspaces, cleanup, multi-repo traceability, and stacked PR workflow moved into R1.2. | AGENT-633, AGENT-634, AGENT-635, AGENT-673, AGENT-678, AGENT-687, AGENT-688, AGENT-689, AGENT-690, AGENT-691, AGENT-692, AGENT-693 | Unmanaged shared-workspace execution and mixed target/process PRs without visible reasoning are excluded. |

## Sprint Close Checklist Addition

Before a sprint is closed, Release Manager should verify:

1. Board-visible regression overview and retro/closure Tasks are assigned to
   the Jira Sprint field.
2. AgileTest artifact issue types remain off the delivery board unless the
   project is configured otherwise.
3. Product Owner retro input is captured or explicitly waived.
4. The Jira sprint lifecycle state matches the closure docs.
5. Every accepted retro follow-up has a Jira story, existing-story mapping, or
   documented deferral.
6. Report artifacts that should be shared outside local worker context are
   prepared for Confluence publication or mapped to a backlog story that will
   publish them.

## Workflow Contract

`RetroToRoadmapPlan` makes the routing explicit for local dry runs and later
worker execution.

The workflow captures:

1. Finding status: accepted, rejected, deferred, or needs PO clarification.
2. Routing target: existing story, new backlog story, documentation update,
   deferred roadmap bucket, or rejection.
3. Cleanup actions for changed local files before the next sprint starts:
   push, park, or exclude.

Accepted findings must map to:

1. An existing Jira story.
2. A new backlog story candidate.
3. A documentation-only update under the sprint publication flow.

Deferred findings require a roadmap bucket. Rejected findings stay documented
without creating scope automatically. Findings that need PO clarification keep
the Product Owner as the final scope-change gate.

When a retro adds or changes reusable process knowledge in docs, Release
Manager or Product Planning should include those docs in the next
documentation-to-backlog traceability audit documented in
`docs/documentation-to-backlog-traceability-audit.md`. The audit result must
show whether each accepted retro commitment is covered by Jira, doc-only,
duplicate, deferred, rejected, PO-needed, or missing Jira reflection.
