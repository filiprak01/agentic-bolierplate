# Release E2E AgileTest Plan

The MVP release E2E AgileTest plan turns approved release scenarios into
inspectable Test Cases before release execution starts.

## Test Case Rules

Each release E2E Test Case includes:

1. Scenario ID and summary.
2. Preconditions.
3. Steps.
4. Expected results.
5. Owner role.
6. Evidence expectation.
7. Covered Jira issues.
8. Manual-only or automated-capable step mode.

Release E2E Test Cases use these labels:

1. `release-regression`
2. `release-e2e`
3. `manual-only` or `automated-capable`

They are excluded from ordinary sprint regression unless the Product Owner or
Release Manager explicitly includes them.

## Execution Plan

The release execution plan groups all MVP release E2E Test Cases under the
release execution overview task. Product Owner review is required before
execution starts.

Failed release E2E execution should create or link bugs back to the failed
scenario and release execution overview.
