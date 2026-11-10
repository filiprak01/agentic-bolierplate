# Sprint Acceptance And Dependency Gates

Scheduler dependency eligibility and Product Owner sprint acceptance are
separate gates.

## Development Dependency Gate

A prerequisite story can unblock dependent development when:

1. It has been merged to `main`.
2. Tester Agent validation is complete.
3. The Jira story is `TEST COMPLETED` or `ACCEPTED/DONE`.
4. No unresolved blocking Bugs are linked to the prerequisite.

The scheduler does not require `ACCEPTED/DONE` for dependencies unless a Jira
link, Product Owner note, or acceptance criterion explicitly says PO acceptance
is required before dependent development.

## Product Owner Acceptance Gate

`ACCEPTED/DONE` remains the Product Owner sprint-level or release-level
acceptance gate.

This means:

1. Developers and schedulers may continue dependent development after technical
   validation.
2. Product Owner acceptance still controls sprint or release closure.
3. Regression and release preparation wait until the Product Owner accepts the
   sprint or release scope.

## Durable Gate Logs

Scheduler and Release Manager decisions should be written with
`write_gate_decision_log`.

The log records:

1. Decision type.
2. Issue key or scope key.
3. Pass/fail result.
4. Reasons.
5. Blockers.

These logs let a stopped worker resume with the same gate decision context and
give the Product Owner visibility into why work was assigned or held back.
