# Agentic Boilerplate

Local-first multi-agent software delivery platform.

The Product Owner controls scope, business decisions, and release acceptance.
Agents help plan, document, implement, review, test, and release work through
Jira, GitHub, durable local files, the operator PO inbox, Docker services, and
host-side Codex subscription execution.

## Current Status

Latest stable release: `1.2.0` on `release/1.2.0` and immutable tag
`v1.2.0`.

Package metadata version: `1.2.0`.

Release `1.2.0` adds Dockerized operator API/UI foundations, role-worker
Compose profiles, image naming/publishing baseline, multi-project inbox support,
model and quota routing, GitHub Pages documentation publication, host-side Codex
runner contracts, and bounded runtime proof gates.

Release `1.2.0` passed the bounded live runtime proof defined by `AGENT-967`:
two Docker-queued Codex stages completed through the host-side subscription
runner, and the `AGENT-1045` blocker was resolved. This proves the bounded
host-assisted path, not fully autonomous container-only Codex execution or the
complete multi-role delivery chain.

Release track selection is documented in `docs/release-track-policy.md`.

Use `release/1.2.0` or `v1.2.0` for stable Release 1.2 validation. Older
release branches and tags remain available for compatibility testing.

## What Is Available To The Product Owner

1. Jira-first delivery process with `FUNNEL`, `READY TO START`, development,
   review, testing, regression, retro, and release closure gates.
2. Role instruction files for Product Planning, Architecture, Developer,
   Review, Tester, Release Manager, Frontend, UI/UX, Security, Docs,
   DevOps/Platform, Data/Persistence, Scheduler, and Orchestrator work.
3. Copy/paste Codex session starters in `ai_agents/session_starters/`.
4. PO inbox CLI, local API, and Dockerized operator UI for questions,
   approvals, decisions, and project-scoped inbox export.
5. Durable local storage for PO inbox, context packs, Codex jobs/results,
   Codex limit observations, agent state, logs, sprint records, and publication
   mirrors.
6. Docker Compose operator stack with API and UI containers.
7. Docker Compose role-worker profiles that register, poll, check durable state,
   and run dry-run/scheduler-supported loops.
8. Host-side Codex runner boundary for subscription-backed execution without
   copying Codex credentials into generic worker containers.
9. GitHub PR/review/merge workflow, CI quality gate, and Jira-visible PR link
   fallback rules.
10. AgileTest/Jira evidence workflows and regression manifest/closure policies.
11. GitHub Pages as the default documentation publication target, with
   Confluence optional per project.
12. Startup diagnostics for connectors, paths, Python runtime, durable roots,
   worker state, and service health.

## Not Yet A Proven Capability

Do not present these as complete until the matching release gate passes:

1. Fully autonomous container-only Codex execution.
2. A proven end-to-end detached chain from Planning/Architecture through
   Developer, Review, Tester, and Release Manager.
3. Automatic Product Owner acceptance without release-level PO review.
4. Automatic model switching in an active Codex UI session.
5. Credential repair, token rotation, branch-protection changes, or Jira
   workflow changes without explicit operator/PO action.

## Switch To A Release Track

Fetch current branches and tags:

```bash
git fetch --all --tags
```

Use the latest development track:

```bash
git switch main
git pull --ff-only
```

Use the stable Release 1.2 branch:

```bash
git switch release/1.2.0
git pull --ff-only
```

or inspect an immutable tag:

```bash
git switch --detach v1.2.0
```

Do not test a target project on `main` when you need an immutable release
snapshot. Use `v1.2.0`, or use `release/1.2.0` when you need the maintained
release line.

## Local Development

Required Python:

```text
Python 3.11+
```

Install development dependencies:

```bash
python -m pip install -e ".[dev]"
```

Run tests:

```bash
python -m pytest
```

The test suite is local-only by default. It must not require live GitHub, Jira,
Confluence, Codex, PostgreSQL, or Redis access for foundation validation.

When running from source without installing the package first:

```bash
PYTHONPATH=src python -m agentic_boilerplate.cli --help
PYTHONPATH=src python -m agentic_boilerplate.cli setup validate --project-root . --codex-limits-root data/codex-limits
```

If `python` is missing on WSL, use `python3` only when it is Python 3.11+ or
install/configure the required Python version. Do not treat a Python PATH
failure as a Jira, GitHub, or Codex limit failure.

## Docker Operator Stack

Create `.env` from the example and fill project-specific values:

```bash
cp .env.example .env
```

Minimum values for a normal local target project:

```text
GITHUB_REPOSITORY=<owner>/<repo>
GITHUB_AUTH_MODE=https
GIT_REMOTE_MODE=https
JIRA_BASE_URL=https://<site>.atlassian.net
JIRA_EMAIL=<jira-account-email>
JIRA_API_TOKEN=<jira-api-token>
JIRA_PROJECT_KEY=<project-key>
JIRA_BOARD_ID=<board-id>
TARGET_PROJECT_PATH=<absolute-path-to-target-project>
VITE_AGENTIC_API_BASE_URL=http://localhost:8000
DURABLE_PO_INBOX_PATH=data/po-inbox
DURABLE_CODEX_LIMITS_PATH=data/codex-limits
AGENTIC_WORKSPACES_ROOT=data/agent-workspaces
```

Start the Product Owner operator inbox and runtime API:

```bash
docker compose --profile operator up --build -d
```

Open:

```text
http://localhost:5173
```

Start all role-worker loops:

```bash
docker compose --profile workers up --build -d
```

Start one role only:

```bash
docker compose --profile developer up --build -d
```

Stop without deleting durable data:

```bash
docker compose down
```

## Codex Subscription Boundary

The intended runtime uses the Product Owner's logged-in ChatGPT/Codex
subscription on the host machine, not an OpenAI API key inside generic workers.

Host setup:

```bash
codex login
codex login status
codex app-server
```

The host-side limit sentinel reads Codex App Server `account/rateLimits/read`
and writes durable availability records under `data/codex-limits`. Worker
containers consume those records. They must not receive Codex login folders,
browser profiles, cookies, or copied subscription credentials.

Use `CODEX_ACCESS_TOKEN` only for trusted host-side automation if a future story
explicitly enables it. Leave it blank for generic Docker workers.

## Windows WSL Path Check

If Codex is opened through `\\wsl.localhost\Ubuntu\...` and shell execution,
Python, PO inbox, or limit checks fail, use the operator workaround documented
in `docs/windows-wsl-codex-runtime-troubleshooting.md`:

1. Leave the real repository in place.
2. Create a Windows directory alias/junction to the repository.
3. Open Codex through the alias path.
4. Verify `git rev-parse --show-toplevel` resolves to the canonical checkout.
5. Verify Python and durable `data/po-inbox` / `data/codex-limits` roots from
   the same path.

This is a setup fix, not proof that runtime execution passed.

## Durable Local Data

The platform stores recoverable runtime artifacts in configurable durable
directories. Defaults:

1. `data/po-inbox`
2. `data/context-packs`
3. `data/codex-jobs`
4. `data/codex-results`
5. `data/codex-limits`
6. `data/agent-state`
7. `data/agent-logs`
8. `data/po-decisions`
9. `data/sprints`
10. `data/confluence-mirror`

Docker mounts `./data` into `/workspace/data`. Make sure host commands, the API,
UI, and worker containers all point to the same durable roots.

## Processing Flow

1. Product Owner moves work from `FUNNEL` to `READY TO START`.
2. Orchestrator/Scheduler checks sprint scope, role labels, dependencies,
   design gates, bug gates, model route, and durable limit availability.
3. Developer/Frontend/role worker creates a Jira-keyed feature branch, performs
   one subtask/stage at a time, commits evidence, and opens a PR.
4. Review Agent performs diff-first review, checks CI, reports conflicts to the
   owning developer, and merges only clean PRs.
5. Tester Agent tests after merge to `main`, creates evidence, and either moves
   the story to `TEST COMPLETED` or creates/links a bug and returns the story to
   `DEV COMPLETED`.
6. Release Manager runs regression, retro, publication, branch/tag planning,
   and closure gates.
7. Product Owner performs release-level acceptance.

## Core Documentation

Start here: [Release 1.2 local multi-agent startup guide](docs/presentations/release-1.2.0-local-agent-start-guide.html).

1. Docker Compose: `docs/docker-compose-foundation.md`
2. Operator guide: `docs/release-1.2-operator-guide.md`
3. Release closure: `docs/release-1.2-closure-package.md`
4. PO inbox API: `docs/po-inbox-api.md`
5. PO inbox CLI: `docs/po-inbox-cli.md`
6. Codex subscription: `docs/codex-subscription-setup.md`
7. Host-side runner: `docs/host-side-codex-runner.md`
8. Startup diagnostics: `docs/worker-startup-diagnostics.md`
9. Windows/WSL troubleshooting: `docs/windows-wsl-codex-runtime-troubleshooting.md`
10. Release track policy: `docs/release-track-policy.md`
11. Jira workflow and links: `docs/jira-workflow-links.md`
12. GitHub adapter: `docs/github-adapter.md`
13. Documentation governance: `docs/documentation-governance.md`

## Development Policy

Use Jira project `AGENT` for boilerplate dogfooding.

Stories start in `FUNNEL`.

Implementation starts only when Product Owner moves work to `READY TO START`.

Feature branches:

```text
feature/{JIRA_KEY}-{short-slug}
```

Pull requests merge to `main` after quality checks and Review Agent approval.

Tester Agent tests after merge to `main`.

## Agent Instructions

Codex-compatible instructions live in `AGENTS.md`, reusable skills live under
`.agents/skills/`, and role definitions live under `ai_agents/roles/`.
`CLAUDE.md` provides the matching Claude entry point so either tool can load the
same repository-owned process and documentation.

## License

Licensed under the Apache License 2.0. See [LICENSE](LICENSE).
