# Developer Branch Commit And Validation Workflow

Status: implemented for `AGENT-45`

The Developer Agent branch workflow keeps implementation visible and resumable
by tying each completed development subtask to validation evidence and a commit.

## Branch Naming

Feature branches use:

```text
feature/{JIRA_KEY}-{short-slug}
```

The branch name is built from the Jira issue key and story summary. The Jira key
is uppercased and the summary becomes a lowercase slug.

## Commit Stages

`DeveloperBranchPlan` records:

1. Jira issue key.
2. Story summary.
3. Feature branch name.
4. Base branch.
5. Target repository path.
6. Ordered development stages.
7. Durable validation output root.

Each `DeveloperCommitStage` maps a development subtask to the validation and
commit work needed before the subtask can be closed.

The next stage is the first non-committed stage. This keeps implementation
one-stage-at-a-time and matches the developer subtask protocol.

## Validation Gate

Validation commands are required on every commit stage. A stage can be marked:

1. `validated` when all commands pass.
2. `validation_failed` when any command fails.
3. `committed` only after it is validated and the commit SHA is known.

Validation failure is not discarded. It is represented in durable validation
evidence so a worker can resume, retry, or report the failed stage.

## Durable Evidence

`FileDeveloperValidationStore` writes validation results as:

1. Markdown evidence for Jira comments and PO visibility.
2. JSON evidence for future worker automation.

Evidence includes:

1. Jira issue key.
2. Stage id.
3. Jira subtask key.
4. Validation timestamp.
5. Command, exit code, and output for each command.
6. Overall pass/fail result.
7. Optional commit SHA.

## Validation Runtime Handoff

Developer validation evidence and Jira handoff comments should name the runtime
used to execute validation commands. Include the command prefix, relevant Python
or project tool version, working directory, intentional runtime fallback, and
durable evidence path.

If local validation or GitHub CI fails after handoff, use
`docs/ci-failure-recovery-playbook.md` to reopen the stage or lock, restore Jira
to the closest active development status, push a focused fix commit, verify
GitHub checks, and restore the story handoff.

The workflow does not create pull requests. Pull request creation is handled by
the dedicated PR workflow story after all development stages are complete.

## Stacked PR Branch Planning

When the context pack or assignment includes stack metadata, the Developer
Agent must resolve the stacked branch decision before creating or switching
branches.

Required checks:

1. GitHub authentication is ready.
2. Resolver path is `stacked-dependent`.
3. Stack id, lane id, trunk branch, repository, and layer are present.
4. Upper layers include parent story key, parent branch, and known parent story
   state.
5. Parent and child branches are in the same repository. Cross-fork and
   cross-repository stacks are blocked.

Base branch selection:

1. Layer 1 uses the configured stack trunk, normally `main`.
2. Upper layers use the previous layer branch as `base_branch`.
3. The branch name still uses `feature/{JIRA_KEY}-{short-slug}`.

Upper-layer development may continue while the lower layer is review-pending,
in-review, dev-completed, test-completed, accepted/done, or merged. If the
resolver marks the story `sequential-only`, the Developer Agent must not use
the stacked path.

If the recorded parent branch SHA differs from the current parent branch SHA,
the decision marks `rebase_required=true` and `stale_state=parent-branch-changed`.
The Developer Agent must refresh or rebase before opening a PR.
