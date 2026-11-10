# Jira Workflow And Dependency Links

The Jira workflow/link adapter extends the project issue adapter with operations
needed by schedulers, developer agents, tester agents, and review agents.

## Workflow Transitions

Workers use the adapter to:

1. Read available transitions for an issue.
2. Match transitions by target status or transition name.
3. Transition an issue to a configured workflow status.
4. Read the issue again after transition so durable state can record the
   resulting status.

Agents must not assume every Jira project has the same transition ids. Transition
ids are discovered per issue at runtime.

Transition policy for review, testing, Product Owner acceptance, Test issues,
Bugs, and development subtasks is documented in
`docs/jira-status-transition-workflow.md`.

## Blocks Link Direction

The platform method is:

```text
create_blocks_link(blocker_key, blocked_key)
```

The Jira Cloud create payload uses:

```text
outwardIssue = blocker_key
inwardIssue = blocked_key
type.name = Blocks
```

Scheduler dependency reads use the same convention:

1. `blockers` are prerequisite issues that block the current issue.
2. `blocked` are downstream issues blocked by the current issue.

For a current issue, an `outwardIssue` in returned Jira issue links is treated as
a blocker of the current issue. An `inwardIssue` is treated as an issue blocked
by the current issue.

This convention must be covered by contract tests because Jira link labels are
configurable by administrators and the raw Jira API fields are not enough on
their own to express product meaning.

## Scheduler Usage

Before assigning a story, the scheduler should call `get_dependency_links`.

An issue can start only when:

1. Its blockers are complete enough for development eligibility.
2. No unresolved blocking bugs are linked to the prerequisite work.
3. The Product Owner has moved the dependent issue to `READY TO START`.

The Product Owner's `ACCEPTED/DONE` status remains the sprint-level acceptance
gate and is not required for development dependency unblocking unless the issue
explicitly says so.

The dependency eligibility checker uses the adapter result to make the
assignment decision and write a durable note. By default, `TEST COMPLETED` and
`ACCEPTED/DONE` prerequisite statuses unblock dependent development, while
unresolved linked Bugs keep the dependent story ineligible.

Unknown prerequisite status is treated as blocked. This prevents worker
assignment when Jira link details were not available or the adapter could not
read the linked issue status.

## Mock Behavior

`MockJiraProjectIssueAdapter` supports:

1. Issue creation in an in-memory project.
2. Transition discovery and status updates.
3. Blocks link creation.
4. Scheduler-facing blocker and blocked reads.

Use the mock for local tests and workflow dry runs. Use
`jira_cloud_adapter_from_settings(settings)` for live Jira Cloud work.
