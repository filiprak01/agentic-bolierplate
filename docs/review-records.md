# Review Records

Review records are durable artifacts used by the Review Agent to track pull
request review state across review cycles.

## Scope

Each record captures:

1. Jira issue and pull request metadata.
2. Findings and requested changes.
3. Developer responses.
4. Final review decision.
5. Review scope: `diff-first` or `expanded-context`.
6. Model, reasoning, speed, and routing rationale.

## Conflict Policy

Merge conflicts are recorded as review findings with kind `conflict`.

They are not product bugs. The Review Agent sends the finding back to the
Developer Agent that owns the branch.

## Repeated Findings

Repeated findings are detected by stable finding fingerprint. Explicit
fingerprints are preferred when a review system can provide them. Otherwise the
platform derives a fingerprint from finding kind, file path, line, and title.

Findings marked `wont-fix` are not treated as repeated findings in later review
cycles, which prevents circular feedback after an intentional decision.

## Durable Storage

File-backed review records are stored as:

```text
<review-record-root>/<review-record-id>/review-record.json
```

The storage root is configured by the workflow that owns review execution.

## Stacked PR Layer Records

Stacked pull request reviews also store a layer-level record with:

1. Jira issue key and pull request metadata.
2. Stack id, lane id, and layer number.
3. Base branch and head branch.
4. Reviewed base SHA and reviewed head SHA.
5. Merge strategy: `bottom-up` or `queued-stack-merge`.
6. Approval readiness, merge readiness, and stale rebase status.

The reviewed base SHA is required because upper-layer reviews can become stale
when a lower layer changes after review. That stale state blocks approval and
returns the work to the owning Developer Agent for rebase or conflict handling.
