# Docker Credential And Volume Safety Matrix

Status: Release 1.1 safety baseline for `AGENT-441`.

This matrix defines how future Docker workers should handle credentials,
volumes, target repositories, durable data, and logs. It supports Release 1.1
requirements discovery and later Release 1.2+ detached worker implementation.

Release 1.1 does not grant detached workers live autonomous access to Codex,
Jira, GitHub, Confluence, or AgileTest without the host/session boundary and
Product Owner-approved workflow.

Release 1.2 detached worker implementation uses
`docs/detached-worker-security-review.md` as the security gate for credential
mounts, durable logs, checkpoints, and external-write metadata.

## Credential Categories

| Category | Example variables | Owner | Worker access | Logging rule |
| --- | --- | --- | --- | --- |
| GitHub repository access | `GITHUB_TOKEN`, `GITHUB_REPOSITORY`, `GITHUB_DEFAULT_BRANCH` | Product Owner or integration owner | Read from environment or secret manager only | Log repository and branch, never token |
| Jira Cloud access | `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEY`, `JIRA_BOARD_ID` | Product Owner or Jira integration owner | Read from environment or secret manager only | Log project key, board id, and issue key, never token/email token pair |
| Confluence access | `CONFLUENCE_BASE_URL`, `CONFLUENCE_SPACE_KEY`, `CONFLUENCE_PARENT_PAGE_ID`, `CONFLUENCE_API_TOKEN` | Product Owner or Confluence space owner | Read from environment or secret manager only | Log space key/page id, never token |
| AgileTest access | `AGILETEST_CLIENT_ID`, `AGILETEST_API_TOKEN` | Product Owner or test integration owner | Read from environment or secret manager only | Log configured state and issue keys, never token/client secret |
| Codex model settings | `CODEX_DEFAULT_MODEL`, `CODEX_DEFAULT_REASONING`, `CODEX_DEFAULT_SPEED` | Product Owner | Read-only configuration | Log selected model/reasoning/speed |
| Codex subscription/session state | Host Codex session, operator-entered limit records | Product Owner | Host-side/session boundary only in Release 1.1 | Log limit percentages and actions, never account/session secrets |
| Database/runtime services | `POSTGRES_*`, `REDIS_*` when configured | Platform owner | Environment or Docker secrets | Log service name and health only |
| Target project settings | `TARGET_PROJECT_PATH`, project-specific env keys | Product Owner / project owner | Read path and allowed project env only | Log paths and missing fields, never secret values |

## Volume Categories

| Path category | Example path | Mount mode | Shared? | Purpose |
| --- | --- | --- | --- | --- |
| Platform durable data | `./data:/workspace/data` | read/write | shared | PO inbox, logs, state, Codex jobs/results, limits, context packs |
| PO inbox | `data/po-inbox` | read/write through store/API | shared | Product Owner questions, answers, approvals, assumptions |
| Agent logs | `data/agent-logs` | append/write | shared by role/issue partition | Durable evidence and worker logs |
| Agent state | `data/agent-state` | read/write | shared with locking | Worker registry, assignments, locks |
| Codex jobs/results | `data/codex-jobs`, `data/codex-results` | read/write | shared with assignment ids | Host-side runner requests and outputs |
| Codex limits | `data/codex-limits` | read mostly, operator writes | shared | Operator-entered quota availability |
| Context packs | `data/context-packs` | read for worker, write for planner | shared by issue path | Story-specific worker inputs |
| Target project workspace | assigned worktree/clone mounted at `/workspace/project` | read/write for assigned worker | isolated per assignment | Source changes for one Jira issue |
| Boilerplate instructions | immutable checkout or copied instruction bundle | read-only for workers | shared/read-only | `AGENTS.md` and role workflows |
| Temporary tool output | container temp or assignment temp path | read/write | isolated | Build/test scratch output |
| Database volume | `postgres-data`, `redis-data` | service-managed | service shared | Runtime persistence/cache |

## Mount Rules

1. Mount platform durable data at stable `/workspace/data` paths.
2. Mount the assigned target workspace at `/workspace/project`.
3. Mount boilerplate instruction files read-only when the worker only needs
   process context.
4. Do not mount the same mutable target checkout into multiple concurrent
   implementation workers.
5. Do not mount host home directories, browser profiles, SSH directories, or
   raw Codex account/session folders into worker containers.
6. Prefer Docker secrets or host secret managers for sensitive values when
   moving beyond local MVP usage.
7. `.env` may be used for local dogfooding, but validation must redact values.

## No-Secret Logging

Workers may log:

1. Jira issue keys and statuses.
2. GitHub repository name, branch, PR number, and commit SHA.
3. Confluence space key and page id.
4. AgileTest issue keys and execution identifiers.
5. Configured model, reasoning, speed, and limit gate result.
6. Durable path names and relative artifact paths.

Workers must not log:

1. API tokens.
2. Authorization headers.
3. Passwords.
4. Raw `.env` contents.
5. Full request bodies containing secrets.
6. Browser/session cookies.
7. Personal account credentials.

Validation failures should report field names and remediation steps, not secret
values.

Detached worker persistence must also redact common standalone token shapes,
including GitHub PAT-style values, before writing failed request artifacts,
checkpoints, worker logs, Jira comments, PR descriptions, or UI payloads.

## Target Repository Safety

Future Docker workers must treat source repositories as assignment-scoped.

Rules:

1. Developer workers use one feature branch per Jira issue.
2. Review workers inspect PR diffs and repository context but do not resolve
   conflicts directly.
3. Tester workers test only after merge to `main`.
4. Release Manager workers operate on selected sprint/release scope.
5. Parallel implementation workers use isolated worktrees or clones.
6. A worker cannot write outside its assigned project workspace and durable
   evidence/output paths.

## Open Product Owner Decisions

Before Release 1.2 detached worker implementation, decide:

1. Whether live workers use one shared integration user or role-specific Jira
   and GitHub accounts.
2. Whether Codex execution remains host-side/session-backed or moves to an API
   execution model.
3. Whether Docker workers may restart automatically after limit reset or must
   wait for Product Owner confirmation.
4. Whether target workspaces default to Git worktrees or fresh clones.
5. Whether Confluence publication is automatic after sprint closure or requires
   explicit Product Owner approval.
6. Whether client-facing evidence packages need a stricter export/redaction
   profile than internal evidence.

These decisions do not block Release 1.1 documentation and dry-run validation.
