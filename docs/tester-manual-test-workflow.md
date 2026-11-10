# Tester Manual Test Workflow

The Tester Agent manual workflow creates or updates Jira `Test` issues and
uses them as AgileTest-style manual Test Cases.
Session-mode validation for the full delivery chain is documented in
`docs/session-mode-delivery-flow-validation.md`.

## Test Case

Each manual Test Case plan includes:

1. Covered Story or Bug key.
2. Jira Test issue key when the Test already exists.
3. Manual steps with expected results.
4. Regression classification labels.
5. Evidence requirement flag.

For configurable classification and optional AgileTest mapping behavior, see
`docs/regression-classification-agiletest-mapping.md`.

For Scrum-board visibility during sprint or release regression, see
`docs/behavioral-regression-visibility.md`.

For durable non-simple test evidence artifacts and redaction rules, see
`docs/test-evidence-artifact-workflow.md`.

For sprint regression overview Test Execution requirements and accepted skip
cases, see `docs/agiletest-test-execution-policy.md`.

The Test issue remains in a To Do-style status such as `FUNNEL`. Execution
pass/fail is recorded in the Test Execution or Test Cycle context.

## AgileTest Link

The planned link uses:

```text
Link type: AgileTest
Outward relationship: tests
```

The Test issue links to the covered Story or Bug.

## Execution Result

Manual execution records:

1. Test Case key.
2. Result: `passed`, `failed`, `blocked`, or `not-run`.
3. Tester role.
4. Execution datetime.
5. Test Execution and optional Test Cycle keys.
6. Evidence path when required.
7. Failed acceptance criteria for failed runs.

When Tester Agent participates in sprint regression overview work, it must
handoff enough detail for Release Manager to either create/reference an
AgileTest Test Execution key or record the approved skip justification.

Passed story testing targets Jira status `TEST COMPLETED`.

Before moving a Story or Bug to `TEST COMPLETED`:

1. At least one linked AgileTest-style Jira `Test` issue is required for
   reusable coverage.
2. The linked Test Case must include inspectable manual scenario steps or an
   inspectable automated coverage mapping.
3. Stories labeled `one-time-validation` may skip reusable Test Case creation
   only when the testing evidence explains why the validation is intentionally
   one-time.

## Failure Handoff

When failed-test bug creation is configured, the workflow emits a Bug creation
plan containing the story key, Test issue key, failed acceptance criteria, and
execution evidence summary.

The full bug linking, developer rework pickup, and retest loop belongs to
the Tester Bug Retest Workflow documented in
`docs/tester-bug-retest-workflow.md`.

## Stacked PR Testing

Default functional testing still happens after merge to `main` or a release
branch. Early or parallel stacked PR testing is allowed only when the sprint
path marks the story as `stack-testable-before-merge` and provides a stable
branch or preview environment.

Tester Agent classifies each stacked story as:

1. `testable-now`
2. `wait-for-lower-layer`
3. `wait-for-merge`
4. `stale-retest-required`
5. `blocked-needs-po`

Stacked evidence records must include stack id, layer, branch, base SHA, head
SHA, environment or preview, covered acceptance criteria, evidence path, and
whether the evidence is `final`, `provisional`, or `stale`.

Provisional evidence is useful for early feedback but does not count for release
acceptance or regression manifests until the story is merged and retested, or
until the Product Owner explicitly approves provisional evidence for a specific
release decision. Stale evidence is never counted.

When lower layers fail or their reviewed head SHA changes, upper-layer
provisional evidence is marked `stale-retest-required`. Tester Agent reports the
stale state and waits for Developer Agent rebase or refreshed branch work before
counting the evidence again.

Bugs found during stacked PR testing must include stack metadata: story key,
Test issue key, stack id, layer, branch, base SHA, head SHA, preview when
available, and evidence path.
