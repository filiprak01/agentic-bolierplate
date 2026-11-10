# Sprint Performance Tracking

Status: active dogfooding process

Purpose: compare planned sprint scope against actual execution so the
boilerplate can learn whether sprint rings are sliced correctly for coherent
delivery, the Product Owner's current Codex Plus working window, review rhythm,
and regression effort.

## Performance Check

At sprint close, Release Manager records:

1. Planned stories.
2. Planned complexity points.
3. Planned coherent deliverable scope.
4. Stories completed.
5. Stories carried over.
6. Whether the sprint remained one coherent deliverable scope.
7. Whether the sprint fit the configured Codex Plus working window.
8. Codex limit pressure or pauses.
9. Review/test/regression effort that was larger than expected.
10. Bugs found during story testing or regression.
11. Scope recommendation for future sprints.
12. Jira sprint lifecycle state at closure.
13. Whether Product Owner retro input was captured before final closure.

## One-Go Completion

`one-go completion` means the sprint could be developed, reviewed, tested, and
prepared for Product Owner acceptance inside the configured working window
without splitting the sprint into a smaller execution slice.

This is a process signal, not a business acceptance rule.

Possible values:

1. `yes` - sprint size was manageable.
2. `partial` - sprint completed, but needed pauses, retries, or significant
   context recovery.
3. `no` - sprint should have been split before execution.

## Sprint Close Template

```text
Sprint performance:
Planned stories:
Planned complexity:
Planned coherent scope:
Completed stories:
Carried over stories:
Coherent scope preserved: yes / partial / no
Fit Codex Plus working window: yes / partial / no
Codex limit pressure:
Unexpected review/test/regression effort:
Bugs found:
Scope recommendation:
Jira sprint lifecycle:
Product Owner retro input:
```

## Scope Adjustment Rule

If two consecutive sprints are `yes` with no limit pressure and no large
regression surprises, Release Manager may propose a slightly larger coherent
scope.

If a sprint is `partial` or `no`, Release Manager should propose one of:

1. Split the next sprint ring.
2. Move lower-priority stories into a later process-hardening sprint.
3. Split by deliverable sub-scope.
4. Keep story count unchanged but reduce expected reasoning level where risk is
   low.

The Product Owner decides whether to accept the scope change.

## Current Baseline

Initial baseline from manual dogfooding:

| Sprint | Coherent Scope | Planned Stories | Planned Complexity | Completed Stories | Carried Over | Fit Working Window | Notes |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| Sprint 1 | Foundation core | 5 | 11 | 5 | 0 | yes | Completed with one tester-found bug resolved inside the sprint cycle. |
| Sprint 2 | PO inbox runtime | 5 | 13 | 5 | 0 | yes | PO inbox runtime completed with behavioral regression passing. |
| Sprint 3 | Worker infrastructure | 4 | 12 | 4 | 0 | yes | Worker infrastructure completed with full local regression passing. |
| Sprint 4 | Integration adapter foundation | 5 | 13 | 5 | 0 | yes | Adapter foundation completed with targeted adapter regression and full regression passing. |
| Sprint 5 | Planning governance | 5 | 13 | 5 | 0 | partial | Planning governance completed with focused regression and full regression passing. A Codex limit pause required context recovery before completion. Product Owner retro input was captured and Jira Sprint 5 was closed. |
| Sprint 6 | Scheduler and assignment governance | 6 | 18 | 6 | 0 | partial | Scheduler governance completed with mapped regression and full regression passing. Work required a limit handoff between windows, but the coherent scheduler scope held together and no regression bugs were found. |

The baseline supports keeping coherent scope as the primary boundary. Sprint 5
still completed as one coherent deliverable, but its `partial` fit means Sprint
6 should be watched closely for Codex Plus limit pressure. Complexity warnings
still matter, but Sprint 6's scheduler scope should be evaluated by coherent
worker orchestration value: if it fits the Product Owner's working window, it
can remain together; if not, split by scheduler sub-scope rather than by points
alone.

Sprint 6 confirmed that a larger coherent scheduler scope can be completed, but
it also required a window handoff. Future sprints should keep coherent
deliverable value as the primary slicing rule and use complexity as a warning.
For clear C3 implementation after prerequisite contracts exist, medium
reasoning is an acceptable starting point; raise reasoning only when the story
contains unresolved cross-role, architecture, security, or data consistency
risk.
