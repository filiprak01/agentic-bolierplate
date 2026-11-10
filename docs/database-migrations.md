# Database Migrations

The database migration foundation uses Alembic for PostgreSQL schema changes.

The first Release 1.2 migration creates the detached worker checkpoint mirror
table. Runtime workers still use file-backed durable stores by default, but the
database schema exists so later scaling work can add a DB-backed store without
changing checkpoint semantics.

## Configuration

Database settings are loaded through the platform configuration layer:

```text
DATABASE_URL=postgresql://agentic:agentic@localhost:5432/agentic
DATABASE_MIGRATION_SCRIPT_LOCATION=migrations
```

When running inside Docker Compose, the API and worker services use:

```text
DATABASE_URL=postgresql://agentic:agentic@postgres:5432/agentic
```

Alembic reads `settings.database.url` in `migrations/env.py`.

## Local PostgreSQL

Start PostgreSQL from Compose:

```bash
docker compose up postgres
```

Start PostgreSQL and Redis together:

```bash
docker compose up postgres redis
```

Validate the Compose file first:

```bash
docker compose config --quiet
```

## Migration Commands

Show current migration state:

```bash
alembic current
```

Apply all migrations:

```bash
alembic upgrade head
```

Create a future migration revision:

```bash
alembic revision -m "describe change"
```

Create an auto-generated revision after SQLAlchemy metadata exists:

```bash
alembic revision --autogenerate -m "describe change"
```

Downgrade one revision:

```bash
alembic downgrade -1
```

## Current Schema Policy

Current state:

1. `migrations/versions/.gitkeep` remains as the directory marker.
2. `migrations/versions/20260809_0001_detached_worker_checkpoints.py` creates
   `detached_worker_checkpoints`.
3. `target_metadata = None` because SQLAlchemy models are not introduced yet.
4. Alembic may create its own version table when migrations are applied.

Future stories must define tables through explicit requirements and acceptance
criteria before adding more migration revisions.

## Detached Worker Checkpoint Table

`detached_worker_checkpoints` mirrors the file-backed checkpoint schema from
`docs/detached-worker-checkpoints.md`.

Required persisted fields include assignment id, worker id, role, project id,
sprint, Jira issue key, branch name, worktree path, stage, last command,
failed request path, resume action, resume recommendation, and timestamps.
Secret-like command and resume text must be redacted before either file or
database persistence.

## Validation Without External Services

The migration foundation can be validated without connecting to PostgreSQL:

```bash
PYTHONPATH=src python -m pytest tests/test_migration_foundation.py tests/test_config_settings.py
```

Full local regression:

```bash
PYTHONPATH=src python -m pytest
```

These tests verify dependency declaration, Alembic config, database URL loading,
the checkpoint migration fields, and the bootstrap revision template.
