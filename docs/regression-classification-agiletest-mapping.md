# Regression Classification And AgileTest Mapping

Status: implemented for MVP Sprint 9

Regression classification lets Tester and Release Manager agents decide which
Jira Test issues should participate in sprint or release regression. AgileTest
mapping remains optional and configurable so projects can use Jira-only testing
or external test-management records without changing the core classification
model.

## Supported Classifications

The workflow supports these reusable classifications:

1. `one-time-validation`
2. `regression-candidate`
3. `smoke-regression`
4. `release-regression`
5. `automated-candidate`
6. `automated-covered`
7. `manual-only`

Each project can override the Jira label used for each classification.

## Classified Test Issues

`ClassifiedTestIssue` records:

1. Jira Test issue key.
2. Summary.
3. Covered Story or Bug key.
4. Regression classifications.
5. Jira labels after classification.
6. Optional AgileTest Test Case key.

This gives release planning a stable input for selecting regression scope.

## Release Scope Query

`ReleaseRegressionScopeQuery` records the project, release label, optional
sprint label, and classification filters used to find Test issues for
regression scope.

By default, query filters include:

1. `regression-candidate`
2. `smoke-regression`
3. `release-regression`

`one-time-validation` is excluded unless explicitly requested by the Product
Owner or Release Manager.

## AgileTest Mapping

`AgileTestMappingConfig` controls whether AgileTest mapping is active.

When disabled, the workflow returns a warning and produces no external mapping
operations.

When enabled, eligible Test issues produce `AgileTestArtifactMapping` records
for Test Case mapping while preserving:

1. Source Jira Test issue key.
2. Covered Story or Bug key.
3. Jira link type.
4. Outward relationship.
5. Target AgileTest issue type.

One-time validations are not mapped by default.

## Agent Usage

Tester Agent uses this workflow when creating or updating Test issues.

Release Manager uses this workflow to prepare sprint and release regression
scope before creating regression overviews, AgileTest executions, or release
notes.

For the board-visible overview Task pattern, behavioral/supporting validation
split, and recommended delivery board filter, see
`docs/behavioral-regression-visibility.md`.

For release regression suite/cycle planning from classified Test issues, see
`docs/agiletest-regression-suite-integration.md`.

The workflow is intentionally pure domain logic. Jira and AgileTest adapters
execute mapping plans separately.
