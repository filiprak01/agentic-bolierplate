# GitHub Adapter

The GitHub adapter is the repository boundary used by workers when they need to
read repository metadata, create feature branches, open pull requests, and read
pull request state or check-run placeholders.

## Runtime Configuration

Configure the target repository through environment variables:

```text
GITHUB_TOKEN=<github-token>
# Optional alias used by GitHub CLI and some CI systems:
GH_TOKEN=<github-token>
GITHUB_REPOSITORY=<owner>/<repository>
GITHUB_DEFAULT_BRANCH=main
```

The current dogfooding repository uses:

```text
GITHUB_REPOSITORY=example-org/agentic-boilerplate
GITHUB_DEFAULT_BRANCH=main
```

These values are examples for this boilerplate project only. New projects must
provide their own repository and default branch through `.env` or the worker
environment.

When one project can involve multiple repositories, also configure the
repository lanes documented in `docs/multi-repo-jira-github-traceability.md`.
`GITHUB_REPOSITORY` remains the default repository for the current worker
operation, while `TARGET_IMPLEMENTATION_REPOSITORY`,
`BOILERPLATE_PROCESS_REPOSITORY`, `DOCUMENTATION_REPOSITORY`, and
`AUTOMATION_REPOSITORY` identify which repository owns each story or PR.

`GITHUB_TOKEN` is the preferred variable for the boilerplate. `GH_TOKEN` is also
accepted as a fallback so host sessions, Docker workers, and GitHub CLI-style
environments can share the same token without interactive `gh auth login`.

## Token-Based Git And CLI Auth

When SSH keys or GitHub device login are not available, configure the local
checkout to use HTTPS and a local credential helper:

```bash
agentic --env-file .env github configure-token-auth --repo-path . --remote origin
```

The command:

1. Reads `GITHUB_TOKEN` or `GH_TOKEN` from the configured env file.
2. Sets the selected Git remote to `https://github.com/<owner>/<repo>.git`.
3. Stores a local Git credential-helper command in `.git/config`.
4. Does not write the token value into `.git/config`.
5. Does not print the token value.
6. Uses a source-checkout helper when `src/agentic_boilerplate` exists, so the
   command works before the package is installed as `agentic`.

For GitHub CLI commands in a non-interactive shell, export the token from the
same secret source before calling `gh`:

```bash
export GH_TOKEN="$GITHUB_TOKEN"
gh repo view "$GITHUB_REPOSITORY"
```

Docker workers should receive `GITHUB_TOKEN` or `GH_TOKEN` through environment
configuration or a secret mount, then run the same `agentic github
configure-token-auth` command inside the mounted working copy before Git push or
pull request work.

When configuring a target project checkout from a source checkout where the
package is not installed globally, point the credential helper at the
boilerplate source:

```bash
PYTHONPATH=/path/to/agentic-bolierplate/src python3 -m agentic_boilerplate.cli \
  --env-file /path/to/agentic-bolierplate/.env \
  github configure-token-auth \
  --repo-path /path/to/target-project \
  --helper-source-root /path/to/agentic-bolierplate/src
```

## Adapter Selection

Use `github_rest_adapter_from_settings(settings)` for live GitHub work.

Use `MockGitHubRepositoryAdapter` for local tests, dry runs, and workflow
validation that must not call GitHub.

Both adapters implement the same repository contract:

1. Validate configured repository access.
2. Read repository metadata.
3. Read and create branches.
4. Create and read pull requests.
5. Read pull request check-run placeholders.

GitHub check failures after Developer handoff follow
`docs/ci-failure-recovery-playbook.md`. The recovery handoff should record the
failing check, corrective commit, validation runtime, and final GitHub check
state before the story returns to `DEV COMPLETED`.

## Startup Validation

Workers should validate GitHub access before accepting assignments that require
GitHub writes. Validation should confirm:

1. The configured repository exists and is accessible.
2. The configured default branch exists.
3. The configured token can read repository metadata.
4. Write-enabled workers can create branches and pull requests when their role
   requires it.

If validation fails, the worker must pause before starting work and record the
configuration issue in durable local state or the PO inbox.

When `*_JIRA_DEV_PANEL_EXPECTED=false` for a configured repository lane, setup
diagnostics should warn that GitHub for Jira may not show PRs automatically.
Workers must then add the explicit Jira PR link fallback comment during PR
handoff.

## Secret Handling

Workers must never print `GITHUB_TOKEN` in logs, Jira comments, errors, evidence
files, or PO inbox records.

Use `redacted_github_config(config)` for diagnostics. HTTP errors should expose
the GitHub response message only, not request headers or token values.
