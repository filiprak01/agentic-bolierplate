# Release Scope Model

Status: implemented for MVP Sprint 6

The release scope model lets a release span multiple sprint rings. It avoids
the early dogfooding assumption that one sprint is the same thing as one
release.

For MVP, Release 1 is the product release and it is delivered through multiple
sprint rings such as planning governance, scheduler foundations, developer
workflow, review/test workflow, and release workflow.

## Model

`ReleaseScope` describes the whole release:

1. Release key.
2. Release name.
3. Release version.
4. Description.
5. Creation timestamp.
6. One or more `SprintRing` records.

`SprintRing` describes a coherent sprint slice:

1. Sprint ring number.
2. Name.
3. Capacity target.
4. Complexity total.
5. Included issues.
6. Goal.

`ScopeIssue` records the issue key, title, issue type, complexity points, and
current status used by the Release Manager during planning.

## Release Manager Proposals

The Release Manager may create a `SprintScopeSelectionProposal` before Product
Owner approval.

The proposal records:

1. Release scope key.
2. Sprint ring number.
3. Selected issue keys.
4. Proposer.
5. Rationale.
6. Creation timestamp.
7. Proposal status.

The proposal starts as `proposed` and can later be marked `po_approved`.

## Release Manager Selection

After the Product Owner moves sprint work to `READY TO START`, the Release
Manager creates a scope selection decision before scheduler assignment.

The decision checks candidate status, dependency eligibility, previous test
outcome, worker availability, story count capacity, and complexity capacity. It
also prepares the release label, release version, sprint label, and sprint ring
label metadata that should be applied to selected issues.

Before a release scope is converted into new backlog work, Product Planning or
Release Manager should attach the latest documentation-to-backlog traceability
report from `docs/documentation-to-backlog-traceability-audit.md`. This keeps
release scope docs, roadmap notes, and deferred decisions from silently
becoming untracked implementation work.

See `docs/release-manager-scope-selection.md` for the implemented decision
record and selection rules.

## Release Branches And Tags

After a release scope is selected and implemented, the Release Manager can
prepare a release maintenance branch and version tag plan.

Release branch plans use `release/{MAJOR}.{MINOR}.x` and release tags use
`v{MAJOR}.{MINOR}.{PATCH}`. The same plan records included Jira issues, PRs,
merge commits, and merge-forward expectations back to `main`.

See `docs/release-branch-version-workflow.md` for the implemented workflow.

## Durable Local Files

`FileReleaseScopeStore` stores release scopes and sprint selection proposals as
JSON files under durable local storage.

Default folders:

```text
release-scopes/
sprint-scope-proposals/
```

Local files are inspectable and resumable. They are not a substitute for
Product Owner approval in Jira.

## Sprint Fit

Sprint scope is still sliced by coherent deliverable value first. Complexity
totals and capacity targets are warning metadata used to manage Codex Plus
limit pressure and avoid overfilling a sprint.
