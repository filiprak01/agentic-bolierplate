# AgileTest Test Case Consistency Validator

Status: implemented for MVP Sprint 10

This validator checks whether reusable Jira `Test` issues are consistent enough
to enter release regression planning.

## Goal

The validator is a read-only helper for Tester and Release Manager workflows.

It does not mutate Jira issues. It reports what is missing so the owning agent
or Product Owner can decide what to fix before suite preparation.

## What It Checks

For one reusable Test Case, the validator checks:

1. Jira project key.
2. Jira issue type name.
3. AgileTest-style Test Case label.
4. Release label.
5. Sprint label.
6. Regression classification label.
7. Manual or automated coverage label.
8. Scenario summary.
9. Preconditions.
10. Steps and expected results.
11. Manual evidence references or automated command references.

## Execution Modes

Manual reusable Test Cases must provide:

1. Manual coverage labels.
2. Scenario, preconditions, and steps.
3. Evidence references that point to inspectable validation artifacts.

Automated reusable Test Cases must provide:

1. Automated coverage labels.
2. Scenario, preconditions, and steps.
3. Command or test-file references that identify the executed coverage.

## Output

The helper returns:

1. One per-Test Case result with findings and matched labels.
2. One batch result that shows whether a release regression set is ready.
3. Renderable Markdown summaries for PO, Tester, or Release Manager review.

## Configuration

Project-specific values stay configurable:

1. Jira project key.
2. Jira Test issue type name.
3. Accepted AgileTest labels.
4. Release and sprint label prefixes.
5. Regression classification labels.
6. Manual and automated coverage labels.

This keeps the validator reusable when a future project uses different naming
conventions.
