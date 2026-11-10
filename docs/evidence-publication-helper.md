# Evidence Publication Helper

Release 1.2 publishes curated report summaries to GitHub Pages by default while
keeping raw evidence in durable local storage for worker context.

## Command

Use the docs-site publication command after story, regression, sprint closure,
retro, or release-report evidence is approved for publication:

```bash
agentic docs-site publish-reports \
  --input data/report-publication/<release>-<sprint>.json \
  --docs-root docs \
  --retry-root data/publication-retries \
  --project-root .
```

Use `--json` when another agent needs machine-readable output.

## Source JSON

The input file contains release/sprint identity, a generation timestamp, and a
list of curated artifacts:

```json
{
  "release_id": "1.2.0",
  "sprint_id": "R1.2 S5",
  "generated_at": "2026-08-10T00:00:00Z",
  "artifacts": [
    {
      "title": "AGENT-698 GitHub Pages deployment evidence",
      "artifact_type": "test_evidence",
      "source_path": "data/agent-logs/AGENT-698/test-evidence-20260810T132049Z.md",
      "visibility": "po_visible",
      "summary": "Post-merge validation passed for the Pages deployment workflow.",
      "jira_issue_key": "AGENT-698",
      "github_pr_url": "https://github.com/example-org/agentic-boilerplate/pull/191",
      "agiletest_key": "AGENT-914"
    }
  ]
}
```

Allowed `artifact_type` values:

1. `test_evidence`
2. `regression_evidence`
3. `regression_manifest`
4. `sprint_retro`
5. `sprint_closure`
6. `release_notes`
7. `partner_report`

Allowed `visibility` values:

1. `po_visible`
2. `partner_report`
3. `internal_only`

## Publication Rules

The helper publishes metadata and curated summaries only. It does not embed raw
evidence body text into GitHub Pages.

The helper publishes references to repo evidence; it does not convert every
local artifact into a shared document. Test logs, review notes, dependency
checks, setup validation records, and local validation summaries stay in the
repo evidence locations defined by
`docs/shared-evidence-publication-policy.md`. Only redacted, curated summaries
are candidates for the configured documentation provider. For AP, the Product
Owner has selected Confluence; other projects retain the GitHub Pages default
unless their provider configuration says otherwise.

Published report pages include:

1. Release and sprint identifiers.
2. Local evidence path for worker context.
3. Jira issue reference.
4. GitHub PR reference when available.
5. AgileTest or Test issue reference when available.
6. Visibility classification.
7. Curated summary.

`internal_only` artifacts are skipped from the published Pages tree and remain
available only through their durable local paths.

`partner_report` artifacts are blocked when the source artifact contains common
secret markers. The Release Manager or Docs Publication Agent must redact the
artifact, regenerate the summary, or create a Product Owner inbox question.

## Retry Records

When publication cannot proceed, the helper writes a durable retry JSON record
under the configured retry root. The retry record includes:

1. Release and sprint identifiers.
2. Artifact metadata.
3. Failure reason.
4. Next action.

Retry records preserve the publication attempt without losing report content or
hiding the failure in chat.

## Agent Responsibilities

Release Manager Agent:

1. Builds the publication source JSON from completed story evidence,
   regression evidence, sprint retro, sprint closure, release notes, and
   partner report summaries.
2. Runs `docs-site publish-reports`.
3. Publishes or comments the resulting GitHub Pages URL when the Pages workflow
   deploys.
4. Keeps Confluence publication optional and only uses it when the project
   documentation provider includes Confluence.

Docs Publication Agent:

1. Maintains this helper and the shared publication policy.
2. Verifies report visibility classifications.
3. Treats retry records as blockers for release publication when the report was
   required for PO or partner review.

Tester Agent:

1. Produces story-level evidence.
2. Provides concise summaries and references for Release Manager publication.
3. Keeps raw logs, credentials, failed requests, and role scratch notes out of
   partner-facing report summaries.
