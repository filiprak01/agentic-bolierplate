# Claude And External AI Agent Handoff

Read `AGENTS.md` first. This file is a compact handoff for Claude or other AI
sessions that are asked to help with this repository.

## Current Track

Latest stable release: `1.2.0` on `release/1.2.0` and immutable tag `v1.2.0`.

Release `1.2.0` passed regression and its bounded host-assisted runtime proof.
Do not broaden that claim to autonomous container-only Codex execution or a
proven end-to-end multi-role delivery chain.

## Switch To The Correct Version

Fetch branches and tags:

```bash
git fetch --all --tags
```

Use active development:

```bash
git switch main
git pull --ff-only
```

Use the latest stable release branch when the Product Owner wants a maintained
released snapshot:

```bash
git switch release/1.2.0
git pull --ff-only
```

or:

```bash
git switch --detach v1.2.0
```

Use the tag for an immutable verification baseline and the branch for Release
1.2 maintenance.

## Never Work Directly On Main

For Jira-backed changes, create a dedicated branch:

```text
feature/{JIRA_KEY}-{short-slug}
```

Commit and PR with the Jira key in the title/body. Testing happens after merge
to `main`; Product Owner release acceptance happens later.

## Docker And Operator Stack

Prepare `.env` from `.env.example` and fill the target project values.

Start the PO inbox UI and local runtime API:

```bash
docker compose --profile operator up --build -d
```

Open:

```text
http://localhost:5173
```

Start all role worker loops:

```bash
docker compose --profile workers up --build -d
```

Start one worker role:

```bash
docker compose --profile developer up --build -d
```

The workers use mounted durable data and target-project paths. The generic
worker containers must not receive Codex login folders or copied ChatGPT
subscription credentials.

## Required Configuration

Minimum local project configuration:

```text
GITHUB_REPOSITORY=<owner>/<repo>
JIRA_BASE_URL=https://<site>.atlassian.net
JIRA_EMAIL=<jira-account-email>
JIRA_API_TOKEN=<jira-api-token>
JIRA_PROJECT_KEY=<project-key>
JIRA_BOARD_ID=<board-id>
TARGET_PROJECT_PATH=<absolute-path-to-target-project>
DURABLE_PO_INBOX_PATH=data/po-inbox
DURABLE_CODEX_LIMITS_PATH=data/codex-limits
AGENTIC_WORKSPACES_ROOT=data/agent-workspaces
VITE_AGENTIC_API_BASE_URL=http://localhost:8000
```

Optional integrations include AgileTest, Figma, GitHub Pages, Confluence,
registry publishing, and SSH/PAT Git modes. Do not invent credentials; ask the
Product Owner through PO inbox when a value is missing.

## Codex Subscription Rules

The platform is designed to use host-side Codex authenticated by ChatGPT
subscription:

```bash
codex login
codex login status
codex app-server
```

The host sentinel reads `account/rateLimits/read` and writes durable records to
`data/codex-limits`. Workers read those records before spending quota.

Do not fall back to an OpenAI API key unless a future project explicitly enables
API-paid execution. `CODEX_ACCESS_TOKEN` is only for trusted host-side
automation when explicitly approved.

## Windows WSL Path Rule

If the repo is opened through `\\wsl.localhost\Ubuntu\...` and shell, Python, PO
inbox, or limit checks fail, use `docs/windows-wsl-codex-runtime-troubleshooting.md`.
The validated workaround is to open Codex through a Windows directory
alias/junction to the same repository, then verify:

```bash
git rev-parse --show-toplevel
git remote -v
git status --short
PYTHONPATH=src python -m agentic_boilerplate.cli setup validate --project-root . --codex-limits-root data/codex-limits
```

A path failure is not a subscription failure. Fix the path first.

## Current Capabilities

Available:

1. Jira workflow and dependency rules.
2. Agent role files and session starters.
3. PO inbox CLI/API/UI with multi-project support.
4. Durable local data roots.
5. Docker Compose operator stack and role worker profiles.
6. Host-side Codex runner contracts.
7. Codex quota guard and App Server limit record model.
8. GitHub PR workflow and CI quality gate.
9. AgileTest/Jira evidence and regression workflows.
10. GitHub Pages documentation publication planning.
11. Startup diagnostics and setup troubleshooting.

Not yet proven complete:

1. Container-only autonomous Codex execution.
2. Full detached multi-role chain.
3. Automatic Codex UI model switching.
4. Silent credential repair or permission bypass.

## Main Process

1. PO moves Jira work to `READY TO START`.
2. Orchestrator checks dependencies, labels, design gates, model route, and
   limits.
3. Developer/role agent works on a feature branch and opens a PR.
4. Review Agent checks diff and CI, then merges clean PRs.
5. Tester Agent tests after merge to `main`.
6. Release Manager runs regression, retro, publication, and closure.
7. PO performs release-level acceptance.

When blocked, create or update a PO inbox item and stop. Do not hide blockers in
chat-only notes.
