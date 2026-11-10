# Release Branch And Version Tag Workflow

Status: implemented for MVP Sprint 9

The release branch and version tag workflow gives the Release Manager a
deterministic plan for creating a release maintenance line. The MVP
implementation creates planning metadata only; it does not create Git branches
or tags directly.

This workflow uses `docs/release-track-policy.md` for reusable release-track
decisions, including stable releases, minor releases, patch fixes, dogfooding
fixes, and deferred future capability.

## Version Metadata

Release versions follow:

```text
<major_update>.<sprint_scope>.<hotfix>
```

Examples:

```text
1.9.0
1.9.1
```

The workflow records this as `ReleaseVersion` with:

1. `major_update`
2. `sprint_scope`
3. `hotfix`

## Naming Rules

Release maintenance branches use:

```text
release/{MAJOR}.{MINOR}.x
```

Release tags use:

```text
v{MAJOR}.{MINOR}.{PATCH}
```

For example, version `1.9.0` maps to:

```text
release/1.9.x
v1.9.0
```

## Release Branch Plan

`ReleaseBranchPlan` records:

1. Release version.
2. Release branch name.
3. Version tag name.
4. Source ref, usually `main`.
5. Main branch name.
6. Included stories, bugs, tasks, or PRs.
7. Merge-back target.
8. Whether merge-forward to `main` is required.
9. Whether manual approval is required.
10. Release Manager rationale.

The plan requires at least one included work item so empty releases are not
published silently.

## Regression-Gated Automation

Release 1.2 adds a deterministic automation checklist that is built from the
release branch plan after regression completes. The automation planner does not
mutate Git directly; it produces the exact branch/tag actions and commands that
the Release Manager or trusted runner may execute.

Automation is ready only when:

1. Regression passed.
2. Regression evidence path is present and can be linked in Jira.
3. There are no unresolved blocking bugs.
4. The release branch plan includes at least one work item.

When the gate is ready, the checklist includes commands to fetch `main`, switch
to the main branch, fast-forward pull, create `release/{MAJOR}.{MINOR}.x`, tag
`v{MAJOR}.{MINOR}.{PATCH}`, and push both branch and tag. If any gate fails, no
commands are emitted and blockers are rendered instead.

This keeps the release branch/tag step automatable without hiding the evidence
and approval checks from the Product Owner.

## Included Work

Included work items should identify:

1. Jira issue key.
2. Summary.
3. Pull request URL when available.
4. Merge commit SHA when available.

This gives release notes and regression scope drafting enough information to
trace what entered the release branch.

## Merge-Forward Expectation

Release branches are maintenance lines. Fixes made on a release branch or
hotfix line must be forward-ported to `main` unless the Product Owner or
Release Manager explicitly records a different decision.

The workflow records `merge_forward_required = true` by default so this rule is
visible to Release Manager and Hotfix workflows.

## Relationship To Hotfix Workflow

AGENT-54 builds on this workflow.

Hotfix branches should start from the relevant release maintenance branch or
tag created by this plan, then merge back to the maintenance line and forward
port to `main`.

See `docs/hotfix-branch-workflow.md` for the implemented hotfix planning
workflow.

## Dogfooding Fix Placement

Dogfooding fixes discovered while testing a release on a real target project
must be visible Jira work. They are assigned to the active minor release when
they unblock current release reliability, or to a patch branch only when the
Product Owner decides the already-published release needs a backport.

Release Manager records that decision before creating the release or patch
branch plan.

For Release 1.1, approved MVP dogfooding fixes are part of the Release 1.1
scope unless the Product Owner explicitly asks for a separate `1.0.x` patch.

Fully detached Docker worker execution remains deferred to Release 1.2.0 or
later and must not be included in a Release 1.1 branch plan as delivered work.
