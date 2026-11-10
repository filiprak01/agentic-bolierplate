# Shared Evidence Publication Policy

Status: approved for `AP-29`; clarified for `AP-219`

This policy defines which delivery evidence is local-only, board-visible, or
shared-documentation visible. It applies to agent evidence created for Jira
stories, bugs, regression work, sprint closure, retrospectives, post-mortems,
and partner-facing summaries.

Product Owner approval source:
`AP-29-evidence-publication-policy-approval-20260719T003803`.

## Default Channels

Each evidence-producing worker keeps the durable local evidence file as the
source artifact.

Default local path pattern:

```text
data/agent-logs/<ISSUE_KEY>/
```

Story-level execution evidence uses Jira for board visibility. The worker
posts a concise Jira comment with:

1. The durable local evidence path.
2. A result summary.
3. Related test or issue keys when available.
4. A note when attachment upload was attempted and failed.

Jira attachments are optional. Workers may attach evidence when credentials,
project settings, and file sensitivity allow it, but attachment failure must
not remove or replace the durable local path reference.

GitHub Pages is the default shared-documentation channel for report-level
artifacts:

1. Regression evidence summaries.
2. Regression manifests.
3. Sprint retros.
4. Sprint closure notes.
5. Post-mortems.
6. Release notes and readiness summaries.
7. Partner-facing delivery or quality summaries.

Published report pages are generated into the repository documentation tree
under:

```text
docs/reports/<RELEASE_ID>/<SPRINT_ID>/
```

Raw local evidence remains available under the durable source path for worker
context. After publication, Jira receives a comment with the GitHub Pages URL
or dry-run artifact reference, related Jira keys, local evidence paths, and any
unresolved Product Owner decisions.

Confluence publication is optional when a project explicitly enables the
adapter. Optional Confluence output must not replace the GitHub Pages report
record unless the Product Owner selects Confluence as the configured provider.

## Repo Evidence And Documentation Boundary

Repo evidence is the durable source of record for execution proof, agent
handoff context, and local validation traceability. The configured documentation
provider is the human-facing surface for product, release, closure, and
Product Owner-facing summaries. AP explicitly selects Confluence; this does not
change the GitHub Pages default for other projects. Agents should not treat
every local evidence file as a shared-documentation page candidate.

Artifacts that count as repo evidence include:

1. Test logs and test evidence files.
2. Regression manifests and regression overview notes.
3. Review notes, PR review summaries, and review completion records.
4. Release closure notes and sprint closure notes.
5. Local validation summaries.
6. Dependency eligibility notes.
7. Setup validation records.
8. Branch, PR, publication, and blocked-publication records.
9. Product Owner inbox decision references.

Default repo evidence locations:

| Evidence type | Default local path |
| --- | --- |
| Story, bug, review, validation, closure, and publication evidence | `data/agent-logs/<ISSUE_KEY>/` |
| Dependency eligibility checks | `data/dependency-eligibility/<ISSUE_KEY>-*.md` |
| Published Confluence mirrors | `data/confluence-mirror/<SPACE_KEY>/<PAGE_ID>.md` |
| Product Owner questions and decisions | `data/po-inbox/` |
| Cross-role handoff notes | `data/handoffs/` |

Jira comments that reference repo evidence should include the local evidence
path, concise result, related AP keys, publication status, and any failed
attachment or publication attempt. The comment should let a human or agent find
the source artifact without copying raw logs into Jira.

For AP and other projects configured to use Confluence, Confluence publication
is required when the work changes or creates:

1. Product documentation.
2. Release documentation.
3. Sprint or release closure summaries.
4. Product Owner-facing documentation updates.
5. Documentation coverage indexes.
6. Process policies that future agents must follow across stories.

Confluence publication is not required for repo evidence that only proves a
single story's execution, local validation, dependency check, branch operation,
or PR workflow step. Those artifacts remain repo evidence plus Jira visibility
unless they are summarized inside a broader release, regression, retro,
closure, or Product Owner-facing document.

## Partner-Safe Filtering

Partner-safe publication excludes:

1. Internal-only artifacts.
2. Raw command logs.
3. Role-specific notes.
4. Debug traces.
5. Credentials, tokens, secrets, and environment dumps.
6. Stack traces or diagnostics that expose secrets or private infrastructure.
7. Original PDFs or source documents.
8. Full extracted text from source documents.
9. Screenshots of source documents.
10. Scratch files and temporary parser artifacts.
11. Unredacted passenger, customer, or business-sensitive content.

Agents should use synthetic or redacted data in published examples. If a report
cannot be made safe without losing required meaning, the worker creates a PO
inbox question and stops before publishing.

## Artifact Classification

Use these defaults unless a Product Owner approval says otherwise:

| Artifact | Default publication |
| --- | --- |
| Raw local command output | Local-only |
| Role-specific working notes | Local-only |
| Test logs or local validation summaries | Local file plus Jira comment |
| Dependency eligibility or setup validation notes | Local file plus Jira comment |
| Review notes or PR review completion records | Local file plus Jira or PR comment |
| Story or Bug test evidence | Local file plus Jira comment |
| Failed attachment attempt record | Local file plus Jira comment |
| Regression overview | GitHub Pages report summary plus Jira link |
| Regression manifest | GitHub Pages report summary plus local evidence path |
| Sprint retro | GitHub Pages report summary plus local evidence path |
| Sprint closure note | GitHub Pages report summary plus Jira link |
| Post-mortem | GitHub Pages report summary plus local evidence path |
| Release readiness or partner summary | GitHub Pages report summary plus Jira link |
| Product documentation update | Configured documentation provider plus durable source |
| Release documentation update | Configured documentation provider plus durable source |
| Product Owner-facing documentation update | Configured documentation provider plus durable source |

For AP's PO-selected Confluence provider, the shared-documentation rows use a
Confluence summary or page plus Jira visibility and a local mirror under
`data/confluence-mirror/<SPACE_KEY>/<PAGE_ID>.md`. Raw evidence stays in the
repository; it is not copied wholesale into either publication provider.

Story evidence may be summarized inside a GitHub Pages regression or release
page when the summary is redacted and linked back to the Jira issue. The raw
story evidence file remains local unless the Product Owner approves broader
sharing.

## Role Responsibilities

Tester Agent:

1. Creates durable test evidence for non-simple story and bug validation.
2. Posts the Jira evidence comment through the evidence publication helper.
3. Keeps raw output redacted and avoids collecting unnecessary sensitive data.

Release Manager Agent:

1. References story evidence paths from regression manifests and sprint
   summaries.
2. Publishes regression, retro, closure, and release summaries through the
   GitHub Pages report publication helper when the target and redaction rules
   are clear.
3. Records unresolved Product Owner decisions instead of burying them in
   reports.

Docs Publication Agent:

1. Maintains this policy and related workflow guidance after Product Owner
   approval.
2. Publishes approved shared-documentation summaries to GitHub Pages.
3. Uses Confluence only when the configured documentation provider enables it.
4. Links published report pages back to Jira.
5. For Confluence-configured projects such as AP, publishes and locally mirrors
   product and release documentation changes, approved closure summaries, and
   required Product Owner-facing documentation.
6. Keeps raw logs, noisy command output, private data, secrets, and
   low-value internal evidence out of shared documentation. A PO publication
   exception never removes the partner-safe filtering requirements.

## Verification Example

`AP-91` follows this policy for an existing AP release/sprint path:

1. The sprint closure evidence remains durable repo evidence at
   `data/agent-logs/AP-91/sprint-closure-publication-20260805T093000Z.md`.
2. The human-facing release summary is published and mirrored as
   `data/confluence-mirror/ExampleProject/21463042.md`.
3. The Confluence summary references the AP evidence path instead of copying
   raw command logs, source documents, or noisy internal output.

## Exception Handling

Create a PO inbox item before publishing when:

1. The publication audience is unclear.
2. Redaction requirements are unclear.
3. A raw artifact appears necessary for a shared report.
4. Evidence contains source documents, extracted text, screenshots, secrets, or
   customer-sensitive content.
5. The GitHub Pages target, workflow, or publication provider configuration is
   missing.
6. The Jira project requires a publication method not covered by this policy.

Rejected or unanswered publication decisions keep the artifact local-only until
the Product Owner resolves the inbox item.
