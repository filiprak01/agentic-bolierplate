# Test Evidence Artifact Workflow

Status: implemented for MVP Sprint 9

Non-simple test execution must produce durable evidence that the Product Owner
can audit without relying only on Jira comments that say `PASSED`.

## Evidence Artifact

Each evidence artifact includes:

1. Jira Story or Bug key.
2. Jira Test issue key.
3. Tester role.
4. Execution datetime.
5. Acceptance criteria and per-criterion result.
6. Commands executed.
7. Relevant output or logs.
8. Linked Bugs.
9. Evidence path.

Supported criterion results:

1. `passed`
2. `failed`
3. `blocked`
4. `not-run`

## Durable Paths

Recommended path pattern:

```text
data/agent-logs/{jira-issue-key}/test-evidence-{timestamp}.md
```

The path is deterministic by issue key and timestamp so a stopped worker can
resume or reference the same evidence location.

## Jira Comment Reference

The evidence workflow prepares a Jira comment reference without requiring live
Jira access in unit tests.

The comment reference includes:

1. Story or Bug key.
2. Test issue key.
3. Evidence path.
4. Summary result.

The Jira adapter can post this reference after evidence is written.

For consistent Jira comments, attachment attempts, AgileTest links, dry-run
mode, and failure handling, see `docs/evidence-publication-helper.md`.

Publication channel defaults are defined in
`docs/shared-evidence-publication-policy.md`. Story and bug evidence stays as a
durable local artifact plus a Jira comment unless the Product Owner approves a
broader sharing rule.

## Concise Jira-Only Evidence

Simple stories may use concise Jira-only evidence when configured.

Non-simple stories require acceptance criteria in the durable evidence artifact.

## Secret Redaction

Captured output is redacted before it is rendered.

The default redaction covers common values such as:

1. `token=...`
2. `api_key=...`
3. `secret=...`
4. `password=...`
5. `Bearer ...`

Agents should still avoid capturing unnecessary secrets in the first place.

## Agent Usage

Tester Agent creates this artifact after merged story testing.

Release Manager Agent references the evidence path from regression manifests
and board-visible regression overview Tasks.

The domain workflow does not write files directly. The worker runtime or
storage adapter writes the rendered Markdown to the planned durable path.

After the evidence file exists, Tester Agent should publish the evidence path
through the Jira and AgileTest evidence helper.

Tester Agent must not publish raw logs, role-specific notes, original source
documents, full extracted text, screenshots of source documents, scratch files,
or unredacted sensitive content as shared documentation.
