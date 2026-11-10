# Tester Bug Retest Workflow

The Tester Agent uses this workflow when a manual or behavioral test fails
after a story has been merged and moved into testing.

## Failed Testing Handoff

When testing fails, the Tester Agent prepares explicit Jira-effect plans:

1. Move the covered Story or Bug back to `DEV COMPLETED`.
2. Add `bug-related` and `has-linked-bug` labels to the covered issue.
3. Create a Jira Bug containing the failed acceptance criteria and evidence.
4. Link the Bug to the covered issue using the configured bug-blocking link.
5. Route rework to the original Developer Agent when available.

The domain workflow does not call Jira directly. It returns plans that a Jira
adapter, scheduler, or worker runner can execute.

The failed test receives a stable duplicate-detection signature based on the
covered issue, Test issue, and failed acceptance criteria. If that signature is
already mapped to an unresolved Bug, the Tester Agent reuses the existing Bug
instead of creating another one for the same failure.

After the Jira-effect plan is prepared, the worker publishes the durable
Developer rework handoff through:

```bash
agentic agent-messages publish-handoff \
  --current-status "IN TESTING" \
  --event testing_failed \
  --actor tester \
  --target-status "DEV COMPLETED"
```

The handoff must include the linked Bug, failed test evidence, bug-related
labels, retest scope, context pack path, and communication channel id. The
resulting durable message type is `bug_fix_requested` and targets the Developer
role.

## Developer Rework Pickup

Developer Agents and the scheduler must detect rework before taking new
`READY TO START` stories when this scan is enabled.

A story is a rework candidate when:

1. It is in `DEV COMPLETED`.
2. It has a bug-related marker label.
3. It has at least one unresolved linked Bug.

The assignment state records:

1. Story key.
2. Linked Bug keys.
3. Failed acceptance criteria.
4. Current developer agent or scheduler-required assignment reason.
5. Retest required flag.
6. Failed-test signature.
7. Durable `bug_fix_requested` message id when the handoff was published.

If the original Developer Agent is unavailable, the scheduler may assign another
eligible Developer Agent and records the fallback reason.

## Retest Gate

A story cannot move to `TEST COMPLETED` while linked Bugs remain unresolved or
resolved-but-not-retested.

After bug fixes are merged, the Tester Agent retests the story and linked Bugs.
Only then can the workflow remove the bug-related labels and target
`TEST COMPLETED`.

The retest handoff follows the normal Developer branch, PR, Review, merge, and
Tester validation path. Product Owner input is required only when the failed
behavior changes scope, expected behavior is ambiguous, or release/risk
acceptance is needed.

## Related Workflow

Manual Test Case creation and execution records are covered by
`docs/tester-manual-test-workflow.md`.
