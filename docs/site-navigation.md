# Documentation Site Navigation

The GitHub Pages scaffold publishes selected approved Markdown pages with a
compact left navigation. Existing docs stay in their original paths so agents
can continue to use stable context references.

## Default Navigation

| Label | Path | Audience |
| --- | --- | --- |
| Product Owner Overview | [index.md](index.md) | `po_readable` |
| Getting Started | [getting-started.md](getting-started.md) | `po_readable` |
| PO Inbox And Operator UI | [operator-ui.md](operator-ui.md) | `po_readable` |
| Agent Roles | [ai-documentation-index.md](ai-documentation-index.md) | `ai_first_internal` |
| Workflow Map | [story-processing-path-matrix.md](story-processing-path-matrix.md) | `ai_first_internal` |
| Release Notes | [release-notes/release-1.1.0.md](release-notes/release-1.1.0.md) | `po_readable` |
| Published Reports | [reports/index.md](reports/index.md) | `partner_report` |
| Evidence Publication | [shared-evidence-publication-policy.md](shared-evidence-publication-policy.md) | `partner_report` |
| Report Publication Helper | [evidence-publication-helper.md](evidence-publication-helper.md) | `ai_first_internal` |

## Navigation Rules

1. Do not publish raw logs, secrets, failed request payloads, or role scratch
   notes.
2. Keep AI-first docs stable and path-addressable.
3. Keep PO-readable docs short enough for review but linked to the deeper
   agent docs when detail matters.
4. Add project-specific sections only after multi-project docs/reporting is
   implemented.
