# Release Manager Scope Selection

Status: implemented for MVP Sprint 9

The Release Manager scope selection workflow sits between Product Owner sprint
approval and scheduler assignment. It turns the approved sprint slice into a
visible decision record before workers start implementation.

## Inputs

The workflow uses:

1. Release scope key.
2. Sprint ring number.
3. Candidate Jira issues.
4. Release label and release version.
5. Sprint label and sprint ring label.
6. Capacity guardrails for story count and complexity points.
7. Release Manager rationale.

Each candidate records:

1. Jira issue key, title, issue type, and current status.
2. Complexity points.
3. Required worker role.
4. Dependency eligibility.
5. Worker availability.
6. Previous test outcome.
7. Dependency rejection details when prerequisites are not satisfied.

## Selection Rules

The Release Manager selects a candidate only when:

1. The issue is `READY TO START`.
2. Dependency eligibility is satisfied.
3. Previous test outcome is not failed or blocked.
4. A worker is available for the required role.
5. Adding the issue does not exceed the configured story count limit.
6. Adding the issue does not exceed the configured complexity-point limit.

Rejected candidates remain in the decision record with a visible reason. This
prevents silent skipping and gives the Product Owner a clear view of why an
issue was not assigned.

## Output

The workflow returns a `ReleaseManagerScopeSelection` record with:

1. Selected issue keys.
2. Rejected issues and reasons.
3. Metadata plans for release label, release version, sprint label, and sprint
   ring label.
4. Assignment decisions by worker role.
5. Selected complexity total and story count.
6. Product Owner approval requirement.
7. Release Manager rationale.

The output can be serialized to JSON for durable worker state and rendered to
Markdown for Jira comments, local evidence, or Confluence sync.

After scope selection, release notes and regression scope drafts are prepared
using the workflow in `docs/release-notes-regression-scope.md`.

## Product Owner Gate

This workflow does not replace Product Owner approval.

`READY TO START` means the Product Owner has approved the story for sprint
execution. After a story is merged, reviewed, tested, and free of unresolved
blocking bugs, Release Manager or Story Agent may move it to `ACCEPTED/DONE`.
The Product Owner's next required validation gate is sprint or release
readiness, unless a blocking PO inbox question or quota pause requires earlier
input.

## Relationship To Scheduler Assignment

Release Manager selection decides what is eligible and planned for assignment.
The scheduler still creates durable worker assignments and enforces the approved
scope/dependency gate before workers run.

This separation keeps release planning, worker assignment, and sprint
acceptance visible as separate process steps.
