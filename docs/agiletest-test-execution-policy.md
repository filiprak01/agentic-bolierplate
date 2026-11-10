# AgileTest Test Execution Policy

This policy defines when sprint regression overview work must create or
reference an AgileTest Test Execution key, and when a documented skip is
acceptable.

The policy applies to Release Manager and Tester Agent work for sprint and
release regression overviews. It does not replace story-level Test Case
coverage requirements.

## Default Policy

Create or upsert an AgileTest Test Execution key for sprint regression when
the sprint includes reusable product or worker-facing behavior validation.

Reusable behavior includes:

1. Parser, API, export, upload, UI, security, persistence, or integration
   behavior that can regress in later releases.
2. Worker-facing automation, command, CI, GitHub/Jira helper, evidence, or
   regression workflow behavior used by future agents.
3. Manual or automated Test Cases already mapped to the sprint or release
   regression scope.

The Test Execution key should be referenced by:

1. The board-visible regression overview Task.
2. The regression manifest.
3. Jira comments that publish regression evidence.
4. Closure notes when sprint closure consumes the regression result.

## Accepted Skip Cases

A sprint regression overview may skip AgileTest Test Execution creation only
when Release Manager records an explicit skip justification in the overview
evidence and Jira comment.

Accepted skip cases are:

1. The sprint contains only documentation, planning, closure, or one-time
   governance work with no reusable behavior to execute.
2. AgileTest credentials, project permissions, or integration setup are
   unavailable, and durable local evidence plus Jira comments are still posted.
3. The Product Owner explicitly approves a Jira-comment plus durable-manifest
   evidence path for the sprint.
4. Regression is intentionally dry-run or setup-only, and no Test Case result
   should be represented as an executed AgileTest run.

Skipping the Test Execution key is a warning, not a silent success. The warning
must be carried into sprint closure until the Product Owner accepts the closure
or creates a follow-up story.

## Skip Justification

When skipping Test Execution creation, Release Manager records:

1. Why no AgileTest Test Execution key was created.
2. Whether the skip is temporary, intentional, or caused by missing
   credentials/setup.
3. The durable regression manifest path.
4. The durable regression evidence path.
5. The Jira regression overview Task key.
6. The Product Owner approval or follow-up Jira key, when applicable.

Use this wording in the regression overview warning:

```text
AgileTest Test Execution skipped: <reason>. Durable manifest: <path>.
Durable evidence: <path>. Follow-up/approval: <Jira or PO inbox key>.
```

## Release Manager And Tester Handoff

Tester Agent supplies executed Test Case results, evidence paths, and whether
each case is manual, automated, supporting validation, or not run.

Release Manager decides whether the sprint regression overview is
publication-ready:

1. Test Execution present: publish as ready when manifest and evidence paths
   are also present.
2. Test Execution skipped with accepted justification: publish as ready with
   warning and carry the warning into closure.
3. Test Execution missing without justification: block closure publication or
   create a PO inbox item before closing the sprint.

If the accepted policy later requires automation changes, create a separate
Developer-owned Jira story in `FUNNEL`. Do not implement automation silently
inside a release-manager closure task.
