# Regression Manifest Builder

Status: implemented for MVP Sprint 9

Regression manifests make sprint and release regression auditable. They list
which reusable Test Cases were executed, how each was executed, where evidence
was stored, and which board-visible or AgileTest artifact references the
manifest.

For stacked PR work, Release Manager includes only merged/final Tester evidence
by default. Provisional stacked evidence may be included only when the Product
Owner explicitly approves that release decision. Stale stacked evidence is
never included.

## Manifest Records

Each manifest record includes:

1. Test Case key.
2. Covered Story or Bug key.
3. Source sprint or release label.
4. Regression labels.
5. Regression classifications.
6. Execution mode.
7. Execution result.
8. Evidence path.
9. Optional automated coverage reference.

Supported execution modes:

1. `manual`
2. `automated`
3. `supporting-validation`

Supported results:

1. `passed`
2. `failed`
3. `blocked`
4. `not-run`

## Automated Coverage Mapping

Automated execution only counts as reusable regression coverage when each Test
Case is mapped to at least one of:

1. Command.
2. Test file.
3. Test function.

A full test-suite command alone is not enough unless each reusable Test Case is
represented in the manifest record with a command, file, or function mapping.

Coverage mappings are durable local records. The MVP store writes one JSON file
per Test Case under a configured coverage-mapping root:

```text
<coverage-mapping-root>/<test-case-key>/coverage-mapping.json
```

Each automated mapping stores:

1. Test Case key.
2. Covered Story or Bug key.
3. Coverage mode.
4. Command.
5. Test file.
6. Optional test function.
7. Optional source sprint and notes.

Manual-only Test Cases remain valid without automation metadata. Release
Manager readiness checks should warn when reusable automated Test Cases have no
mapping, but they should not block manual-only Test Cases for lacking automated
coverage.

When a mapped automated Test Case is included in a sprint or release
regression manifest, the mapping is converted into the manifest automated
coverage reference. This lets a full suite or focused subset run count only
when every reusable Test Case in scope is explicitly mapped to the executed
command, file, or function.

## One-Time Validations

`one-time-validation` records are excluded by default.

Release Manager can include them only when the Product Owner or release plan
explicitly requires them. The default manifest should focus on reusable
regression coverage.

## Required References

Each manifest references:

1. Board-visible regression overview Task.
2. AgileTest Test Execution when one exists.
3. AgileTest Test Cycle when one exists.
4. A documented AgileTest Test Execution skip justification when no Test
   Execution key is created.

The overview Task and AgileTest execution should include a link or comment to
the manifest evidence path.
When Test Execution is skipped, the overview Task and closure evidence must
carry the warning defined in `docs/agiletest-test-execution-policy.md`.

Use `docs/evidence-publication-helper.md` for the standard helper that posts
manifest evidence comments, plans attachments, and links overview Tasks, Test
executions, and Test Cases.

## Agent Usage

Release Manager Agent builds the manifest after sprint or release regression
execution.

Tester Agent supplies execution results and evidence paths.

Automation-aware Tester or Release Manager agents supply command, file, or test
function mappings for automated coverage.

The manifest is pure domain data and can be serialized to JSON or rendered to
Markdown for local files, Jira comments, or Confluence sync.

For the durable evidence files referenced by manifest records, see
`docs/test-evidence-artifact-workflow.md`.
