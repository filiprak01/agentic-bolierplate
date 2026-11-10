# Jira Status Transition Workflow

This workflow defines policy decisions for review, testing, Product Owner
acceptance, Test issues, Bugs, and development subtasks.

The domain policy returns allowed or blocked transition decisions. It does not
call Jira directly. Jira adapters execute transitions after the policy has
confirmed that the requested move is valid.

## Review To Tester Handoff

Review Agent merges clean pull requests, confirms the Story or Bug remains in
`DEV COMPLETED`, and emits a `test_requested` handoff.

Tester Agent may move Story or Bug issues from `DEV COMPLETED` to
`IN TESTING` only when:

1. The pull request was merged to `main`.
2. Review passed.
3. The issue is a Story or Bug.

This keeps Review ownership on PR quality/merge and Tester ownership on
validation status.

## Tester Pass

Tester Agent may move Story, Bug, or explicit testing Subtask issues to
`TEST COMPLETED` only when:

1. Tester validation passed.
2. No unresolved linked Bugs remain.
3. Every linked Bug in the tested scope was retested.
4. Reusable work has at least one linked AgileTest-style Test Case.
5. The linked Test Case includes scenario steps or automated coverage mapping
   that the Product Owner can inspect.

Stories labeled `one-time-validation` may skip reusable Test Case creation only
when the evidence explains why the check is intentionally one-time.

When this transition is allowed, bug marker labels can be removed.

## Tester Failure

When testing fails, Tester Agent may return Story or Bug issues to
`DEV COMPLETED` only when:

1. Tester validation failed.
2. At least one Bug was created or linked.

The transition decision adds `bug-related` and `has-linked-bug` marker labels so
Developer Agent and scheduler scans can pick up rework before new work.

## Story Acceptance

The Product Owner controls execution by moving approved scope to
`READY TO START`.

After that, story-by-story acceptance may be completed by the Release Manager
or Story Agent when:

1. The current status is `TEST COMPLETED`.
2. Tester validation passed.
3. No unresolved linked Bugs remain.
4. Reusable Test Case coverage exists, or one-time validation is explicitly
   labeled and explained.

The Product Owner may still move work to `ACCEPTED/DONE` manually with an
explicit approval flag. Product Owner validation then happens at sprint or
release readiness instead of stopping every completed story.

## Process Story Closure

Process stories that change boilerplate documentation, role guidance, CI,
helper tooling, repository configuration, or workflow policy can skip Tester
Agent execution only when the Jira story explicitly does not require a
post-merge Tester Agent pass. In that case, the responsible process owner may
move the story to `ACCEPTED/DONE` after:

1. The ready-for-review pull request is opened or the documented no-code action
   is complete.
2. The responsible role records validation evidence and related Jira keys.
3. Any process-review, release-manager, or Product Owner handoff is documented.
4. No unresolved blocking bugs or prerequisite links remain.

Pull request merge ownership remains with the documented process-review or
merge owner. Developer Agent does not merge process-story pull requests while
closing development work.

## Development Subtasks

Development subtasks move to `ACCEPTED/DONE` or the closest done-like status
after developer validation passes.

Development subtasks do not move to `TEST COMPLETED` unless they are explicit
testing subtasks. Tester Agent validates the parent Story or Bug as a whole
after merge to `main`.

## Test Issues

Jira `Test` issues remain in `FUNNEL` or the configured To Do-style status.

Test pass/fail belongs to AgileTest Test Execution records, not the Test Case
issue workflow status.
