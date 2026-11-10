# GitHub Pages Documentation Workflow

Release 1.2 publishes approved documentation and release reports through
GitHub Pages by default.

## CI Behavior

The workflow `.github/workflows/docs-pages.yml` has two stages:

1. `validate` runs on pull requests, pushes to `main`, pushes to `release/**`,
   version tags, and manual dispatch. It runs:
   `agentic docs-site validate --docs-root docs` and
   `agentic docs-site build --docs-root docs --output-root site`.
2. `deploy` runs only after validation and only when publication is explicitly
   enabled.

Pull requests never deploy. They only validate docs and upload the dry-run site
artifact for review.

## Approved Publication Refs

Deployment is allowed only from:

1. `main`
2. `release/**`
3. `v*` release tags
4. Manual dispatch when the same branch/tag policy is satisfied

Feature branches must not publish to the production GitHub Pages site.

## Dry-Run Default

Publication is disabled by default. Enable it by setting repository variable:

```text
AGENTIC_DOCS_PUBLISH_ENABLED=true
```

Manual dispatch can set `publish=true` for an operator-triggered deployment
after repository Pages settings are configured.

## Product Owner Repository Settings

The Product Owner or repository administrator must configure:

1. GitHub Pages enabled for the repository.
2. Source set to GitHub Actions.
3. Actions allowed to read repository contents and write Pages artifacts.
4. Optional custom domain and DNS configuration.
5. Repository variable `AGENTIC_DOCS_PUBLISH_ENABLED=true` only after dry-run
   validation is accepted.

## Release Manager Publication Rules

Release Manager publishes these after merge and validation:

1. Release notes.
2. Sprint closure notes.
3. Regression summaries and manifests.
4. Retro summaries approved for publication.
5. Partner reports after redaction and Product Owner approval.

Published Jira comments should include the GitHub Pages URL when available. If
GitHub Pages is still disabled, comments must include the dry-run artifact or
local evidence path instead.

## Redaction Rules

The published site must not include:

1. `.env` values.
2. GitHub, Jira, AgileTest, Confluence, Figma, Codex, or registry tokens.
3. Raw failed requests or internal-only debugging logs.
4. Role scratch notes.
5. Customer or partner data not approved by the Product Owner.
