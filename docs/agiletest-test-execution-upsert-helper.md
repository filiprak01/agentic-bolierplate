# AgileTest Test Execution Upsert Helper

Status: implemented for MVP Sprint 10

This helper gives Release Manager a deterministic way to create or update the
AgileTest-style Jira `Test execution` artifact without duplicating lookup,
summary, label, and linking logic in higher-level publication workflows.

## Scope

The helper owns:

1. Create-vs-update decision making.
2. Configurable Jira project key, issue type, labels, and link types.
3. Deterministic Test Execution summary and description defaults.
4. `EvidenceLinkPlan` output for:
   - overview Task -> Test execution
   - Test execution -> Test Case
5. Failure records that always preserve the durable local evidence path.

The helper does not own regression manifest orchestration or broader release
publication flow. That remains with higher-level release stories such as
AGENT-198.

## Idempotency

The helper updates an existing Test Execution when either:

1. The caller already knows the execution issue key.
2. A precomputed lookup result resolves to exactly one matching execution.

If neither source is available, the helper plans a create operation using a
placeholder key in dry-run mode and replaces it with the created key during
live execution.

If a lookup returns more than one match, the helper fails fast instead of
guessing which execution should be updated.

## Execution Boundary

Dry-run mode requires no live adapter and is intended for local tests and
planning.

Live execution goes through a small adapter boundary that can:

1. Create a Test Execution and return the created key.
2. Update an existing Test Execution.

This keeps Jira or AgileTest transport details out of the core domain helper.

## Evidence Publication Contract

The helper reuses the AGENT-134 evidence publication contract by returning an
`EvidencePublicationRequest` containing `EvidenceLinkPlan` records.

That lets a higher-level workflow reuse the same publisher boundary for:

1. Jira comments.
2. Evidence attachments.
3. Overview, Test Execution, and Test Case links.

## Failure Handling

When live create or update fails, the helper returns a failure record with:

1. The attempted operation.
2. The execution key or placeholder.
3. The durable local evidence path.
4. The transport error message.

This keeps the recovery path explicit for retries, Jira comments, or manual
publication.
