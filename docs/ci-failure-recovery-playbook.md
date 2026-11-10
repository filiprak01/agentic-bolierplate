# CI Failure Recovery And Validation Runtime Handoff

This playbook standardizes Developer Agent recovery when local validation or
GitHub CI fails after a story has already been handed off.

## Validation Runtime Handoff

Developer handoff comments and pull request descriptions should name the
validation runtime used for the completed stage.

Include:

1. Runtime command prefix, such as `PYTHONPATH=src python3 -m pytest`.
2. Python, Poetry, Node, or project tool version when it affects reproducibility.
3. Working directory or target project path.
4. Any intentional fallback, such as using system Python because a local virtual
   environment is unavailable.
5. Durable evidence path that records the exact command and result.

Do not record secrets, tokens, or private environment values in validation
runtime handoffs.

## CI Failure Recovery

When GitHub checks fail after Developer handoff:

1. Confirm the failing check belongs to the story pull request and branch.
2. Reopen the relevant development stage or create a corrective follow-up stage
   under the same Jira story.
3. Reacquire or reopen the assignment lock when the previous Developer lock was
   released. Record the reason as CI recovery or requested-change recovery.
4. Move Jira back to the closest active development status when the story had
   already moved to `DEV COMPLETED`.
5. Reproduce or explain the failure with the expected validation runtime.
6. Push a focused fix commit to the same feature branch.
7. Verify GitHub checks are passing or record the remaining failing check with a
   blocker.
8. Restore the Jira handoff comment with the new commit, validation runtime,
   GitHub check result, and durable evidence path.
9. Return the story to `DEV COMPLETED` only after the corrective validation and
   GitHub check verification pass.

Review Agent requested changes follow the same recovery shape, except the
trigger is a review finding instead of a failing check.

## Stop Conditions

Stop and ask Product Owner through the PO inbox when recovery requires:

1. A new product requirement or changed acceptance criteria.
2. Credentials, repository permissions, or CI configuration secrets.
3. A decision to abandon the branch, replace the PR, or merge with failing
   checks.
