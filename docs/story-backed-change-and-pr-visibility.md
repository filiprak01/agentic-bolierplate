# Story-Backed Change And PR Visibility

Status: implemented for `AGENT-138`

This policy keeps Jira, GitHub, review, and validation visibly connected for
every repository change that affects the boilerplate.

## Change Surfaces

`StoryBackedChangeSurface` distinguishes:

1. `product-behavior`
2. `code-change`
3. `configuration-change`
4. `documentation-only`
5. `process-documentation`

Product behavior, code, tests, scripts, and configuration changes require an
approved Jira story before implementation.

Documentation-only and process-documentation updates may be created
immediately, but still require:

1. A dedicated branch.
2. A pull request.
3. Review.
4. Validation evidence before the next sprint starts.

## Process Branch Naming

`build_process_change_branch_name` supports the agreed fallback patterns:

1. `process/{JIRA_KEY}-{slug}`
2. `docs/{sprint-name}-{slug}`

Examples:

1. `process/AGENT-138-retro-closure`
2. `docs/sprint-8-process-closure`

## PR Visibility

`DeveloperPullRequestPlan` now carries:

1. Sprint name.
2. Sprint publication task.
3. Related Jira story keys.
4. Change surface.
5. Boilerplate behavior impact flag.

The PR body renders that metadata so the Product Owner and Review Agent can see
scope, lineage, and validation context without leaving GitHub.

When Jira or GitHub smart links are unavailable, the workflow uses
`render_manual_jira_pr_visibility_fallback` to produce a durable Jira comment
with:

1. PR URL.
2. Branch.
3. Commits.
4. Validation evidence.
5. Review result.
6. Merge commit when available.

`plan_github_validation_fallback` is the decision helper for outage or
visibility checks. Callers provide the observed GitHub/Jira signals:

1. Whether GitHub validation was available.
2. Whether Jira shows a visible pull request link.
3. Whether a manual fallback comment is already present.

The helper requires branch, commit, PR URL, and validation evidence inputs. It
returns a Jira-ready fallback comment only when GitHub/Jira visibility is not
trustworthy and no manual fallback has already been recorded.

Multi-repository work extends this rule through
`docs/multi-repo-jira-github-traceability.md`. Stories must name the affected
repository lanes, and each lane needs a Jira-keyed branch, commits, PR title,
PR body, and manual Jira PR link when automatic development-panel visibility is
not expected.

Boilerplate/process repository PRs created because of target project work must
state the project story that caused the process change. Combined target and
process changes are allowed only when the story and PR body include visible
reasoning for the combined scope.

## Review Enforcement

The Review Agent continues to verify visible Jira PR linkage.

It now also records a finding when unrelated staged or pushed files are found
in the pull request scope. That supports the policy that retro, closure, and
story-backed changes must not silently carry unrelated repo edits.

Review queue triage for story-backed PRs is documented in
`docs/review-agent-queue-report.md`. The queue report highlights missing Jira
links, draft PRs, dependency blockers, incomplete subtasks, check failures,
missing evidence, merge conflicts, and process-repository handoffs before the
Review Agent starts diff-first review.

## Validation

Docs-only and process-documentation changes use lightweight validation:

1. Referenced markdown paths exist.
2. Updated markdown includes the required sprint, Jira, PR, retro, or closure
   references.

Code, configuration, and behavior changes still require targeted developer
validation and durable evidence before PR creation.
