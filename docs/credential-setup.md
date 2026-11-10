# Credential And Token Setup

This guide explains what credentials are needed and where they belong.

Never commit real secrets. Store them in `.env`, local secret storage, or the
deployment secret manager used by the target environment.

## GitHub

Variables:

```text
GITHUB_TOKEN=
GH_TOKEN=
GITHUB_REPOSITORY=<owner>/<repo>
GITHUB_DEFAULT_BRANCH=main
GITHUB_AUTH_MODE=https
GIT_REMOTE_MODE=https
```

`GITHUB_TOKEN` is preferred. `GH_TOKEN` is accepted as a compatibility alias for
GitHub CLI and CI-style environments.

The token should allow the worker account to:

1. Read repository metadata.
2. Create branches.
3. Open pull requests.
4. Read pull request checks.
5. Merge pull requests when the Review Agent is trusted to merge.

For a new project, replace the dogfooding repository with the target project
repository.

For projects that touch multiple repositories, also configure repository lanes:

```text
TARGET_IMPLEMENTATION_REPOSITORY=<owner>/<repo>
TARGET_IMPLEMENTATION_DEFAULT_BRANCH=main
TARGET_IMPLEMENTATION_JIRA_DEV_PANEL_EXPECTED=true
BOILERPLATE_PROCESS_REPOSITORY=<owner>/<repo>
BOILERPLATE_PROCESS_DEFAULT_BRANCH=main
BOILERPLATE_PROCESS_JIRA_DEV_PANEL_EXPECTED=true
DOCUMENTATION_REPOSITORY=
DOCUMENTATION_DEFAULT_BRANCH=main
DOCUMENTATION_JIRA_DEV_PANEL_EXPECTED=false
AUTOMATION_REPOSITORY=
AUTOMATION_DEFAULT_BRANCH=main
AUTOMATION_JIRA_DEV_PANEL_EXPECTED=false
```

Use `*_JIRA_DEV_PANEL_EXPECTED=false` when GitHub for Jira is not expected to
show PRs automatically for that repository. Agents then add explicit Jira PR
link comments during handoff.

If GitHub device login or SSH auth is blocked, configure the checkout for token
based HTTPS auth:

```bash
agentic --env-file .env github configure-token-auth --repo-path . --remote origin
```

This stores only a credential-helper command in local Git config. The token
stays in <code>.env</code> or the worker environment and is redacted from command output.

Before assigning Developer, Review, or Release Manager work, run the live
readiness diagnostic:

    agentic setup live-diagnostic --project-root .

The GitHub gate is non-mutating. It reads repository metadata, requires
GitHub to report branch write permission through the authenticated token or
user, and verifies the configured local checkout can read origin HEAD and
dry-run push a preflight branch. If the repository is readable but write permission is missing, refresh the
PAT or GitHub CLI login with repository contents, pull request, checks, merge,
and organization access. Then run <code>gh auth setup-git</code> or the token-auth helper,
verify origin on TARGET_PROJECT_PATH, and rerun the diagnostic.

Docker workers that need Git push or PR branch updates can use SSH without
changing session-mode HTTPS behavior:

```text
GITHUB_AUTH_MODE=ssh
GIT_REMOTE_MODE=ssh
GITHUB_SSH_KEY_PATH=/run/secrets/github_ssh_key
GITHUB_SSH_PRIVATE_KEY=
GITHUB_SSH_PRIVATE_KEY_B64=
GITHUB_SSH_KNOWN_HOSTS_PATH=
GITHUB_SSH_STRICT_HOST_KEY_CHECKING=true
```

`GITHUB_SSH_KEY_PATH` is preferred. If a key path and key value are both set,
the mounted path wins, then base64 key value, then raw key value. Use
`docs/docker-git-ssh-auth.md` for the Compose override, diagnostics, and
security rules.

If the target project is separate from the boilerplate source checkout and the
`agentic` console command is not installed globally, configure the helper with
the boilerplate source path:

```bash
PYTHONPATH=/path/to/agentic-bolierplate/src python3 -m agentic_boilerplate.cli \
  --env-file /path/to/agentic-bolierplate/.env \
  github configure-token-auth \
  --repo-path /path/to/target-project \
  --helper-source-root /path/to/agentic-bolierplate/src
```

## Documentation Publication

Release 1.2 defaults to GitHub Pages for published documentation and reports.
Configure:

```text
DOCUMENTATION_PROVIDER=github_pages
GITHUB_PAGES_DOCS_URL=
GITHUB_PAGES_BRANCH=gh-pages
GITHUB_PAGES_SOURCE_DIR=docs
GITHUB_PAGES_CUSTOM_DOMAIN=
GITHUB_PAGES_DEPLOYMENT_MODE=github_actions
GITHUB_PAGES_DEPLOY_TOKEN=
```

`DOCUMENTATION_PROVIDER` supports `github_pages`, `confluence`, `both`, and
`offline`. `GITHUB_PAGES_DOCS_URL` may be empty before the first deployment.
Confluence credentials are required only when `DOCUMENTATION_PROVIDER` is
`confluence` or `both`.

Secret values such as `GITHUB_PAGES_DEPLOY_TOKEN` must never be written to Jira
comments, logs, evidence files, or browser responses.

## Jira Cloud

Variables:

```text
JIRA_BASE_URL=https://your-site.atlassian.net
JIRA_EMAIL=integration-user@example.com
JIRA_API_TOKEN=
JIRA_PROJECT_KEY=<project-key>
JIRA_BOARD_ID=<scrum-board-id>
```

The integration user should be able to:

1. Read project and board metadata.
2. Create stories, tasks, bugs, subtasks, and Test-related issue types.
3. Add issue links.
4. Transition issues through the agreed workflow.
5. Start and close sprints if Release Manager automation is used.
6. Comment on issues with evidence links.

The `AGENT` project and board `1` are dogfooding examples only.

## Confluence

Variables:

```text
CONFLUENCE_BASE_URL=https://your-site.atlassian.net/wiki
CONFLUENCE_SPACE_KEY=<space-key>
CONFLUENCE_SPACE_URL=<space-overview-url>
CONFLUENCE_PARENT_PAGE_ID=<parent-page-id>
CONFLUENCE_EMAIL=integration-user@example.com
CONFLUENCE_API_TOKEN=
```

If Confluence uses the same Atlassian account as Jira, the email and token can
match the Jira integration account.

Confluence is the shared documentation source of truth. Local files are durable
mirrors and worker context inputs.

## AgileTest

Variables:

```text
AGILETEST_CLIENT_ID=
AGILETEST_API_TOKEN=
```

Jira should include the configured AgileTest issue types:

1. `Test`
2. `Test execution`
3. `Test cycle`
4. `Test script`
5. `Test session`

The MVP maps Jira `Test` issues to AgileTest Test Cases and uses board-visible
overview tasks for regression visibility.

## Figma

Variables:

```text
FIGMA_TOKEN=
FIGMA_FILE_KEY=
FIGMA_PROJECT_URL=
FIGMA_EXPORTS_PATH=docs/design
```

Figma access is optional. UI/UX agents may use manual Figma links and exported
artifacts without a token, but every UI-facing story must carry a design
reference in its generated context pack before frontend implementation starts.

Set `FIGMA_TOKEN` and `FIGMA_FILE_KEY` only when the project explicitly allows
live Figma reads. `FIGMA_PROJECT_URL` is the human review link, and
`FIGMA_EXPORTS_PATH` is where exported design snapshots should be stored for
workers that cannot access Figma directly.

## Codex

Variables:

```text
CODEX_DEFAULT_MODEL=gpt-5.5
CODEX_DEFAULT_REASONING=medium
CODEX_DEFAULT_SPEED=normal
CODEX_ALLOW_HIGH_REASONING=true
CODEX_ALLOW_XHIGH_REASONING=false
CODEX_PAUSE_ON_LIMIT=true
CODEX_SAVE_FAILED_REQUEST=true
```

Codex subscription access is controlled by the host session. Do not put OpenAI
or Codex account secrets in Jira comments, evidence, or committed files.

## Durable Path Permission Remediation

Setup validation checks that every PO inbox status folder exists and is writable
by the runtime user before workers start. If validation reports a PO inbox
permission failure, fix local ownership or container volume permissions and
rerun validation. On a WSL project owned by user filip, the usual repair is:

    sudo chown -R filip:filip data/po-inbox

## Durable Paths

Variables:

```text
DURABLE_PO_INBOX_PATH=data/po-inbox
DURABLE_CONTEXT_PACKS_PATH=data/context-packs
DURABLE_CODEX_JOBS_PATH=data/codex-jobs
DURABLE_CODEX_RESULTS_PATH=data/codex-results
DURABLE_AGENT_LOGS_PATH=data/agent-logs
DURABLE_PO_DECISIONS_PATH=data/po-decisions
DURABLE_SPRINTS_PATH=data/sprints
DURABLE_CONFLUENCE_MIRROR_PATH=data/confluence-mirror
```

These paths must be mounted into Docker workers so interrupted work can resume.

## Worker Roles

Variables:

```text
WORKER_ROLES=product_planning,architecture,developer,review,tester,release_manager,scheduler,platform,frontend,ui_ux,security,docs_confluence,devops_platform,data_persistence
TARGET_PROJECT_PATH=/workspace/target-project
```

Valid role values include:

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

Use only roles that the current worker runtime can support. Startup validation
requires `TARGET_PROJECT_PATH` to be set and to resolve to an existing target
project checkout before a worker accepts assignments.

## Redaction Rules

Agents must not print or persist:

1. Token values.
2. Authorization headers.
3. Passwords.
4. Raw request bodies containing secrets.
5. Secret-like file names.

Validation should report field names and missing/invalid status only.

## Token Scope Expectations

Use the smallest scope that supports the configured workflow:

| Integration | Minimum expected access | Scope notes |
| --- | --- | --- |
| GitHub | Repository metadata, branches, pull requests, checks, and trusted merge operation when Review Agent merges | Prefer one repository or organization-scoped token for the target project. Avoid broad personal account scopes unless explicitly approved. |
| Jira Cloud | Project/board read, issue create/update/comment/link, workflow transitions, sprint read/start/close when Release Manager automation is enabled | Prefer a dedicated integration user. Do not reuse a personal Product Owner token for long-running workers unless accepted as a temporary local setup. |
| Confluence | Read/write within the configured documentation space and parent page tree | Avoid site-wide write access when a single project space is enough. |
| AgileTest | Test issue, execution, cycle, and script operations needed by the configured Jira project | Treat client id and token as integration secrets and never expose them in test evidence. |
| Codex subscription/session | Host-side supervised session state and Product Owner-entered limit observations | Do not store account cookies, browser profiles, or session secrets in Docker volumes or project repositories. |
| Database/runtime services | Local runtime connection values only for configured services | Use local `.env` only for dogfooding; use Docker secrets or a secret manager for shared environments. |

Detached Docker worker implementations must also satisfy
`docs/detached-worker-security-review.md` before running live worker pilots.
That review is the Release 1.2 gate for credential mounts, durable logs,
checkpoint persistence, and external write metadata.

## Never Log Or Display

The following values must never appear in CLI output, local API responses,
operator UI views, Jira comments, Confluence pages, evidence, logs, or PR text:

1. Raw token values, API keys, passwords, or client secrets.
2. Authorization headers, cookies, browser/session files, or account recovery
   material.
3. Full `.env` contents.
4. Raw request/response bodies that can contain credentials or Product Owner
   private answers.
5. Secret-like file names or paths, including names containing token, secret,
   password, credential, or API key values.
6. OpenAI/Codex account secrets, browser profile paths, or host session
   artifacts.

Redaction must cover both named assignments such as `api_token=...` and common
standalone token shapes used by local setup, including GitHub PAT-style values.

Operator-visible status views may show configured state, project keys, issue
keys, branch/PR identifiers, relative evidence paths, limit percentages, and
field names that need attention. They must not show secret-bearing values or
raw log file contents.

## First Project Setup Validation

Before starting project agents for a new target project, run the redacted setup
validator from the boilerplate repository:

```bash
agentic setup validate --project-root . --codex-limits-root data/codex-limits
```

Machine-readable output is available for future UI or worker orchestration:

```bash
agentic setup validate --project-root . --codex-limits-root data/codex-limits --json
```

The validator checks:

1. GitHub repository format.
2. Docker Git SSH auth mode and key source when SSH mode is enabled.
3. Jira project key and board id.
4. Confluence space and parent page configuration.
5. AgileTest client id and token presence without printing secrets.
6. Target project path existence.
7. Durable paths resolving under the Docker-mounted `data` directory.
8. PO inbox status-directory writability.
9. Confluence mirror space-directory writability at
   `data/confluence-mirror/<CONFLUENCE_SPACE_KEY>`.
10. Latest Codex limit availability record.

Use `docs/target-project-layout.md` to decide which source-preparation files
belong in the target project checkout and which runtime artifacts belong in
platform durable data.

Use `docs/docker-credential-volume-safety.md` for the Docker worker credential,
mount, no-secret logging, and target repository safety matrix.

If the Codex limit record is missing or unsafe, record current PO-observed
limits before starting new worker activity:

```bash
agentic codex-limits record \
  --id availability-<timestamp> \
  --short-status available \
  --short-remaining <percent> \
  --short-reset-at <iso-time> \
  --broad-status available \
  --broad-remaining <percent> \
  --broad-reset-at <iso-time>
```
