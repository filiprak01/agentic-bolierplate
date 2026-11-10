# Release Notes And Regression Scope Drafts

Status: implemented for MVP Sprint 9

Release Manager creates draft release notes and regression scope before release
readiness so the Product Owner can review what is included, what is known, and
which tests belong to release regression.

## Release Notes Draft

Release notes include:

1. Stories and bugs included in the release.
2. Jira status for each included item.
3. Pull requests connected to each item.
4. Linked Test issues.
5. Linked bugs.
6. Known limitations and workarounds.

The draft starts in `draft` status. Product Owner review can move it to
`po-approved` or `changes-requested`.

## Regression Scope Draft

Regression scope is generated from classified Jira Test issues.

The draft separates:

1. `one-time-validation`
2. `smoke-regression`
3. `release-regression`
4. `regression-candidate`
5. `automated-candidate`
6. `automated-covered`
7. `manual-only`

Changed areas must be listed so the Product Owner and Release Manager can see
why the scope was selected.

When AgileTest mapping is configured, the draft includes mapping details from
Jira Test issues to their covered stories or bugs. AgileTest execution creation
belongs to the AgileTest regression suite integration workflow.

## Local Storage And Confluence Sync

Drafts are prepared for durable local storage first, then Confluence sync.

Recommended local paths:

```text
data/release-drafts/{release-key}/release-notes.md
data/release-drafts/{release-key}/regression-scope.md
```

The release draft model returns these paths as a plan. The storage layer or
worker runtime writes the rendered Markdown and then the Confluence adapter can
sync it into shared documentation.

## Agent Usage

Release Manager Agent builds the draft bundle after release or sprint scope is
known and before release readiness review.

Tester Agent contributes linked Test issues, classification labels, evidence,
and known testing limitations.

Product Owner reviews the drafts and either approves them or requests changes.

The workflow does not execute AgileTest regression. It prepares the reviewed
scope that AGENT-86-style AgileTest integration can later turn into cycles or
executions.

For AgileTest suite and manual execution synchronization planning, see
`docs/agiletest-regression-suite-integration.md`.
