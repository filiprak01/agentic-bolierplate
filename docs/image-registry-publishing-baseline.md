# Image Registry Publishing Baseline

Status: Release 1.2 baseline for `AGENT-663`.

This document defines the default container image names, tag rules, registry
variables, and safe publishing boundary for local Docker Compose and future
OCI-compatible registry publication.

## Scope

Release 1.2 defines the baseline. It does not push images automatically by
default. Local development remains build-only unless the Product Owner enables
publishing explicitly.

Supported registry targets are any OCI-compatible registry, including:

1. Local Docker image store.
2. GitHub Container Registry.
3. Docker Hub.
4. JFrog Artifactory Docker registries.
5. Private OCI-compatible registries.

## Image Families

Default local image references use the `agentic-boilerplate` namespace and
`local` tag:

| Component | Default image |
| --- | --- |
| Operator API | `agentic-boilerplate/operator-api:local` |
| Operator UI | `agentic-boilerplate/operator-ui:local` |
| Platform worker | `agentic-boilerplate/worker-platform:local` |
| Product Planning worker | `agentic-boilerplate/worker-product-planning:local` |
| Architecture worker | `agentic-boilerplate/worker-architecture:local` |
| Developer worker | `agentic-boilerplate/worker-developer:local` |
| Review worker | `agentic-boilerplate/worker-review:local` |
| Tester worker | `agentic-boilerplate/worker-tester:local` |
| Release Manager worker | `agentic-boilerplate/worker-release-manager:local` |
| Scheduler worker | `agentic-boilerplate/worker-scheduler:local` |
| Frontend worker | `agentic-boilerplate/worker-frontend:local` |
| UI/UX worker | `agentic-boilerplate/worker-ui-ux:local` |
| Security worker | `agentic-boilerplate/worker-security:local` |
| Docs/Confluence worker | `agentic-boilerplate/worker-docs-confluence:local` |
| DevOps Platform worker | `agentic-boilerplate/worker-devops-platform:local` |
| Data Persistence worker | `agentic-boilerplate/worker-data-persistence:local` |

## Tag Format

Use these tag classes:

1. `local` for local development and Docker Compose testing.
2. `1.2.0-rc.<n>` for release-candidate images.
3. `1.2.0` for accepted release images.
4. `1.2.1` and later patch tags for hotfix images.
5. Optional immutable build metadata may be added by CI as an additional tag,
   for example the short Git SHA.

Never rely on `latest` for release or regression evidence. `latest` may be used
only as a convenience alias in a private local registry when the immutable
version tag is also published.

## Environment Contract

Base registry settings:

```env
AGENTIC_IMAGE_REGISTRY_HOST=
AGENTIC_IMAGE_NAMESPACE=agentic-boilerplate
AGENTIC_IMAGE_TAG=local
AGENTIC_IMAGE_PUSH_ENABLED=false
AGENTIC_IMAGE_PUBLISH_DRY_RUN=true
AGENTIC_IMAGE_REGISTRY_USERNAME=
AGENTIC_IMAGE_REGISTRY_TOKEN=
AGENTIC_IMAGE_REGISTRY_CREDENTIAL_REF=
```

`AGENTIC_IMAGE_PUSH_ENABLED=false` means local build-only mode. Docker Compose
must work without registry credentials in this mode.

`AGENTIC_IMAGE_PUSH_ENABLED=true` requires:

1. A registry host.
2. A namespace.
3. A tag.
4. Either a secret-manager credential reference or username/token credentials.

Credential values must never be committed, printed in logs, copied to Jira,
published to Confluence, returned through the UI, or stored in evidence files.

Compose uses explicit image variables such as:

```env
AGENTIC_OPERATOR_API_IMAGE=agentic-boilerplate/operator-api:local
AGENTIC_OPERATOR_UI_IMAGE=agentic-boilerplate/operator-ui:local
AGENTIC_WORKER_DEVELOPER_IMAGE=agentic-boilerplate/worker-developer:local
```

CI or release tooling may override those values with registry-qualified names:

```text
ghcr.io/example-org/agentic-boilerplate/operator-api:1.2.0
artifactory.example.com/docker-local/agentic-boilerplate/operator-api:1.2.0
```

## Local Build Mode

Local validation:

```bash
docker compose config --quiet
docker compose --profile workers config --quiet
docker compose build api operator-ui worker-developer
```

The local build mode must not require registry credentials.

## Registry Publish Mode

Publish mode is opt-in and should run from CI/release automation after the
Release Manager selects the version tag.

Required checks before push:

1. Render compose config and verify image references.
2. Validate `AGENTIC_IMAGE_PUSH_ENABLED=true`.
3. Validate registry host, namespace, tag, and credential reference.
4. Build images locally.
5. Tag images with immutable release or release-candidate tags.
6. Push only the selected image families.
7. Record image references in release evidence.

## Story Dependencies

Stories that create or run Dockerized operator API/UI services, role workers,
or detached worker pilots must reference this baseline when choosing image
names, tags, registry variables, and publishing behavior.
