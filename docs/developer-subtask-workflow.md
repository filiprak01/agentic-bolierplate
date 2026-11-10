# Developer Subtask Workflow

Status: implemented for `AGENT-44`

Developer Agents must create visible Jira subtasks before implementation starts
for every code implementation Story or Bug. Each subtask represents one
implementation stage under the parent Story or Bug.

The only allowed exception is an explicit Product Owner or Orchestrator
approval recorded on the parent Jira issue before implementation begins. When
an exception is approved, the Developer Agent records the reason in the Jira
handoff comment and still commits work in reviewable stages.

## Planning Contract

`DeveloperSubtaskPlan` records:

1. Parent Jira issue key.
2. Parent issue type, limited to Story or Bug.
3. Context pack path.
4. Acceptance criteria used by the worker.
5. Ordered implementation stages.

Each `DeveloperSubtaskStage` records:

1. Stable stage id.
2. Title and implementation description.
3. Expected changed areas.
4. Developer validation commands.
5. Jira subtask key after creation.
6. Developer-owned status.

Every Jira development subtask description must include:

1. Objective: the concrete outcome for the stage.
2. Affected area: files, modules, docs, workflow surfaces, or integration
   boundaries expected to change.
3. Validation expectation: focused checks or commands that prove the stage is
   complete.
4. Completion evidence: commit SHA, changed files, validation result, and any
   handoff notes needed by Review or Tester agents.

Only one stage can be `in_progress` at a time. If no stage is explicitly active,
the next non-done stage is the stage the Developer Agent should work on.
Session-mode validation for the full delivery chain is documented in
`docs/session-mode-delivery-flow-validation.md`.

## Required Implementation Sequence

Developer Agents process a code implementation story in this order:

1. Load `AGENTS.md`, the Developer role file, and required workflow/context
   documents.
2. Confirm the parent Jira issue is `READY TO START`.
3. Check dependency invariants and unresolved linked Bugs.
4. Confirm acceptance criteria, context pack, and validation commands are
   present.
5. Create Jira development subtasks or record the approved no-subtask
   exception.
6. Create the feature branch or isolated worktree.
7. Implement one active subtask at a time.
8. Validate the active subtask and commit that stage.
9. Update the matching Jira subtask with completion evidence and move it to the
   closest done status after validation passes.
10. Open a ready-for-review pull request after all development subtasks are
    committed.

## Jira Subtasks

The workflow converts each stage into configurable `JiraIssueFields`:

1. Summary includes the parent key and stage title.
2. Issue type defaults to `Subtask` but can use the configured Jira subtask type.
3. Parent key is always the story or bug being implemented.
4. Labels include `developer-subtask`.
5. Description includes context pack, expected changes, and validation commands.

`execute_developer_subtask_creation` creates the subtasks through the configured
Jira project adapter and returns a keyed plan that can be stored by the worker.

## Stage Updates

When a stage is complete, the Developer Agent records a Jira note with:

1. Stage id and title.
2. Commit SHA.
3. Changed files.
4. Validation results.
5. Additional implementation notes.

The subtask should move to the configured done status after developer validation
passes. Story-level testing remains the Tester Agent's responsibility after the
pull request is merged to `main`.

## Missing Context

The workflow creates PO inbox blocking questions when implementation would start
without required context:

1. Missing context pack.
2. Missing acceptance criteria.
3. Missing developer validation commands.

This keeps implementation from silently inventing product scope or accepting
work that cannot be verified.
