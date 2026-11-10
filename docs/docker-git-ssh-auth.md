# Docker Git SSH Authentication

Release 1.2 supports SSH authentication for Docker worker Git operations while
keeping Codex session-mode work on HTTPS by default.

## Modes

Use HTTPS for supervised Codex sessions:

```text
GITHUB_AUTH_MODE=https
GIT_REMOTE_MODE=https
```

Use SSH for Docker workers that need to clone, push, or update PR branches:

```text
GITHUB_AUTH_MODE=ssh
GIT_REMOTE_MODE=ssh
GITHUB_REPOSITORY=example-org/example-project
GITHUB_DEFAULT_BRANCH=main
```

## SSH Key Sources

At least one SSH key source is required when `GITHUB_AUTH_MODE=ssh`.

Preferred mounted file source:

```text
GITHUB_SSH_KEY_PATH=/run/secrets/github_ssh_key
```

Fallback environment value sources:

```text
GITHUB_SSH_PRIVATE_KEY=
GITHUB_SSH_PRIVATE_KEY_B64=
```

If multiple sources are configured, the worker uses this deterministic order:

1. `GITHUB_SSH_KEY_PATH`
2. `GITHUB_SSH_PRIVATE_KEY_B64`
3. `GITHUB_SSH_PRIVATE_KEY`

Mounted key files are used in place. Environment-provided key values are
materialized into an ephemeral SSH directory with `0600` permissions.

## Compose Override

Use the SSH override only when a host key file is available:

```bash
GITHUB_AUTH_MODE=ssh GIT_REMOTE_MODE=ssh \
HOST_GITHUB_SSH_KEY_PATH=/absolute/host/path/to/deploy_key \
docker compose -f docker-compose.yml -f docker-compose.ssh.example.yml --profile workers up
```

The override mounts the key read-only at `/run/secrets/github_ssh_key`.

## Diagnostics

Plan the checks without touching the network:

```bash
agentic github ssh-auth-diagnostic --json
```

Run live safe probes:

```bash
agentic github ssh-auth-diagnostic --execute --repo-path .
```

The live diagnostic performs:

1. `git ls-remote` to verify repository read access.
2. `git push --dry-run` to verify branch create/update permission without
   changing the remote repository.

## Security Notes

Use a least-privilege deploy key or bot key. Rotate keys when a worker host is
replaced, a teammate leaves, or logs suggest a credential boundary issue.

Do not store SSH keys in Git, Jira, Confluence, browser bundles, test evidence,
or worker logs. Diagnostics and worker output report only configured field
presence, selected source name, remote URL, and redacted command metadata.

Keep strict host-key checking enabled by default. If a project needs custom
known-hosts data, set:

```text
GITHUB_SSH_KNOWN_HOSTS_PATH=/run/secrets/github_known_hosts
GITHUB_SSH_STRICT_HOST_KEY_CHECKING=true
```

