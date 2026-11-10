# AI Documentation Index

This index helps agents load the right context without reading every file in
the repository.

## Core Startup Context

Every agent starts with:

1. `AGENTS.md`
2. Matching role file under `ai_agents/roles/`
3. Matching session starter under `ai_agents/session_starters/`
4. Project-specific context pack when one is assigned

## Role Map

| Role | Required Docs |
| --- | --- |
| Orchestrator | [scheduler-approved-scope-assignment.md](scheduler-approved-scope-assignment.md), [dependency-eligibility-checker.md](dependency-eligibility-checker.md), [orchestration-event-queue.md](orchestration-event-queue.md) |
| Product Planning | [backlog-draft-workflow.md](backlog-draft-workflow.md), [jira-story-creation-workflow.md](jira-story-creation-workflow.md), [context-pack-generator.md](context-pack-generator.md) |
| Architecture | [architecture-templates.md](architecture-templates.md), [nfr-workflow.md](nfr-workflow.md), [documentation-governance.md](documentation-governance.md), [infrastructure-planning-template.md](infrastructure-planning-template.md) |
| Developer | [developer-subtask-workflow.md](developer-subtask-workflow.md), [developer-branch-commit-validation-workflow.md](developer-branch-commit-validation-workflow.md), [developer-pull-request-creation-workflow.md](developer-pull-request-creation-workflow.md) |
| Review | [review-agent-pr-workflow.md](review-agent-pr-workflow.md), [review-records.md](review-records.md), [review-agent-queue-report.md](review-agent-queue-report.md) |
| Tester | [tester-manual-test-workflow.md](tester-manual-test-workflow.md), [tester-bug-retest-workflow.md](tester-bug-retest-workflow.md), [test-evidence-artifact-workflow.md](test-evidence-artifact-workflow.md) |
| Release Manager | [release-manager-scope-selection.md](release-manager-scope-selection.md), [regression-manifest-builder.md](regression-manifest-builder.md), [sprint-closure-publication-workflow.md](sprint-closure-publication-workflow.md) |
| Docs Publication | [github-pages-documentation-strategy.md](github-pages-documentation-strategy.md), [github-pages-site-scaffold.md](github-pages-site-scaffold.md), [shared-evidence-publication-policy.md](shared-evidence-publication-policy.md) |
| DevOps/Platform | [docker-worker-readiness.md](docker-worker-readiness.md), [host-side-codex-runner.md](host-side-codex-runner.md), [infrastructure-planning-template.md](infrastructure-planning-template.md) |
| Release 1.2 Closure | [release-1.2-operator-guide.md](release-1.2-operator-guide.md), [release-1.2-migration-guide.md](release-1.2-migration-guide.md), [release-1.2-closure-package.md](release-1.2-closure-package.md), [release-notes/release-1.2.0.md](release-notes/release-1.2.0.md) |

## Workflow Map

1. Planning and backlog creation:
   [backlog-draft-workflow.md](backlog-draft-workflow.md) ->
   [context-pack-generator.md](context-pack-generator.md) ->
   [jira-story-creation-workflow.md](jira-story-creation-workflow.md)
2. Delivery:
   [story-processing-path-matrix.md](story-processing-path-matrix.md) ->
   [stacked-pr-sprint-path-resolver.md](stacked-pr-sprint-path-resolver.md) ->
   [developer-subtask-workflow.md](developer-subtask-workflow.md) ->
   [review-agent-pr-workflow.md](review-agent-pr-workflow.md) ->
   [tester-manual-test-workflow.md](tester-manual-test-workflow.md)
3. Publication:
   [github-pages-documentation-strategy.md](github-pages-documentation-strategy.md) ->
   [github-pages-site-scaffold.md](github-pages-site-scaffold.md) ->
   [shared-evidence-publication-policy.md](shared-evidence-publication-policy.md)

## Reading Rule

Load only the docs required for the current role, story, and context pack.
When a missing business or architecture decision can change behavior, create a
PO inbox item and stop instead of guessing.
