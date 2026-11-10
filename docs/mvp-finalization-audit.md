# MVP Finalization Audit

Status: prepared for `AGENT-399`

This audit anchors the final MVP handoff package. It records what the current
repository supports, what can be run in Docker today, and what must be treated
as a documented limitation or follow-up before the boilerplate is used for a
new project.

## Current MVP Shape

The repository is a local-first backend boilerplate for agentic software
delivery. It provides domain contracts, file-backed durable stores, local
integration adapters, scheduler/release workflows, testing workflows, and
release E2E evidence models.

The MVP is strongest as a controlled backend/process framework. It does not yet
include a production UI. Product Owner interaction is handled through Jira,
local PO inbox artifacts, durable evidence files, and Confluence-ready report
publication workflows.

## Implemented Capability Areas

Implemented and covered by tests:

1. Product Owner inbox schema, file store, CLI, and local API boundary.
2. Context pack generation for approved Jira work.
3. Jira, GitHub, and Confluence adapter contracts with mockable live adapters.
4. Documentation governance and Confluence report publication planning.
5. Story complexity and model/reasoning routing.
6. Sprint and release scope planning.
7. Dependency eligibility, recursive co-scheduling, and scheduler assignment
   planning.
8. Agent registry and durable assignment store.
9. Codex job, result, pause/resume, failed request, and limit availability
   artifacts.
10. Host-side Codex runner boundary with fakeable executor.
11. Developer subtask, branch, validation, and pull request workflows.
12. Review record and diff-first pull request review workflow.
13. Tester manual test, bug retest, AgileTest mapping, and evidence workflows.
14. Regression visibility, regression manifests, and release notes regression
   scope planning.
15. Sprint closure, sprint performance tracking, retro publication, and
   release E2E scenario planning.

## Docker Readiness Finding

The repository includes:

1. A `Dockerfile` that builds the local Python package.
2. A `docker-compose.yml` with `api`, `worker`, role-specific worker,
   `postgres`, and `redis` services.
3. Durable repository, target-project, and `data` mounts for the API and
   worker services.
4. Health checks for PostgreSQL and Redis.
5. Tests that verify the Compose foundation.

AGENT-404 updates Docker from a generic worker shell to role-specific dry-run
worker services. The `api` container still runs a runtime shell, while worker
containers run `agentic worker run-once` for their configured roles.

This means Docker can run the MVP platform foundation and all MVP worker roles
in controlled dry-run mode with durable volumes. Live Jira, GitHub, Confluence,
AgileTest, and Codex execution remains delegated to approved host-side
workflow boundaries.

## Worker Role Readiness

Supported as domain/process workflows:

1. `product_planning`
2. `architecture`
3. `developer`
4. `review`
5. `tester`
6. `release_manager`
7. `scheduler`
8. `platform`

Configured by default in `WorkerSettings`:

1. `product_planning`
2. `architecture`
3. `developer`
4. `review`
5. `tester`
6. `release_manager`
7. `scheduler`
8. `platform`

The `release_manager`, `scheduler`, and `platform` roles are included in the
default `WORKER_ROLES` tuple and in Docker worker profiles.

## Configuration Finding

`.env.example` covers:

1. GitHub repository and token.
2. Jira project, board, email, and token.
3. Confluence space, parent page, email, and token.
4. Codex default model, reasoning, speed, high-reasoning flags, and pause
   behavior.
5. AgileTest client and token placeholders.
6. Durable local storage paths.
7. Sprint sizing guardrails.

AgileTest setup is documented for the handoff. Future code-level work may add
typed startup probes for AgileTest API access if a target project requires live
AgileTest validation before worker startup.

## Startup And Validation Finding

Startup validation exists in `agentic_boilerplate.runtime.startup`.

It checks:

1. Required GitHub, Jira, Confluence, Codex, and durable path configuration.
2. Supported worker roles.
3. Durable directory creation and writeability.
4. Optional GitHub, Jira, and Confluence probes.

AgileTest is not currently part of startup validation. Final handoff should
call this out as a limitation if AgileTest live access must be verified before
release execution in a future project.

## Release Evidence Baseline

Sprint 12 produced the release E2E and regression baseline for MVP handoff:

1. `data/agent-logs/AGENT-357/test-evidence-20260707T082516Z.md`
2. `data/agent-logs/AGENT-357/mvp-r1-e2e-scenario-map.md`
3. `data/agent-logs/AGENT-357/mvp-r1-e2e-execution.md`
4. `data/agent-logs/SPRINT-12/release-readiness-summary-20260707T082947Z.md`
5. `data/agent-logs/REGRESSION-S12/regression-evidence-20260707T083222Z.md`
6. `data/agent-logs/REGRESSION-S12/regression-manifest-20260707T083222Z.md`

These files are durable local evidence and should be referenced by the release
notes and final presentations.

## Handoff Deliverable Implications

The final package must be explicit that:

1. The MVP is ready as a backend/process framework for controlled local
   dogfooding.
2. Docker supports background infrastructure and role-specific dry-run worker
   services today.
3. Fully autonomous live execution inside containers is not claimed; Codex work
   still depends on the host-side runner boundary and Product Owner limits.
4. Product Owner control remains through Jira statuses, local evidence, PO
   inbox, and Confluence-ready reports.
5. New projects must provide their own Jira project/board, GitHub repository,
   Confluence space, credentials, durable paths, and role configuration.
