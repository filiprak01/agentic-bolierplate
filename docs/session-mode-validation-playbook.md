# Session-Mode Validation Playbook

Status: Release 1.1 validation baseline for `AGENT-442`

This playbook validates role-specific Codex sessions before the same behavior is
promoted into Docker worker automation. It is intentionally session-mode first:
the Product Owner starts or supervises Codex sessions, and every role loads
shared instructions from `AGENTS.md`, its role file, and the workflow docs
listed there.

Use this playbook when validating a target project, a release candidate, or a
new role prompt.

For the Architecture and Product Planning handoff into executable development
work, use `docs/session-mode-planning-handoff-validation.md` with this playbook.
For the Developer, Review, Tester, and Release Manager delivery chain, use
`docs/session-mode-delivery-flow-validation.md`.

## Common Startup Contract

For every role:

1. Start from the prompt in `ai_agents/session_starters/README.md`.
2. Replace `<PLATFORM_REPO>`, `<TARGET_PROJECT>`, `<JIRA_ISSUE>`, and
   `<SPRINT>`.
3. Open the platform repository as the working directory.
4. Load `AGENTS.md` first.
5. Load the role file listed in the role matrix below.
6. Check durable Codex limits before Codex-spending work:

```bash
agentic codex-limits latest
agentic setup validate --project-root . --codex-limits-root data/codex-limits
```

7. Validate Jira status and dependency eligibility before changing files.
8. Use the PO inbox for blockers, missing requirements, approvals, or
   assumptions that need Product Owner confirmation.

## Findings Feedback Loop

Session-mode findings must not stay only in chat.

1. Record blocking questions in the durable PO inbox.
2. Record implementation evidence under `data/agent-logs/<JIRA_ISSUE>/`.
3. If the finding changes the current project process, update the matching
   process document through a Jira-backed story or task.
4. If the finding is a future Docker/autonomy requirement, add or update a
   backlog story in `FUNNEL` and reference one of:
   `docs/docker-worker-requirements.md`, `docs/docker-worker-readiness.md`,
   `docs/docker-worker-triggering.md`, or
   `docs/parallel-agent-workspaces.md`.
5. If the finding is a reusable decision, propose a shared documentation update
   rather than hiding it in role-specific notes.

## Role Matrix

| Role | Startup prompt | Role file | Expected outputs | Stop conditions |
| --- | --- | --- | --- | --- |
| Orchestrator | `## Orchestrator` in `ai_agents/session_starters/README.md` | `ai_agents/roles/orchestrator.md` | Eligible READY work selected, dependency blockers reported, model/reasoning stated, next agent handoff identified. | Missing limit record, ambiguous sprint scope, unresolved dependency, no READY work, or Product Owner decision required. |
| Product Planning | `## Product Planning` in `ai_agents/session_starters/README.md` | `ai_agents/roles/product_planning.md` | Draft epics/stories, acceptance criteria, dependencies, context-pack references, and PO-review-ready Jira items in `FUNNEL`. | Missing requirements, unclear acceptance criteria, missing target docs, sprint assignment uncertainty, or business-scope decision required. |
| Architecture | `## Architecture` in `ai_agents/session_starters/README.md` | `ai_agents/roles/architecture.md` | Architecture decisions, NFRs, shared docs, assumptions, and follow-up backlog candidates. | Missing NFR, deployment, data, security, cost, or integration decision requiring Product Owner confirmation. |
| Developer | `## Developer` in `ai_agents/session_starters/README.md` | `ai_agents/roles/developer.md` | Jira subtasks, feature branch, staged commits, validation evidence, and pull request linked to the story. | Story not READY, dependency blocked, context pack missing, quota unavailable, failing validation, merge conflict requiring developer action, or unclear implementation scope. |
| Review | `## Review` in `ai_agents/session_starters/README.md` | `ai_agents/roles/review.md` | Diff-first review result, requested changes or approval comment, conflict status, clean merge when eligible. | Checks failing, conflict detected, required changes open, security/correctness concern, or Product Owner release decision required. |
| Tester | `## Tester` in `ai_agents/session_starters/README.md` | `ai_agents/roles/tester.md` | Acceptance-criteria test evidence, AgileTest-style Test issue where reusable, bug links for failures, and status transition to `TEST COMPLETED` when passed. | Story not merged to `main`, not in `DEV COMPLETED`, unclear expected behavior, missing evidence path, failing test, or blocking bug. |
| Release Manager | `## Release Manager` in `ai_agents/session_starters/README.md` | `ai_agents/roles/release_manager.md` | Regression scope, regression evidence, closure report, release notes, and retro follow-ups in `FUNNEL`. | Sprint stories not tested, blocking bugs open, regression scope incomplete, publication credentials missing, or release acceptance required. |
| Frontend | `## Frontend` in `ai_agents/session_starters/README.md` | `ai_agents/roles/frontend.md` | UI implementation branch, component/API contract changes, validation evidence, accessibility notes, and PR. | Missing UI/UX decision, API contract gap, route/state ambiguity, failing UI validation, or Product Owner copy/design decision required. |
| UI/UX | `## UI/UX` in `ai_agents/session_starters/README.md` | `ai_agents/roles/ui_ux.md` | User flow, design handoff, copy decisions, accessibility requirements, and frontend-ready acceptance notes. | Missing brand/accessibility target, unclear user workflow, unavailable design input, paid-tooling decision, or Product Owner tradeoff required. |
| Security | `## Security` in `ai_agents/session_starters/README.md` | `ai_agents/roles/security.md` | Threat model, risk findings, mitigation stories, credential handling guidance, and security evidence. | Risk acceptance needed, data sensitivity unclear, credential access missing, compliance concern, or high-risk decision requiring Product Owner sign-off. |
| Docs/Confluence | `## Docs/Confluence` in `ai_agents/session_starters/README.md` | `ai_agents/roles/docs_confluence.md` | AI-usable shared docs, Confluence-ready publication artifacts, evidence links, and role/shared-content separation. | Missing publication target, redaction requirement, audience decision, Confluence credentials, or external-sharing approval. |
| DevOps/Platform | `## DevOps/Platform` in `ai_agents/session_starters/README.md` | `ai_agents/roles/devops_platform.md` | Docker/runtime updates, durable mount checks, setup validation, worker evidence, and operational runbooks. | Missing host path, port, credential, infrastructure decision, failing Compose validation, or boundary unclear between session mode and Docker. |
| Data/Persistence | `## Data/Persistence` in `ai_agents/session_starters/README.md` | `ai_agents/roles/data_persistence.md` | Storage contract, migration guidance, retention/recovery behavior, and persistence validation evidence. | Data ownership, retention, privacy, backup, restore, audit, or migration-risk decision requires Product Owner confirmation. |

## Validation Checklist

For each role session, mark these checks in evidence:

1. Role prompt was started from `ai_agents/session_starters/README.md`.
2. `AGENTS.md` and the role file were loaded.
3. Durable Codex limits were checked before work.
4. Jira status and dependency eligibility were checked before work.
5. Expected role outputs were produced or the stop condition was documented.
6. Any blocker was written to the PO inbox.
7. Any Docker/autonomy finding became a `FUNNEL` backlog candidate or a
   reference in the relevant Docker requirement document.

## Pass Criteria

A role passes session-mode validation when it can start from the documented
prompt, perform only eligible work, produce the expected output for its role,
stop safely on missing inputs, and leave durable evidence that another session
can resume.

The release passes session-mode validation when all roles in the matrix have at
least one successful validation record or an explicit Product Owner-approved
reason for deferring that role.
