# Worktree Cleanup Workflow

Status: implemented for `AGENT-199`

This workflow plans safe cleanup for completed feature worktrees without
silently deleting unrelated user changes.

## Inputs

Each `CompletedWorktree` records:

1. Jira issue key.
2. Branch name.
3. Local worktree path.
4. Whether the branch is merged to `main`.
5. Whether uncommitted changes exist.
6. Optional evidence and status file paths.
7. Optional PR URL.

## Cleanup Policy

`CleanupApprovalPolicy` supports:

1. `manual-approval`
2. `auto-delete-clean`
3. `auto-archive-then-delete`

Manual approval keeps clean worktrees from being deleted until the operator or
workflow explicitly approves deletion.

## Safety Rules

`build_worktree_cleanup_plan` enforces:

1. Unmerged worktrees are kept.
2. Worktrees with uncommitted changes are blocked for manual review.
3. Evidence and status files can be archived before deletion.
4. Cleanup remains a plan until an outer workflow executes it.

## Durable Logging

`write_worktree_cleanup_log` stores a markdown log for the cleanup decisions so
the sprint process can reference what was archived, kept, blocked, or approved
for deletion.
