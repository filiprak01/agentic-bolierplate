# AgileTest Regression Suite Integration

Status: implemented for MVP Sprint 9

AgileTest regression suite integration lets Release Manager organize reusable
regression Test Cases for release readiness without requiring live AgileTest API
execution in the MVP.

## Configuration

The workflow records these configurable fields:

1. Jira project key.
2. AgileTest project key.
3. AgileTest client id environment variable.
4. AgileTest token environment variable.
5. Test Case issue type.
6. Test Cycle issue type.
7. Test Execution issue type.
8. Manual execution synchronization mode.

Default environment variables:

```text
AGILETEST_CLIENT_ID
AGILETEST_TOKEN
```

## Regression Suite Plan

Release Manager creates an AgileTest regression suite plan from a reviewed
regression scope draft.

The plan includes:

1. Release key and version.
2. Cycle name.
3. Suite name.
4. Included reusable Test Cases.
5. Covered Story or Bug key for each Test Case.
6. Regression classifications.
7. Release links such as release branch and tag.
8. Manual execution synchronization steps.
9. Warnings for disabled AgileTest or excluded one-time validations.

`one-time-validation` tests are excluded from the default reusable regression
suite unless Product Owner or Release Manager explicitly includes them in a
future workflow.

## Manual Execution Sync

MVP supports manual execution synchronization.

Default mode:

1. Create or update the AgileTest Test Execution for the release cycle.
2. Set each Test Case execution result manually in AgileTest.
3. Mirror the final execution summary to the Jira regression overview Task.
4. Create or link Jira Bugs for failed Test Case executions.

Comment-only mode records AgileTest execution status in Jira comments when
external execution updates are not available.

Disabled mode records no synchronization steps and treats the plan as
Jira-only guidance.

## Future Automation Hooks

The MVP does not require an automation repository.

Each Test Case can still carry future automation hook metadata:

1. `not-configured`
2. `planned`
3. `automated-candidate`
4. `automated-covered`

Release Manager and Tester agents use this metadata later when automation
repositories are introduced.

## Agent Usage

Release Manager Agent builds this plan after regression scope is drafted and
before release readiness execution.

Tester Agent uses the plan to understand which reusable Test Cases need manual
execution and where failed executions should create Jira Bugs.

Adapters execute live AgileTest create/update operations later. The domain
workflow stays mockable and does not require live AgileTest access in tests.

After execution, Release Manager should produce a reusable coverage manifest
using `docs/regression-manifest-builder.md`.
