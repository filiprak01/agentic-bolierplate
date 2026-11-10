# GitHub Pages Documentation Strategy

Release 1.2 makes local Markdown in Git the editable documentation source of truth
and GitHub Pages the default published documentation and report view.
Confluence remains an optional secondary publication target for projects that
explicitly enable it.

## Source Model

Documentation has three distinct surfaces:

1. `source` - approved Markdown committed to the configured repository.
2. `published` - GitHub Pages site generated from approved Markdown.
3. `fallback` - optional Confluence publication when a project explicitly
   enables Confluence or a partner requires it.

Agents must not treat Confluence as required when the documentation provider is
`github_pages`. Local Markdown remains the durable worker context input, while
GitHub Pages provides the Product Owner and partner-readable presentation layer.

## Publication Classes

Every published document or report must be classified before publication:

1. `ai_first_internal` - machine-oriented process, role, architecture, and
   context-pack documentation. Published by default to the internal GitHub
   Pages docs section when the repository access model is private.
2. `po_readable` - Product Owner handbooks, release overviews, setup guides,
   inbox usage guides, and roadmap summaries. Published by default.
3. `partner_report` - sprint/regression summaries, release readiness reports,
   quality summaries, and agreed delivery evidence. Published only after
   redaction and Product Owner approval rules pass.
4. `internal_only` - raw logs, role notes, failed requests, credentials,
   debugging transcripts, and noisy command output. Never published unless the
   Product Owner explicitly approves a redacted summary.

## Repo Slimming Boundary

GitHub Pages is the default publication surface, not a reason to commit every
durable worker artifact. Agents must classify documentation-like files with the
repo slimming policy before adding them to Git:

1. Keep approved shared source, release notes, curated reports, and published
   indexes in the repository.
2. Keep generated site output out of the repository unless the project has an
   explicit static-output publishing requirement.
3. Keep raw logs, role-specific notes, temporary planning scratchpads, and
   unapproved context packs in durable local storage.
4. Archive to Confluence only when the project enables the optional provider and
   the content is approved for that audience.

## Story And PR Requirement

Documentation changes require a Jira story or task and a pull request when they:

1. Change shared process, architecture, security, deployment, or agent behavior.
2. Change publication rules or report visibility.
3. Add or change user-facing setup, Product Owner workflow, or partner-facing
   material.
4. Alter source paths, generated site structure, or publication provider
   configuration.

Docs-only release notes may be created without a new implementation story only
when they summarize already approved and merged work without changing process
or behavior.

## Confluence Fallback

Confluence publication is preserved as an adapter-backed fallback, not removed.
Projects may enable it when they need an Atlassian-native knowledge base,
partner access, or existing Confluence governance.

When Confluence is disabled:

1. Setup validation must not block default project readiness because
   Confluence credentials are missing.
2. Docs workers must route publication to GitHub Pages.
3. Confluence mirror paths are not required for normal release/report
   publication.

When Confluence is enabled:

1. The adapter must still validate space, parent page, token, and mirror path.
2. Published content must preserve Jira, GitHub PR, AgileTest, and local
   evidence references.
3. The Product Owner decides whether Confluence is a secondary copy or the
   partner-visible surface for that project.

## Follow-Up Implementation Scope

The strategy requires these follow-up implementation stories:

1. Documentation provider configuration and setup validation.
2. GitHub Pages docs site scaffold with AI documentation index.
3. GitHub Pages deployment workflow and release publication policy.
4. Report publication workflow for test evidence, regression, retro, closure,
   and partner summaries.

This strategy must be Product Owner-reviewable before those implementation
stories start.
