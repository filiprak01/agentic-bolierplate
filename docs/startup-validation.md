# Startup Validation

Status: implemented for `AGENT-10`

Startup validation protects local workers from starting when configuration is
missing or durable state cannot be persisted.

## Required Checks

The runtime startup validator checks:

1. Required configuration values.
2. Configured worker roles.
3. Documentation provider selection.
4. Durable directory creation.
5. Durable directory write/read/delete behavior.
6. Optional integration access probes.

Release 1.2 defaults `DOCUMENTATION_PROVIDER` to `github_pages`. Missing
Confluence values must not block startup when GitHub Pages or offline local docs
are selected. Confluence settings are required only when the selected provider
is `confluence` or `both`.

## Worker Roles

Worker roles are configured with `WORKER_ROLES`.

Example:

```env
WORKER_ROLES=product_planning,architecture,developer,review,tester
```

Supported roles:

1. `product_planning`
2. `architecture`
3. `developer`
4. `review`
5. `tester`
6. `release_manager`
7. `scheduler`
8. `platform`

Unsupported worker roles fail startup validation.

## Durable Persistence

Startup validation initializes the configured durable directories and writes a
temporary probe file into each directory. Workers must not start if any durable
directory cannot be created, written, read, or cleaned up.

## Optional Integration Checks

The validator can run optional probes for:

1. GitHub.
2. Jira.
3. Confluence.

The MVP validator accepts probe callables so future adapter implementations can
provide live access checks without coupling startup validation to network
clients.

If integration checks are enabled but a probe is not supplied, the checklist
records that the check was skipped. This keeps local-only tests deterministic.

## Example

```python
from agentic_boilerplate.config import load_settings
from agentic_boilerplate.runtime import require_startup_ready

settings = load_settings(".env")
require_startup_ready(settings)
```

With adapter probes:

```python
require_startup_ready(
    settings,
    check_integrations=True,
    integration_probes={
        "github": github_adapter.check_access,
        "jira": jira_adapter.check_access,
        "confluence": confluence_adapter.check_access,
    },
)
```

## Checklist Output

Validation output is checklist-style and redacted. Token values, API tokens, and
other secret values must not appear in startup messages.

Startup and setup validation may show missing field names such as
`jira.api_token`, configured-state booleans, and remediation steps. It must not
show configured secret values, authorization headers, raw `.env` contents, or
free-text errors containing secret-like values.
