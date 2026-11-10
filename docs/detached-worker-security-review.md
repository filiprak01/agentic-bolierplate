# Detached Worker Security Review

Status: Release 1.2 security gate for `AGENT-623`.

This review records the credential, workspace, log, and external-write
constraints that detached Docker worker stories must satisfy before the worker
pilot can run against a target project.

## Scope

Reviewed areas:

1. Docker worker credential mounts and environment variables.
2. Durable logs, evidence, Codex pause artifacts, and detached worker
   checkpoints.
3. Target project workspaces and parallel worker isolation.
4. GitHub, Jira, Confluence, AgileTest, database, and Codex subscription
   boundaries.
5. Downstream Release 1.2 stories that build host-side execution, bounded
   worker commands, failed-request persistence, limit auto-wait, and PO inbox
   blocking.

Out of scope:

1. Production cloud infrastructure hardening.
2. Paid security scanning products.
3. Full compliance certification.
4. Detached in-container Codex account/session access.

## Security Decision

Detached worker implementation can proceed only under the existing host-side
Codex execution boundary.

Workers may receive assignment context, durable data paths, target workspaces,
and role-specific integration credentials. Workers must not receive raw Codex
subscription session files, browser profiles, account cookies, or full host home
mounts.

## Threat Model

| Risk | Impact | Required mitigation | Release blocking |
| --- | --- | --- | --- |
| Secret value appears in logs, checkpoints, failed requests, PR comments, Jira comments, or UI responses | Token exposure and unauthorized external writes | Redact known token shapes before persistence and never echo raw `.env` contents | Yes |
| Shared mutable checkout is mounted into multiple implementation workers | Cross-story contamination and accidental commits | Allocate one isolated worktree or clone per assignment | Yes |
| Worker resumes with stale or wrong assignment context | Wrong project, branch, or Jira issue receives changes | Re-check assignment id, project id, role, Jira key, branch, context pack, and lock before resume | Yes |
| Worker runs external writes without assignment metadata | Lost traceability and hard-to-audit changes | Every adapter write includes assignment id, Jira key, role, worker id, evidence path, and idempotency key | Yes |
| Worker starts without current limit state | Unexpected quota drain and unfinished work | Gate Codex-backed actions on durable limit availability before request creation | Yes |
| PO decision is resolved only through agent-to-agent communication | Product Owner loses control of business decisions | Create or update PO inbox items for decisions, approvals, and blockers | Yes |
| Integration token has broad personal account scope | Excessive blast radius if exposed | Prefer project/org scoped tokens or dedicated integration user accounts | No for local dogfooding, yes before shared use |
| Evidence contains private PO answers or raw request payloads | Private data exposure in repo or external systems | Evidence stores summaries, field names, issue keys, and artifact references, not raw secret-bearing content | Yes |

## Credential Constraints

1. Read credentials from environment, Docker secrets, or an approved secret
   provider only.
2. `.env` is allowed for local dogfooding, but workers must log field names and
   validation status only.
3. Use `GITHUB_TOKEN` or `GH_TOKEN` for HTTPS GitHub operations; use mounted SSH
   keys only when the project explicitly selects SSH.
4. GitHub tokens should be repository or organization scoped when possible.
5. Jira, Confluence, and AgileTest tokens should belong to an integration user
   with only the project/space permissions needed by the workflow.
6. Codex subscription state remains host-side/session-backed until a later
   release explicitly implements a safe container boundary.

## Volume Constraints

1. Mount durable coordination data at `/workspace/data`.
2. Mount one assignment workspace at `/workspace/project`.
3. Mount instruction bundles read-only when the worker does not need to mutate
   the boilerplate source.
4. Do not mount host home directories, browser profiles, raw SSH directories, or
   Codex app session folders into workers.
5. Do not mount the same mutable target checkout into multiple implementation
   workers.
6. Store test evidence and worker logs under durable `data/agent-logs`, not
   ad-hoc non-durable temp paths.

## Log And Evidence Constraints

Allowed in logs, evidence, Jira comments, PR descriptions, and UI status:

1. Jira keys, branch names, commit SHAs, PR URLs, status names, and sprint names.
2. Integration field names and configured/missing states.
3. Relative durable artifact paths.
4. Limit percentages, reset timestamps, and scheduler actions.
5. Redacted command summaries and redacted resume recommendations.

Forbidden:

1. API tokens, PATs, passwords, client secrets, authorization headers, cookies,
   and browser/session files.
2. Full `.env` contents.
3. Raw request/response bodies that can include credentials or private PO
   answers.
4. Secret-like file names or full host paths that expose account data.

The shared redaction helper masks Authorization headers, token/API token
assignments, password/secret assignments, OpenAI-style `sk-...` keys, and
standalone GitHub PAT-like values such as `github_pat_...` or `ghp_...`.

## Downstream Story Constraints

| Story | Required security constraint |
| --- | --- |
| `AGENT-624` host-side Codex execution bridge | Bridge inputs and outputs must store redacted request summaries and must not mount or persist Codex subscription secrets. |
| `AGENT-625` bounded worker assignment command | Command must validate assignment, workspace, context, credentials, and limits before external writes. |
| `AGENT-626` failed request persistence | Failed request and partial-output artifacts must redact secret-like values before write. |
| `AGENT-627` limit auto-wait and resume scheduling | Wait/resume artifacts may show percentages and reset times, not account/session secrets. |
| `AGENT-628` PO inbox pause/resume | Inbox blockers may include business questions and artifact references, not raw credential values or private request bodies. |
| `AGENT-684` Docker Git SSH key auth | Key path or key value must be optional configuration, redacted from output, and mounted only into workers that need Git operations. |

## Deferred Items

These are not blockers for the Release 1.2 local/dogfooding path but must be
planned before shared or client-facing worker deployments:

1. Role-specific integration accounts for review separation.
2. External secret manager or Docker secret provider instead of `.env`.
3. Formal dependency/security scanning in CI.
4. Client-facing evidence export profile with stricter redaction.
5. Production infrastructure threat model.
6. Container image provenance and registry access policy.

## Acceptance Checklist

1. A downstream worker story cannot require committing secrets.
2. A worker story cannot require raw secrets in non-durable evidence files.
3. Logs and UI responses show only redacted values or field names.
4. Detached checkpoints and pause artifacts redact standalone GitHub PATs.
5. The implementation plan keeps Codex subscription/session secrets outside
   worker containers.
6. Any remaining risk that needs PO acceptance is tracked as a deferred item or
   PO inbox decision.
