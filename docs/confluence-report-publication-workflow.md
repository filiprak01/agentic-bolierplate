# Confluence Report Publication Workflow

Status: implemented for `AGENT-201`

This workflow publishes durable execution and sprint artifacts into the
configured Confluence space while keeping local files as mirrors and context
inputs.

Channel and redaction defaults are governed by
`docs/shared-evidence-publication-policy.md`.

## Supported Artifact Classes

`ReportArtifactType` covers:

1. Story test evidence.
2. Regression reports.
3. Regression manifests.
4. Sprint retros.
5. Sprint closure notes.
6. Post-mortems.
7. Partner-facing summaries.

`classify_report_artifact_type` can infer the class from the artifact path or
title when explicit typing is not provided.

## Publication Plan

`ConfluenceReportPublicationPlan` defines:

1. Sprint or publication Jira issue key.
2. Confluence page title.
3. Report summary.
4. Included local artifacts.
5. Related Jira issues.
6. Optional parent page override.
7. Partner-safe filtering mode.

The workflow uses the configured Confluence adapter, so the target space and
parent page remain configurable and are not hardcoded to the AGENT space.

## Visibility And Filtering

Each `ReportArtifact` can carry:

1. Local path.
2. Jira issue keys.
3. GitHub PR URLs.
4. Role-specific notes.
5. Raw debug log paths.
6. Audience classification.

Partner-safe publication excludes:

1. Internal-only artifacts.
2. Raw debug log sections.
3. Role-specific note sections.
4. Credentials, source documents, full extracted text, screenshots of source
   documents, scratch files, and unredacted passenger, customer, or
   business-sensitive content.

Story-level evidence files remain local and board-visible through Jira comments
by default. Confluence pages may include redacted story summaries when they are
part of a regression, sprint closure, release readiness, or partner-facing
report.

Product documentation, release documentation, closure summaries, Product
Owner-facing documentation updates, documentation coverage indexes, and
cross-story process policies require Docs/Confluence publication when the
project selects Confluence as a documentation provider and the target and
redaction requirements are clear. AP selects this provider; the boilerplate
default for other projects remains GitHub Pages. Raw logs, secrets,
private data, noisy command output, source artifacts, and low-value internal
evidence remain repo evidence unless the Product Owner explicitly approves a
different publication rule.

## Result Handling

`execute_confluence_report_publication`:

1. Creates or updates the Confluence child page.
2. Mirrors the published page into durable local storage.
3. Produces Jira comment plans that reference the Confluence page URL and local
   mirror path.

`FileConfluenceReportPublicationStore` persists the result JSON so local
metadata can track page URL, mirror path, and Jira visibility actions.
