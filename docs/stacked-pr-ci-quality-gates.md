# Stacked PR CI Quality Gates

Stacked pull requests do not reduce the quality gate. They change where a
check runs and how Review, DevOps, and Tester agents interpret failures.

## Layer Checks

Every stacked PR layer requires:

1. Formatting and lint checks.
2. Unit tests for changed modules.
3. Stack metadata validation.
4. Security/static checks when the changed paths touch security-sensitive code.

Each result must include a durable evidence path or provider URL and must be
visible from the Jira story.

## Integrated Checks

Before merging a stack trunk, merged lower layer, or contiguous merge group to
`main` or a release branch, the policy requires integrated checks:

1. Broader unit and integration tests.
2. Stack-level smoke or regression-candidate checks.
3. Branch protection compatibility.
4. Merge queue compatibility when merge queue is enabled.

## Failure Impact

Layer-local failures such as format/lint or changed-module unit tests block the
current layer only.

Integrated stack failures, branch protection failures, merge queue failures, and
metadata validation failures invalidate upper layers because later evidence may
be based on an unsafe or stale lower layer.

Review Agent records this distinction so Developer Agent can fix the owning
branch while Orchestrator avoids advancing dependent upper layers too early.

## Branch Protection And Merge Queue

When merge queue is enabled and branch protection supports queued stack merge,
the policy can use `merge-queue-enabled` mode.

When merge queue is not available, branch protection is incompatible, or the
provider cannot prove safe queued stack merge, the workflow falls back to
`fallback-branch-chain` mode. In fallback mode, layers merge bottom-up and
upper layers rebase or refresh after lower-layer changes.
