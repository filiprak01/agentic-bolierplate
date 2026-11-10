# Developer Pull Request Creation Workflow

Status: implemented for `AGENT-46`

Developer pull request creation is the handoff from completed development work
to review. It is allowed only after all development subtasks are committed,
durable validation evidence exists, the feature branch is pushed to the
configured GitHub repository, and a visible pull request can be opened.

## Eligibility

`DeveloperPullRequestPlan` records:

1. Jira issue key.
2. Story summary.
3. Feature branch name.
4. Base branch.
5. Completed development stages.
6. Durable validation log paths.
7. Optional assignment id.

PR creation is blocked when:

1. Any development stage is not `committed`.
2. A stage is missing commit SHA.
3. A stage is missing Jira subtask key.
4. Validation evidence is missing for any stage.
5. Sprint publication metadata is incomplete when the PR is tied to sprint
   publication.
6. The feature branch was not pushed to the configured GitHub repository.
7. GitHub authentication, permissions, connector state, or repository
   configuration prevents reading the branch or opening the PR.

If a Product Owner or Orchestrator approved a no-subtask exception, the PR
creation plan may omit Jira subtask keys only when the parent Jira handoff names
the exception source and reason. Without that recorded exception, missing Jira
subtask keys block PR creation.

## PR Description

The generated PR body includes:

1. Jira issue key.
2. Story summary.
3. Development subtasks.
4. Commit SHA per subtask.
5. Validation evidence paths.
6. Sprint name and sprint publication task when applicable.
7. Related Jira story keys when applicable.
8. Change surface and boilerplate behavior impact flag.
9. Review workflow handoff note.
10. Stacked PR metadata when the story is part of a stack.

This gives the Product Owner and Review Agent direct traceability from Jira to
GitHub.

For stacked PR stories, the PR body and Jira handoff comment include:

1. Stack id and lane id.
2. Execution mode: `gh-stack` or `base-branch-fallback`.
3. Stack layer and trunk branch.
4. Base branch used for the PR.
5. Parent story, parent branch, and parent PR when known.
6. Child stories and child PRs when known.
7. Context pack reference.
8. Stale state.

## Execution

`execute_developer_pull_request_creation` uses the configured GitHub repository
adapter to open the PR. The workflow itself does not review, approve, or merge
the PR.

Before calling PR creation, Developer Agent must ensure the local feature branch
has been pushed to the configured GitHub repository. A local-only branch is not
a review handoff. If push, branch lookup, PR creation, or Jira PR-link
publication fails, keep the story in `IN PROGRESS`, write the diagnostic to
Jira/durable logs, and do not move the story to `DEV COMPLETED`.

Stacked PR creation supports two modes:

1. `gh-stack`: use GitHub stacked PR tooling when available while preserving the
   normal Jira-keyed branch name and PR metadata.
2. `base-branch-fallback`: open a standard GitHub PR whose base branch is the
   previous stack layer branch. This is the safe fallback when stacked PR
   tooling is unavailable, experimental, or blocked by local tooling.

Both modes keep all branches in the same repository. Cross-fork stacks are not
supported. Required checks and branch protection still apply to every PR.

PR creation is blocked when stack metadata says `rebase_required=true`, when the
stack is cross-repository/cross-fork, when the resolver path is no longer
`stacked-dependent`, or when an upper-layer PR targets any branch other than the
previous stack layer branch.

Developer-created pull requests open ready for review by default. A draft pull
request is allowed only when one of these sources explicitly requires draft
status:

1. Product Owner instruction.
2. Jira story, bug, or development subtask acceptance criteria.
3. A documented project process for the affected repository or release lane.

When a draft exception is used, the Jira handoff comment must name the exception
source and the condition that will make the pull request ready. In all other
cases, including process-repository documentation or workflow changes, the pull
request must be opened as non-draft.

## CI Trigger And Review Handoff

GitHub Actions should run automatically when the pull request is opened,
synchronized by a new push, or retargeted to another base branch. Developer
Agent should not poll or rerun remote CI after every local commit. The intended
handoff is one final stage push, one ready pull request, then Review Agent CI
validation on the current PR head SHA.

Review Agent waits for pending checks at review time and blocks the PR when the
remote GitHub workflow run/status is missing, stale, unreadable, cancelled, or
failing. If checks are missing because Actions did not trigger, Developer Agent
should synchronize the branch with a new push or use a documented manual rerun
or workflow dispatch only when that repository allows it. Local validation logs
remain useful evidence, but they never replace remote CI for review or merge.

After successful PR creation and Jira visibility publication, the worker should:

1. Store `DeveloperPullRequestResult` durably.
2. Add the PR link to Jira.
3. Add the manual Jira visibility fallback comment when smart-link visibility is
   missing or unreliable.
4. Ensure the Jira comment contains branch, commits, validation evidence,
   development subtasks or the approved no-subtask exception, and review handoff
   context.
5. Move the story to `DEV COMPLETED`.

Review and merge are handled by the Review Agent workflow.

## Multi-Repo PR Traceability

When a story touches multiple repository lanes, follow
`docs/multi-repo-jira-github-traceability.md`.

Developer Agent must create or update a trace for each affected repository:

1. Repository lane and configured owner/name.
2. Jira-keyed feature branch.
3. Jira-keyed commits.
4. Jira-keyed PR title and body.
5. Manual Jira PR link comment when automatic Jira development-panel visibility
   is not expected.
6. Process/change reason when the boilerplate/process repository is touched by
   a target-project story.

Do not rely only on branch naming for Jira visibility. If the Jira story does
not show a PR link through the configured GitHub integration, add the manual PR
link comment before moving the story to `DEV COMPLETED`.

Process-repository pull requests keep the same ready-by-default handoff, but
merge ownership follows the documented process lane. If a process-story PR needs
a process-review or release-manager owner instead of the default Review Agent
merge lane, the Developer Agent records that owner in the Jira handoff and stops
after the ready pull request is opened.

## Durable Result

`FileDeveloperPullRequestResultStore` writes `pull-request.json` under the
configured result root and Jira issue key.

The result stores:

1. Jira issue key.
2. Assignment id.
3. Pull request number.
4. Pull request URL.
5. Head branch.
6. Base branch.
7. Head SHA.
8. Created flag.

Tests use the mock GitHub adapter and do not require live GitHub access.
