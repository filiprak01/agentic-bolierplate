# Confluence Documentation Adapter

The Confluence adapter is the optional shared documentation boundary used by
agents when approved reusable knowledge should be created or updated in
Confluence and mirrored locally for durable context generation.

Release 1.2 defaults documentation publication to GitHub Pages as described in
`docs/github-pages-documentation-strategy.md`. Confluence is preserved as a
fallback or secondary provider for projects that explicitly enable it.

## Runtime Configuration

Configure the target Confluence space through environment variables:

```text
CONFLUENCE_BASE_URL=https://your-site.atlassian.net/wiki
CONFLUENCE_SPACE_KEY=<space-key>
CONFLUENCE_PARENT_PAGE_ID=<parent-page-id>
CONFLUENCE_EMAIL=integration-user@example.com
CONFLUENCE_API_TOKEN=<confluence-api-token>
```

The current dogfooding space uses:

```text
CONFLUENCE_SPACE_KEY=AGENT
CONFLUENCE_PARENT_PAGE_ID=458864
```

These values are examples for this boilerplate project only. New projects must
provide their own space key and parent page id.

## Adapter Selection

Use `confluence_cloud_adapter_from_settings(settings)` for live Confluence work.

Use `MockConfluenceDocumentationAdapter` for local tests, dry runs, and workflow
validation that must not call Confluence.

Both adapters implement the same documentation contract:

1. Validate configured space and parent page access.
2. Read the configured space.
3. Read individual pages with storage-format content.
4. Create or update child pages under the configured parent.
5. Mirror page content to durable local storage.

## Optional Provider And Mirror

Confluence is not the default Release 1.2 documentation source of truth. Local
Markdown in Git is the editable source and GitHub Pages is the default published
view when the configured documentation provider is `github_pages`.

Local mirror files are durability and context-generation artifacts for projects
that enable Confluence. They should not replace the Git source when GitHub
Pages is selected.

Mirror files are written under the configured durable mirror root by space key
and page id:

```text
data/confluence-mirror/<space-key>/<page-id>.md
```

Each mirror file includes page metadata and the Confluence storage-format body.

Before a Docs/Confluence worker starts Confluence publication, local setup
validation must also prove that the space-specific mirror directory can be
created and written:

```text
data/confluence-mirror/<space-key>/
```

This check is separate from live Confluence access. Live access proves the
worker can read or write Confluence; mirror readiness proves the worker can
persist the durable local copy that later agents and context-pack generation
need for recovery.

## Report Publication

Release 1.2 workflows publish approved report artifacts to GitHub Pages by
default. Projects that explicitly enable Confluence may also publish approved
report artifacts to Confluence, with local repo files kept as durable mirrors.

Report artifacts include:

1. Story test evidence summaries.
2. Regression evidence and manifests.
3. Sprint retros and closure notes.
4. Release notes and readiness summaries.
5. Post-mortems.
6. Partner-facing delivery or quality reports.

Publishing should preserve links back to Jira issues, GitHub pull requests,
local evidence paths, and AgileTest artifacts when available.
Publication channels and redaction defaults are documented in
`docs/shared-evidence-publication-policy.md`.

Partner-facing pages should exclude internal-only role notes, raw debugging
logs, secrets, and unrelated worker context unless the Product Owner approves
that content for sharing.

## Startup Validation

Workers should validate Confluence access before accepting assignments that
require Confluence documentation writes. Validation should confirm:

1. The configured space exists and is accessible.
2. The configured parent page exists and is accessible.
3. The token can read page content.
4. Write-enabled workers can create or update child pages when their role
   requires it.

If Confluence is selected and validation fails, the worker must pause before
starting work and record the configuration issue in durable local state or the
PO inbox. If GitHub Pages is selected, missing Confluence credentials must not
block default project setup.
In short: missing Confluence credentials must not block default project setup
when the configured documentation provider is GitHub Pages.

## Secret Handling

Workers must never print `CONFLUENCE_API_TOKEN` in logs, Jira comments, errors,
evidence files, or PO inbox records.

Use `redacted_confluence_config(config)` for diagnostics. HTTP errors should
surface the Confluence response message only, not request headers or token
values.
