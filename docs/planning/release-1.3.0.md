# Release 1.3.0 Planning Addendum

Status: proposed release scope; not a release announcement or implementation.
Planning recorded: 2026-11-12.
Tracking epic: AGENT-1081.

Stable fallback remains `release/1.2.0` and immutable `v1.2.0`. No release
branch/tag is created by this plan. Public `main` intentionally omits root
auto-discovery instruction files; that external-tool compatibility change is
not a security or worker-process bypass.

## Confirmed Tracking And Recommended Next Task

| Item | Tracking | Release treatment | Delivery truth |
| --- | --- | --- | --- |
| Sprint Overview / Delivery Control Tower | AGENT-1083 | New 1.3.0 feature; suggested R13 S1 operator visibility slice | External local-only work reported by PO; no committed artifact has been reviewed or integrated. Do not duplicate implementation. |
| Local Backlog v1: durable work items, CLI and API | AGENT-1082 | Recommended bounded external-agent task; suggested R13 S1 foundation slice | FUNNEL candidate, not implemented. |
| Reusable role-independent skills | Earlier PO discussion retained | Separate 1.3.0 planning track; one implementation/testing story per skill, followed by role adoption | Do not replace this track with the new candidates or claim unspecified skills delivered. |

The suggested slices are planning labels, not started Jira sprints or a frozen
release commitment. Both new stories are in FUNNEL under AGENT-1081.

Sprint Overview is independent of Local Backlog v1. Its current scope may keep
the configured Jira source; local-provider support requires a separate
integration story. Existing external work must first be provided as files or a
patch, reviewed, integrated through a normal PR, and tested. Local or uncommitted
work is not merged or delivered work.

## One Bounded External-Agent Candidate

Choose [Local Backlog v1](r13-local-backlog-task.md), using the
[three-stage prompts](r13-local-backlog-three-prompts.md).

The existing `BacklogDraft` and `FileBacklogDraftStore` describe planning output
before Jira publication. They do not supply an independently editable
operational work-item store. The candidate adds that missing foundation instead
of recreating draft generation or replacing Jira in one large task.

The candidate deliberately excludes UI, migration, JQL compatibility, a general
provider abstraction, scheduler rewiring, and new worker orchestration. It does
not claim that existing agents automatically switch away from Jira.

## Local Tracker Roadmap

Implement in this order if the PO selects the local-first direction:

1. Local Backlog v1 store/CLI/API, tracked by AGENT-1082.
2. A project-configurable work-item provider and scheduler pickup/writeback
   integration, depending on step 1. Keep Jira supported; test every relevant
   role, dependency, bug/review rework, and approval path.
3. A dedicated local backlog/sprint-management UI with an accepted design,
   depending on steps 1-2. Add local-provider support to Sprint Overview through
   an explicit integration task rather than rewriting its existing UI.
4. Optional read-only Jira import with preview, identifier mapping, dependency
   validation and explicit conflict handling. Do not begin with bidirectional
   synchronization or delete remote data.

Steps 2-4 are roadmap candidates, not executable stories or implemented
capabilities. Create separate bounded stories when their scope is selected.
Local files remove remote calls from that path; actual agent-speed or quota
savings still require measurement. File-backed planning is not proof of
unattended multi-agent execution.

## Additional PO Inbox Code Candidates

These are new candidate tasks, not additions to AGENT-1082:

| Candidate | User-visible value | Small first slice |
| --- | --- | --- |
| Durable reply drafts | A partially written answer survives refresh or container restart | Project/item-scoped autosave, restore and explicit discard; saving a draft never submits an answer or resumes an agent. |
| Searchable decision history | Find earlier answered/rejected decisions without repeating questions | Project-scoped full-text/filter search over existing answered items and safe result references. No automatic reuse as current approval. |
| Linked decision follow-up | Ask for clarification while preserving the original decision | New linked inbox item, visible history, explicit handling of superseded answers; never rewrite old approval silently. |

Current UI evidence: `POInboxPanel.tsx` keeps the answer field in React state;
there is no durable reply-draft implementation in the inspected baseline.
Answer/approve/reject actions, project filters and JSON exports already exist
and must not be recreated as new features.

## Three-Prompt Delivery Contract

1. Prompt 1: local design, domain/store implementation and unit tests.
2. Prompt 2: CLI/API/configuration integration and focused integration tests.
3. Prompt 3: review/fixes, regression, Docker persistence proof and documentation.

Each invocation has an external hard budget of approximately 80 actions. Target
at most 55-60 calls and reserve the remainder for tests, a checkpoint and the
final report. Platform action counting and timeout behaviour are not controlled
by the repository, so completion within a fixed budget is an estimate.

External execution is local-only: no commit, push, PR, merge, release, live Jira
write or credential request. The PO delegates in-scope engineering decisions
and waives additional clarification/design/readiness/model-switch pauses for
this specific task. Stop only at the prescribed stage boundary or an actual
platform limit, after saving truthful progress. Do not disable security,
permissions, input validation, concurrency protection or tests.

Later integration into the framework still requires the normal code review,
quality checks, merge, post-merge testing and release process. The external
handoff exception must not change production approval/dispatch behaviour.

