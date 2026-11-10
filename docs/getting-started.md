# Getting Started

This guide explains how to run the MVP locally, validate the setup, and prepare
the boilerplate for a new project.

## Prerequisites

Install:

1. Python 3.11 or newer.
2. Git.
3. Docker Desktop or Docker Engine with Docker Compose.
4. Access to the target GitHub repository.
5. Jira Cloud project and Scrum board.
6. GitHub Pages-capable repository settings for default documentation
   publication.
7. Optional Confluence space for projects that explicitly enable Confluence
   fallback publication.
8. AgileTest configured in Jira when release regression management is needed.
9. A host Codex subscription/session for Codex-backed worker execution.

## Local Python Setup

From the repository root:

```bash
python -m pip install -e ".[dev]"
```

Run the local test suite:

```bash
PYTHONPATH=src python -m pytest
```

Run a smaller setup validation pack:

```bash
PYTHONPATH=src python -m pytest \
  tests/test_config_settings.py \
  tests/test_startup_validation.py \
  tests/test_docker_compose_foundation.py
```

## Environment Setup

Copy the template:

```bash
cp .env.example .env
```

Fill in values for:

1. GitHub repository and token.
2. Jira URL, project key, board id, email, and API token.
3. Documentation provider selection. Release 1.2 defaults to GitHub Pages with
   local Markdown in Git as source.
4. `DOCUMENTATION_PROVIDER`, `GITHUB_PAGES_BRANCH`, `GITHUB_PAGES_SOURCE_DIR`,
   optional `GITHUB_PAGES_DOCS_URL`, optional custom domain, and deployment
   mode for GitHub Pages publication.
5. Confluence URL, space key, parent page id, email, and API token only when
   Confluence fallback publication is enabled.
6. AgileTest client id and token when release/regression Test Execution sync is
   needed.
7. Codex defaults and limit behavior.
8. Durable data paths.
9. Worker roles.
10. Target project path for the project being built by the boilerplate.
11. Worker polling interval when running Docker workers in the background.
12. Infrastructure planning answers when the target project needs public
    deployment, paid services, managed data stores, backups, monitoring, or a
    growth path beyond local Docker.

Do not commit `.env`. It is ignored by Docker and Git.

## Target Project AGENTS.md

Before starting workers for a new target project, copy the starter template:

```bash
cp docs/templates/target-project-AGENTS.md "$TARGET_PROJECT_PATH/AGENTS.md"
```

Then replace the placeholders with the target project name, Jira key, board id,
GitHub repository, and platform durable root. The setup validator reports
`target_project.agents_template` so the operator can confirm the template is
available before preparing the target project.

## Codex Limit Gate Before Workers

Before workers start Codex-backed work, record the current Codex quota state.
Use Codex app `/status` or Codex CLI `/usage` to inspect visible usage/reset
information, then persist the observation:

```bash
agentic codex-limits record \
  --id availability-20260707T100000Z \
  --five-hour-status available \
  --five-hour-remaining 80 \
  --five-hour-reset-at 2026-07-07T15:00:00Z \
  --weekly-status available \
  --weekly-remaining 80 \
  --weekly-reset-at 2026-07-14T10:00:00Z
```

Check the latest gate before starting or resuming workers:

```bash
agentic codex-limits latest --json
```

For a readable operator view:

```bash
agentic codex-limits status
```

Enter the values manually from Codex status or usage screens. The MVP CLI does
not scrape or infer subscription limits automatically.

If the gate action is `wait`, `downgrade_model`, or `ask_product_owner`, do not
start a new story. Use the returned `resume_after` timestamp to schedule a Codex
app reminder/thread automation or external wake-up, then resume after the
Product Owner confirms limits are available.

## Docker Compose Setup

Validate Compose:

```bash
docker compose config --quiet
```

Build and start services:

```bash
docker compose up --build
```

Start all role-specific worker dry-run services:

```bash
docker compose --profile workers up --build
```

Run in the background:

```bash
docker compose up --build -d
```

Run all role-specific workers in the background:

```bash
docker compose --profile workers up --build -d
```

Stop services:

```bash
docker compose down
```

Stop and remove database/cache volumes:

```bash
docker compose down --volumes
```

## Durable Volumes

The Compose file mounts:

```text
./data:/workspace/data
```

This keeps these artifacts durable across container restarts:

1. PO inbox items.
2. Context packs.
3. Codex jobs and results.
4. Codex limit availability records.
5. Agent registry and assignment state.
6. Agent logs.
7. PO decisions.
8. Sprint data.
9. Optional Confluence mirrors.
10. GitHub Pages publication artifacts and generated report inputs.

## Startup Validation

Workers should validate startup readiness before accepting work:

```python
from agentic_boilerplate.config import load_settings
from agentic_boilerplate.runtime import require_startup_ready

settings = load_settings(".env")
require_startup_ready(settings)
```

This validates required configuration, supported worker roles, durable
directories, and optional integration probes.

Worker assignment execution also validates the role instruction bundle and
context-pack path described in `docs/worker-instruction-context-loading.md`.
Missing role docs or context packs pause the worker before it claims an
assignment.

## Infrastructure Planning Before Deployment

Use `docs/infrastructure-planning-template.md` when a generated project needs
anything beyond local Docker. The template helps Architecture and
DevOps/Platform agents capture expected scale, data sensitivity, availability,
budget, deployment target, and growth path.

The template is planning support only. It may create roadmap story candidates
for deployment preparation, managed database setup, object storage, backups,
monitoring, or future Kubernetes, but it does not create real cloud resources
or paid services without separate Product Owner-approved stories.

## Creating A New Project With The Boilerplate

Before choosing a branch, read `docs/release-track-policy.md`.

Use `release/1.0.0` only when testing or demonstrating the MVP snapshot.
Use `main` for Release `1.1.0` planning and implementation until a dedicated
Release `1.1` maintenance line exists. Do not copy Release `1.1.0` planning
documents or implementation work into `release/1.0.0` test branches.

For each target project:

1. Create a GitHub repository and set `GITHUB_REPOSITORY`.
2. Create or select a Jira Scrum project and set `JIRA_PROJECT_KEY` and
   `JIRA_BOARD_ID`.
3. Configure the Jira workflow statuses expected by the process.
4. Choose documentation publication. The default is GitHub Pages; set
   Confluence values only when the project requires Confluence fallback.
5. Enable AgileTest issue types and configure Test/Test execution behavior if
   regression tracking is required.
6. Set `TARGET_PROJECT_PATH` to the local checkout the workers should modify.
7. Prepare product vision, architecture, NFR, and release-scope docs using the
   target project layout in `docs/target-project-layout.md`.
8. Generate or draft backlog candidates.
9. Review Jira stories in `FUNNEL`.
10. Move approved stories to `READY TO START`.
11. Let scheduler/release-manager workflows select unblocked work.
12. Run development, review, testing, regression, and PO acceptance gates.

When validating Codex sessions for a new target project, use
`docs/session-mode-validation-playbook.md` after the role prompts in
`ai_agents/session_starters/README.md`. The playbook defines expected outputs,
stop conditions, and the feedback path from session findings into Docker
requirements or future backlog stories.

## Worker Runtime Boundary

Docker can run the platform foundation and role-specific worker services for
the configured Release 1.2 roles:

1. `product_planning`
2. `architecture`
3. `developer`
4. `review`
5. `tester`
6. `release_manager`
7. `scheduler`
8. `platform`
9. `frontend`
10. `ui_ux`
11. `security`
12. `docs_confluence`
13. `devops_platform`
14. `data_persistence`

Each worker runs:

```bash
agentic worker run-once --role <role>
```

The default Docker command is dry-run safe. It validates startup, registers the
worker, checks Codex limit availability records before queued work is accepted,
polls queued assignments for its role, and writes logs under
`data/agent-logs/<role>/`.
Docker wraps this command in a polling loop controlled by
`AGENTIC_WORKER_POLL_INTERVAL_SECONDS`.

Before workers accept assignments, startup validation requires
`TARGET_PROJECT_PATH` to point to an existing target project checkout. Leave
durable runtime data under the boilerplate `data` folder or configured durable
paths, and keep mutable target-project code in the configured target checkout.

Live Codex-backed execution is still delegated to the host-side Codex runner
boundary. This keeps Codex subscription control with the Product Owner and
prevents containers from making uncontrolled model calls.
