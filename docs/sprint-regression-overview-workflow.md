# Sprint Regression Overview Workflow

Release Manager uses this workflow to prepare the board-visible Sprint
regression overview, the delivery board filter, and the durable publication
references that point to regression evidence.

The workflow composes the existing behavioral regression visibility and
regression artifact publication helpers instead of replacing them.
AgileTest Test Execution requirements and accepted skip cases are defined in
`docs/agiletest-test-execution-policy.md`.

Evidence channel and redaction rules are governed by
`docs/shared-evidence-publication-policy.md`.

## Inputs

The overview plan uses:

1. Sprint name.
2. Release label.
3. Sprint label.
4. Project-specific board filter configuration.
5. Behavioral regression items.
6. Supporting validation items.
7. Test execution key when available.
   If no Test Execution key is available, Release Manager must provide the
   skip justification required by `docs/agiletest-test-execution-policy.md`.
8. Regression manifest key and path when available.
9. Durable evidence path when available.

## Outputs

The workflow produces:

1. A board-visible regression overview Task plan.
2. A delivery board filter plan that excludes AgileTest artifact issue types.
3. Jira link plans from the overview Task to the execution and Test Cases.
4. A durable Markdown summary for local evidence and Jira comments.
5. Warnings when manifest, evidence, or execution inputs are missing.

## Classification Rules

1. User-facing and worker-facing checks are behavioral regression.
2. Setup-only, schema-only, and internal-storage checks are supporting
   validation unless they expose visible behavior.
3. The Scrum delivery board should not show AgileTest artifact issue types.
4. The regression overview should point to the durable manifest after execution
   completes.
5. Missing Test Execution keys are warnings only when a documented policy skip
   exists. Missing Test Execution keys without a skip justification block
   closure publication or require a PO inbox decision.

## Ready State

The overview plan is publication-ready only when Release Manager supplies:

1. A regression manifest key.
2. A durable regression manifest path.
3. A durable regression evidence path.
4. A test execution key, or an accepted skip justification that names the
   durable manifest, durable evidence, and PO approval or follow-up key.

If one of those inputs is missing, the workflow still renders a useful dry run,
but it leaves a warning trail for the publication step.

When publication-ready, Release Manager should publish a partner-safe GitHub
Pages report summary for the regression overview. The page links back to Jira
and durable evidence paths without embedding raw logs, role notes, source
documents, or unredacted sensitive content.

Confluence publication is optional when the project documentation provider
selects Confluence or `both`. Optional Confluence output must reference the
same regression overview Task and durable evidence paths.
