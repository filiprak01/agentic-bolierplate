# Release Track Policy

Status: implemented for `AGENT-424`

This policy defines how release, stabilization, hotfix, and future capability
work is assigned to release tracks. It is reusable for Release 1.1 and later
release planning.

## Operator Track Selection

Use the release track that matches the work being performed:

1. Use `release/1.0.0` when testing or demonstrating the MVP snapshot exactly
   as it was released for first target-project dogfooding.
2. Use `main` when planning or implementing future boilerplate work such as
   Release `1.1.0`.
3. Use a release maintenance branch such as `release/1.1.x` only after that
   release line exists and the work is a patch or stabilization change for the
   released line.

Do not mix Release `1.1.0` planning documents, stories, or implementation work
into `release/1.0.0` test branches. If an MVP dogfooding issue must be fixed
while Release `1.1.0` work is already active, create a Jira bug or story,
assign it to the correct release track, and record whether it should be
backported to the MVP release branch.

Release `1.1.0` planning lives in Jira release labels, Confluence-ready
planning docs, and local planning mirrors on `main`. Operators should treat
`docs/release-1.1-scope-discussion.md` and
`docs/release-1.1-backlog-draft.md` as Release `1.1.0` planning inputs, not as
MVP release artifacts.

## Track Types

### Stable Release

A stable release is a Product Owner approved capability snapshot.

Use a stable release when:

1. The scoped stories are implemented, reviewed, tested, and accepted.
2. Release regression has passed or known issues are explicitly accepted.
3. Release notes and operator guidance are ready.
4. The Product Owner approves release creation.

Stable release tags use:

```text
v{MAJOR}.{MINOR}.{PATCH}
```

Example:

```text
v1.1.0
```

### Minor Release

A minor release introduces planned platform capabilities on top of the previous
stable release.

Examples:

1. `1.1.0` for session-agent and operator UX foundation.
2. `1.2.0` for a future detached Docker worker execution release.

Minor release maintenance branches use:

```text
release/{MAJOR}.{MINOR}.x
```

Example:

```text
release/1.1.x
```

### Patch Fix

A patch fix stabilizes an existing release line without introducing broad new
capability.

Use a patch fix for:

1. Runtime stability problems found while dogfooding a stable release.
2. Documentation corrections needed to use the released scope.
3. Setup, path, or configuration defects that block normal operation.
4. Low-risk fixes approved by the Product Owner for the active release line.

Patch tags increment only the patch segment:

```text
v1.1.1
v1.1.2
```

Patch fixes should be merged back to the maintenance branch and forward-ported
to `main` unless the Product Owner records a different decision.

### Future Major Release

A future major release is used when capability, compatibility, or operating
model changes are large enough that they should not be treated as minor
extension work.

Major release planning must include:

1. Migration impact.
2. Backward compatibility expectations.
3. Operator upgrade notes.
4. Security and credential review.
5. Regression strategy for existing projects.

## Dogfooding Fix Flow

Dogfooding fixes are defects or friction discovered while testing the
boilerplate on real target projects.

Dogfooding fixes are handled as normal Jira work:

1. Create or identify the Jira story or bug.
2. Assign it to the active release or patch track.
3. Implement through branch, PR, review, merge, and test.
4. Add regression or operator evidence when behavior changes.
5. Record whether the fix must be backported to an existing release branch.

Dogfooding fixes must not be applied as invisible side work.

## Release 1.1 Decision

Release 1.1 includes approved MVP dogfooding fixes when they unblock reliable
session-agent and operator workflow.

The Docker API keepalive fix is included in Release 1.1 as a stabilization
story. It may be backported to `1.0.x` only if the Product Owner decides a
separate patch release is needed.

## Deferred Capability

Fully detached Docker worker execution is explicitly deferred to `1.2.0` or
later.

Release 1.1 may document Docker worker requirements, constraints, credentials,
volumes, and pause/resume behavior, but it must not present fully autonomous
detached execution as available capability.

## Required Release Manager Checks

Before creating a release or patch branch, Release Manager verifies:

1. The target version and branch follow this policy.
2. Included Jira work belongs to the selected release track.
3. Dogfooding fixes have clear release or backport placement.
4. Deferred work is documented and not described as delivered.
5. Product Owner approval is recorded before release creation.
