# Documentation-To-Backlog Traceability Audit

Status: Release 1.2 process contract for `AGENT-694`.

The documentation-to-backlog traceability audit prevents actionable knowledge
from remaining only in Markdown or an optional Confluence mirror. Documentation
can and should hold AI/operator context, but implementation-worthy product,
process, architecture, roadmap, agent, operator UI, or integration commitments
must have visible Jira traceability or an explicit Product Owner decision.

## When To Run

Product Planning runs the audit:

1. Before creating Jira issues from approved docs.
2. Before asking the Product Owner to approve Jira creation from backlog
   drafts.
3. During release planning when roadmap/docs changed since the last approved
   backlog.
4. During retro follow-up triage when accepted findings change future process
   or implementation behavior.

Release Manager may also run the audit before release closure when release
notes, roadmap, or closure packages introduced follow-up commitments.

## Inputs

The audit uses local files and configured mirrors so unit tests and dry runs can
execute without live external calls:

1. Local Markdown documentation roots.
2. Optional Confluence mirror/input roots.
3. Jira-like issue metadata exported from Jira or supplied by the planning
   workflow.
4. Project identity: project id, project name, Jira project key, docs roots,
   Confluence space when enabled, and release target.

## Extraction

The extractor records each actionable commitment with:

1. Stable commitment id.
2. Normalized commitment id and content fingerprint.
3. Commitment kind.
4. Source type: `local_doc` or `confluence_mirror`.
5. Source path, heading, line number, and heading anchor.
6. Project identity and release target in every report row.

Actionable markers include must/should/required/need/add/implement/create,
agent responsibilities, operator UI requirements, integration requirements,
roadmap/future/deferred notes, and explicit doc-only/rejected decisions.

## Matching

The audit matches commitments to Jira-like issues through:

1. Explicit issue keys in the commitment text.
2. Labels that contain commitment ids, content fingerprints, or source slugs.
3. Issue descriptions that reference commitment ids, content fingerprints, or
   line-level source references.
4. Summary token overlap when the issue summary clearly describes the same
   commitment.

Heading-only source references are not enough by themselves because one heading
can contain several unrelated commitments.

## Classification

Every row is classified as one of:

1. `covered-by-jira`
2. `covered-by-doc-only`
3. `duplicate`
4. `deferred-roadmap`
5. `rejected`
6. `needs-po-decision`
7. `missing-jira-reflection`

Duplicates are based on the normalized content fingerprint or ambiguous
multi-issue matches. Missing implementation-worthy commitments are never
silently promoted; they are routed according to the configured follow-up policy.

## Follow-Up Policies

Supported follow-up policies:

1. `draft-backlog-candidate`: produce reviewable candidate records whose target
   Jira status is `FUNNEL`.
2. `po-inbox-question`: create Product Owner inbox questions asking whether the
   commitment should become Jira work, remain doc-only, be deferred, or be
   rejected.
3. `report-only`: save the report and do not create follow-up artifacts.

Product Planning must show the report summary and follow-up rows before final
Jira creation. The Product Owner remains the final gate for missing or
ambiguous scope.

## CLI

Run a local audit with no live Jira or Confluence calls:

```bash
agentic docs-traceability audit \
  --docs-root docs \
  --confluence-mirror-root data/confluence-mirror \
  --jira-issues-json data/jira-exports/release-1.2-issues.json \
  --report-root data/documentation-traceability-reports \
  --report-id release-1.2-preplanning \
  --project-id AGENT \
  --project-name "Agentic Boilerplate" \
  --jira-project-key AGENT \
  --release-target 1.2.0 \
  --follow-up-policy draft-backlog-candidate
```

The command returns a non-zero exit code when the report has
`missing-jira-reflection` or `needs-po-decision` rows. That exit code is a
planning gate, not a runtime crash.

## Agent Rules

Product Planning Agent must load this audit before creating Jira stories from
approved docs or before asking for final PO approval of a backlog draft.

Docs/Confluence Agent must update docs with explicit doc-only, deferred,
rejected, or Jira references when the audit finds ambiguous commitments.

Orchestrator must not assign implementation work that exists only as a doc
commitment without a Jira issue or Product Owner-approved follow-up route.

Release Manager must include unresolved report rows in sprint/release closure
risk when those rows change implementation scope, regression scope, or release
process.
