# GitHub Pages Site Scaffold

The Release 1.2 docs site scaffold is a Markdown-first static publication
layer. It is intentionally repo-native and dependency-light so local Docker,
session-mode workers, and GitHub Pages deployment can use the same source docs.

## Source And Output

| Purpose | Path |
| --- | --- |
| Source Markdown | `docs/` |
| PO overview | `docs/index.md` |
| Navigation contract | `docs/site-navigation.md` |
| AI index | `docs/ai-documentation-index.md` |
| Generated static site | `site/` |

`site/` is generated output and is ignored by Git. Deployment automation can
publish it to GitHub Pages, or rebuild it in CI before publishing.

## Local Validation

Validate the scaffold:

```bash
agentic docs-site validate --docs-root docs
```

Build a local static preview:

```bash
agentic docs-site build --docs-root docs --output-root site
```

The build command creates static HTML for the default navigation pages. It does
not mutate the source Markdown.

Publish curated release or sprint report summaries into the docs tree:

```bash
agentic docs-site publish-reports --input data/report-publication/<release>-<sprint>.json --docs-root docs
```

Report publication writes Markdown under `docs/reports/<release-id>/<sprint-id>/`
and retry records under `data/publication-retries/` when a required source
artifact is missing or requires redaction.

CI publication is documented in
[github-pages-documentation-workflow.md](github-pages-documentation-workflow.md).

## Publication Rules

1. Existing docs remain usable as AI context and are not converted into a
   human-only marketing site.
2. Navigation must include setup, PO inbox/operator UI, agent roles, workflows,
   release notes, and evidence/report sections.
3. Link validation checks the configured navigation and AI index paths where
   practical.
4. Future multi-project report sections should be added below a stable
   project-id namespace.
