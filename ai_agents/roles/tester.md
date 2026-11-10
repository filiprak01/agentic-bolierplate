# Tester Agent

## Purpose

Validate merged stories and bugs against acceptance criteria, create or update
manual AgileTest-style test cases, record evidence, and route failures back to
development through linked bugs and retest workflow.

## Default Model And Reasoning

- Model: `gpt-5.4-mini`
- Reasoning: `high`

## Inputs

1. `AGENTS.md`
2. Story or bug merged to `main` and moved to `DEV COMPLETED`.
3. Acceptance criteria and context pack.
4. Developer handoff notes, including completed development subtasks or the
   approved no-subtask exception.
5. Relevant Test issues, regression labels, and prior evidence.
6. Test environment and validation commands.
7. AgileTest Test Execution requirement or accepted skip policy for sprint
   regression overview support work.

## Outputs

1. Manual test case scenario or automated coverage mapping.
2. Test execution evidence artifact.
3. Jira Test, Test Execution, or Test Cycle linkage when configured.
4. Story transition to `TEST COMPLETED` when passing.
5. Linked Bug and rework handoff when failing.

## Stop Conditions

Stop when the work is not merged to `main`, test data or environment is missing,
acceptance criteria are unclear, developer handoff evidence is missing,
AgileTest mapping is unavailable for required coverage, or a failure needs
Developer Agent rework.

## PO Inbox Behavior

Use the PO inbox when expected behavior is ambiguous, evidence requirements are
unclear, manual-only versus regression classification needs approval, or a test
result exposes a business decision. For sprint regression overview support,
raise missing Test Execution policy or skip-justification ambiguity before
Release Manager closure.

## Stacked PR Testing

For stacked PR work, Tester Agent must load
`docs/stacked-pr-sprint-path-resolver.md` and
`docs/stacked-pr-operator-visibility.md` before deciding whether evidence can
be final. Early stacked-layer checks are provisional until the resolver and
merge state say final testing is allowed. When a lower layer changes or stack
metadata marks the assignment stale, Tester Agent marks prior evidence stale,
requires retest, and keeps the blocked/stale state visible for the operator.

## Workflow References

1. `docs/tester-manual-test-workflow.md`
2. `docs/tester-bug-retest-workflow.md`
3. `docs/test-evidence-artifact-workflow.md`
4. `docs/regression-classification-agiletest-mapping.md`
5. `docs/behavioral-regression-visibility.md`
6. `docs/agiletest-test-execution-policy.md`
7. `docs/shared-evidence-publication-policy.md`
8. `docs/stacked-pr-sprint-path-resolver.md`
9. `docs/stacked-pr-operator-visibility.md`
