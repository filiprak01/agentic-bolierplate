# Docker Compose Foundation

The Docker Compose foundation provides a local runtime skeleton for the MVP.

It defines:

1. `api`
2. `operator-ui`
3. `worker`
4. Role-specific worker services under Docker Compose profiles.
5. `postgres`
6. `redis`

Release 1.2 image names, registry variables, tag rules, and build-only versus
publish mode are defined in
`docs/image-registry-publishing-baseline.md`.

The API service is intentionally lightweight and serves the local operator API
until the Product Owner stops the stack. Worker services load `.env`, mount the
repository, target project, and durable data folder, then run a dry-run worker
loop. They do not call GitHub, Jira, Confluence, AgileTest, or Codex at
container startup.

## Start Infrastructure

Validate the Compose file:

```bash
docker compose config --quiet
```

Validate all worker profiles:

```bash
docker compose --profile workers config --quiet
```

Start base services:

```bash
docker compose up --build
```

Start the Product Owner operator inbox:

```bash
docker compose --profile operator up --build -d
```

Open the UI:

```text
http://localhost:5173
```

Start all role workers:

```bash
docker compose --profile workers up --build -d
```

Start one role worker:

```bash
docker compose --profile developer up --build -d
```

Start only PostgreSQL and Redis:

```bash
docker compose up postgres redis
```

Stop services:

```bash
docker compose down
```

Stop services and remove named database/cache volumes:

```bash
docker compose down --volumes
```

## Windows WSL Path Setup

When running from Windows with the repository stored in WSL, prefer opening
Codex through the Product Owner validated Windows directory alias/junction path
when direct UNC workspace execution fails. See
`docs/windows-wsl-codex-runtime-troubleshooting.md`.

Before starting Compose or a live proof, verify from the same path:

```bash
git rev-parse --show-toplevel
git remote -v
python --version
PYTHONPATH=src python -m agentic_boilerplate.cli setup validate --project-root . --codex-limits-root data/codex-limits
```

The Docker stack, host-side commands, and Codex session must resolve the same
`./data` durable root. If the API reads `/workspace/data/po-inbox` while the
session writes a different `data/po-inbox`, the UI may show `Failed to fetch` or
empty inbox state even though the worker created messages elsewhere. If the
session reads a different `data/codex-limits`, the quota guard may falsely look
missing or unavailable.

## API And Worker Services

Agentic services:

1. Build from `Dockerfile`.
2. Load environment values from `.env`.
3. Mount the repository at `/workspace`.
4. Mount durable local data at `/workspace/data`.
5. Mount the configured target project at `/workspace/project`.
6. Depend on healthy PostgreSQL and Redis services.
7. Set `DATABASE_URL` and `REDIS_URL` for future runtime work.
8. Keep the `api` and `operator-ui` containers running with
   `restart: unless-stopped` until the stack is stopped manually.
9. Render deterministic local image references through `AGENTIC_*_IMAGE`
   variables so future registry publishing can reuse the same image families.
10. Expose health checks for API and UI readiness.

Role-specific worker profiles cover `product-planning`, `architecture`,
`developer`, `review`, `tester`, `release-manager`, `scheduler`, `platform`,
`frontend`, `ui-ux`, `security`, `docs-confluence`, `devops-platform`, and
`data-persistence`.

API command:

```text
agentic --inbox-root /workspace/data/po-inbox api serve --data-root /workspace/data --host 0.0.0.0 --port 8000
```

Worker command:

```text
agentic worker run-once --role <role>
```

This validates startup, registers worker state, checks durable Codex limit
availability records when present, polls assignments for the worker role, and
writes logs without making external integration calls in dry-run mode. Docker
wraps this command in a polling loop controlled by
`AGENTIC_WORKER_POLL_INTERVAL_SECONDS`.

Startup validation fails before assignment pickup when `TARGET_PROJECT_PATH` is
missing or does not resolve to an existing target project checkout.

## PostgreSQL

PostgreSQL uses:

1. Image: `postgres:16-alpine`
2. Named volume: `postgres-data`
3. Default database: `agentic`
4. Default user: `agentic`
5. Default password: `agentic`

Override defaults through `.env`:

```text
POSTGRES_DB=agentic
POSTGRES_USER=agentic
POSTGRES_PASSWORD=agentic
```

## Redis

Redis uses:

1. Image: `redis:7-alpine`
2. Named volume: `redis-data`
3. Append-only persistence enabled.

## Durable Local Data

The Compose services mount:

```text
./data:/workspace/data
```

This keeps Product Owner inbox items, context packs, Codex jobs, Codex results,
Codex limit availability records, agent registry/assignment state, agent logs,
PO decisions, sprint data, and Confluence mirrors durable across container
restarts.

## Current Limitations

This foundation does not yet:

1. Run live Codex execution inside containers.
2. Run database migrations.
3. Probe GitHub/Jira/Confluence/AgileTest/Codex during startup by default.
4. Prove live unattended host-side Codex execution without the AGENT-967 proof
   package passing.

Those behaviors should be introduced or closed by later stories once the
Product Owner approves live execution and startup probes.

## Validation

Local validation should include:

1. `docker compose config --quiet`
2. `docker compose --profile workers config --quiet`
3. `docker compose --profile operator config --quiet`
4. `docker compose --profile operator build api operator-ui`
5. `PYTHONPATH=src python -m pytest tests/test_docker_compose_foundation.py`
6. Full local test suite.

Registry baseline validation should also include:

1. Verify `AGENTIC_OPERATOR_API_IMAGE`, `AGENTIC_OPERATOR_UI_IMAGE`, and worker
   image variables render in `docker compose config`.
2. Verify local build mode works with `AGENTIC_IMAGE_PUSH_ENABLED=false`.
3. Verify publish mode is rejected when registry host or credentials are
   missing.
