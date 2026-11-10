# Behavioral Regression Visibility

Status: implemented for MVP Sprint 9

Behavioral regression visibility keeps sprint and release regression visible to
the Product Owner on the Scrum board without forcing AgileTest artifact issue
types onto the delivery board.

## Board-Visible Overview Task

Each sprint or release regression run should create or update one Jira `Task`
as the board-visible overview.

The overview Task contains:

1. Sprint or release name.
2. Release label.
3. Sprint label.
4. Behavioral regression items.
5. Supporting validation items.
6. Linked Test Execution key when one exists.

Recommended labels:

1. `regression-overview`
2. `behavioral-regression` when user-facing or worker-facing checks are in
   scope.
3. `supporting-validation` when setup-only, schema-only, or internal-storage
   checks are recorded.
4. Release and sprint labels, for example `release-mvp` and `mvp-sprint-09`.

## AgileTest Artifacts

AgileTest records remain linked test-management artifacts:

1. `Test` issues represent Test Cases.
2. `Test execution` issues represent execution artifacts.
3. `Test cycle`, `Test script`, and `Test session` issues stay out of the
   delivery board when the board filter can be edited.

The overview Task links to the relevant Test Execution and included behavioral
Test Cases so the Product Owner can navigate from the board item to the test
evidence.

## Behavioral vs Supporting Validation

Behavioral regression means the check covers behavior visible to a user or an
agent worker.

Supporting validation means the check supports confidence but does not directly
exercise user-facing or worker-facing behavior.

Default classification:

1. `user-facing` -> `behavioral-regression`
2. `worker-facing` -> `behavioral-regression`
3. `setup-only` -> `supporting-validation`
4. `schema-only` -> `supporting-validation`
5. `internal-storage` -> `supporting-validation`

Setup-only, schema-only, and internal checks become behavioral only when they
expose user-facing or worker-facing behavior.

## Delivery Board Filter

Recommended Scrum board filter:

```text
project = AGENT AND issuetype not in ("Test", "Test execution", "Test cycle", "Test script", "Test session") ORDER BY Rank ASC
```

The project key and excluded issue types are configurable per target project.
The MVP must not hard-code this project forever; `AGENT` is the current
boilerplate development example.

## Agent Usage

Release Manager Agent creates or updates the overview Task during sprint or
release regression preparation.

Tester Agent supplies behavioral Test Cases and supporting validation evidence.

The workflow produces domain plans only. Jira and AgileTest adapters execute
the create, update, and link operations.

Regression overview Tasks should reference the durable manifest described in
`docs/regression-manifest-builder.md` after execution completes.
