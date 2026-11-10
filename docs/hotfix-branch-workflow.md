# Hotfix Branch Workflow

Status: implemented for MVP Sprint 9

The hotfix branch workflow gives the Release Manager a deterministic plan for
fixing production or UAT bugs on the correct release maintenance line. The MVP
implementation creates planning metadata only; it does not create Git branches,
tags, or pull requests directly.

## Naming Rule

Hotfix branches use:

```text
hotfix/{MAJOR}.{MINOR}.{PATCH}-{jira-key-or-slug}
```

Example:

```text
hotfix/1.9.1-AGENT-900
```

The patch component must be greater than zero. Base release branches and tags
remain owned by the release branch/version workflow.

## Source Ref Rule

Hotfix work must start from one of these refs on the same release line:

1. The release maintenance branch, such as `release/1.9.x`.
2. A prior release tag, such as `v1.9.0`.

The source tag must be earlier than the planned hotfix version so a hotfix does
not accidentally branch from itself or a later patch.

## Hotfix Plan

`HotfixBranchPlan` records:

1. Hotfix version.
2. Hotfix branch name.
3. Source ref and source type.
4. Fixed bug key, summary, environment, and severity.
5. Merge-back target.
6. Forward-port target.
7. Whether conflict resolution is required.
8. Manual approval points.
9. Release Manager rationale.

## Merge Back And Forward Port

Hotfix pull requests merge back to the release maintenance branch:

```text
release/{MAJOR}.{MINOR}.x
```

The fix must then be forward-ported to `main` unless the Product Owner or
Release Manager records an explicit exception.

## Conflict And Approval Points

Conflicts are not product bugs by default. They are workflow findings that must
be routed back to the responsible developer or Release Manager.

Manual approval points should include at least:

1. Release Manager approval for the hotfix scope.
2. Product Owner acceptance of the fixed behavior before release.

Additional security, compliance, or client approval points can be added per
project.

## Relationship To Release Branch Workflow

This workflow builds on `docs/release-branch-version-workflow.md`.

Release branches and release tags establish the maintenance line. Hotfix branch
plans use that maintenance line as the source and merge-back target.
