# Release E2E Scenario Map

The MVP release E2E scenario map is the Product Owner and Release Manager view
of the complete release validation flow.

It is created after MVP implementation scope is complete enough to validate as
one release flow. It is not a replacement for unit tests, integration tests, or
sprint regression. It checks that the implemented agentic process works from
approved scope through release readiness.

## Default MVP Scenarios

1. Approved backlog and sprint scope become eligible worker assignments.
2. Developer implementation, review, merge, and PR visibility complete as one
   flow.
3. Tester failure creates a linked bug and routes the story back to
   development.
4. Sprint regression evidence, retro, and closure publish before release
   readiness.

Each scenario records:

1. Preconditions.
2. Steps.
3. Expected result.
4. Owner role.
5. Evidence type.
6. Mapped Jira issues.
7. AgileTest Test Case expectation.
8. Failure severity.

## Release Gate

The release gate distinguishes three failure severities:

1. `blocks-release`: create or link a Bug, fix, retest, and rerun the failed
   E2E scenario before release.
2. `requires-po-waiver`: create or link a known limitation and require explicit
   Product Owner waiver before release.
3. `non-blocking`: record the evidence and create a follow-up story or bug when
   useful for visibility.

## Excluded Checks

Release E2E excludes lower-level checks from its default scope:

1. Unit tests remain part of implementation validation.
2. Integration tests remain part of implementation or regression validation.
3. Sprint regression remains a sprint-level evidence artifact.

Release E2E may reference those artifacts as preconditions, but it should not
duplicate their detailed execution unless the Product Owner explicitly asks for
that release gate.
