# MVP Release 1 Notes

Status: Product Owner review package for `AGENT-399`

Version: `1.0.0`

## Release Summary

MVP Release 1 delivers the backend/process foundation for a local-first
agentic software delivery boilerplate. It is designed for a Product Owner who
keeps final control over scope, process, acceptance, and release decisions
while agents help with planning, architecture, implementation, review, testing,
regression, and release preparation.

The MVP is ready for controlled local dogfooding and handoff review. It is not
an uncontrolled autonomous production agent fleet.

## Delivered Scope

Core platform:

1. Python package scaffold with local CLI and test suite.
2. Durable local storage conventions under `data/`.
3. Typed configuration loading and redacted validation.
4. Docker Compose foundation with API, role-specific dry-run workers,
   PostgreSQL, and Redis services.
5. Database migration foundation with Alembic.

Product Owner control:

1. PO inbox schema, store, CLI, and local API.
2. Jira workflow/status transition contracts.
3. Story-backed change policy and PR/Jira visibility rules.
4. Documentation governance for shared and role-specific knowledge.

Planning and architecture:

1. Backlog draft workflow.
2. Jira story creation workflow.
3. Architecture templates and ADR/NFR workflows.
4. Story complexity and model/reasoning routing.
5. Context pack generation for approved work.

Development and review:

1. Developer subtask planning and update workflow.
2. Branch and commit validation workflow.
3. Pull request creation workflow.
4. Diff-first review workflow and review record tracking.
5. GitHub adapter contract for branch, pull request, checks, and merge
   metadata.

Testing and regression:

1. Tester manual test workflow.
2. Tester bug/retest workflow.
3. AgileTest-style Test Case mapping.
4. Regression classification, suite planning, manifests, evidence, and
   board-visible regression overview tasks.
5. Release E2E scenario map, runner/checklist, AgileTest planning, execution
   overview, and readiness closure.

Release management:

1. Release scope selection.
2. Release notes regression scope.
3. Release branch/version and hotfix branch workflow models.
4. Sprint acceptance, dependency gates, sprint fit, sprint closure, and sprint
   performance tracking.
5. Confluence report publication workflow for approved report artifacts.

## Validation Summary

Latest release validation from Sprint 12:

1. Release E2E execution overview: `AGENT-357`
2. Release E2E Test Execution: `AGENT-396`
3. Sprint 12 regression overview: `AGENT-397`
4. Sprint 12 regression Test Execution: `AGENT-398`
5. Release E2E Test Cases: `AGENT-392`, `AGENT-393`, `AGENT-394`, `AGENT-395`

Recorded results:

1. Focused Sprint 12 regression: `75 passed`
2. Full backend suite: `498 passed`
3. Bugs created during Sprint 12 release E2E/regression: none
4. Waivers required: none

Durable evidence:

1. `data/agent-logs/AGENT-357/test-evidence-20260707T082516Z.md`
2. `data/agent-logs/SPRINT-12/release-readiness-summary-20260707T082947Z.md`
3. `data/agent-logs/REGRESSION-S12/regression-evidence-20260707T083222Z.md`
4. `data/agent-logs/REGRESSION-S12/regression-manifest-20260707T083222Z.md`

## Known Limitations

1. There is no production web UI in MVP Release 1.
2. Docker Compose runs platform foundation services and role-specific dry-run
   workers for every MVP role.
3. The host-side Codex runner boundary is implemented and fakeable, but live
   Codex execution still depends on the host-side Codex session/subscription
   and manual model/reasoning switching.
4. AgileTest fields are documented in `.env.example`, but live AgileTest API
   startup validation is not part of the current `validate_startup` checks.
5. Local files mirror Confluence-ready content. Approved report publication to
   Confluence should be executed when partner-facing reporting is needed.

## Release Risks

1. Live Codex-backed execution remains delegated to the host-side runner
   boundary; Docker workers validate startup, register, poll assignments, and
   write logs in dry-run mode.
2. If a future project requires live AgileTest API validation before startup,
   AgileTest should be added to typed settings and startup probes.
3. If Codex subscription limits are low, workers must pause through the durable
   pause/resume artifacts instead of continuing with incomplete state.

## Release Decision

Recommendation: ready for Product Owner handoff review as a backend/process
MVP, with Docker worker readiness supported for controlled role-specific
dry-run operation and live Codex execution still governed by host-side
subscription controls.
