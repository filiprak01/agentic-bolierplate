# R13-LOCAL01 - Local Backlog v1

Tracking: AGENT-1082, parent epic AGENT-1081.
Status: FUNNEL candidate; no implementation has been delivered by this document.
Execution: [three bounded external-agent prompts](r13-local-backlog-three-prompts.md).

## Goal

The PO and agents can create, inspect and revise durable project work items
using local CLI/API calls without Jira credentials or remote access. This is a
backend foundation for a future local tracker, not a full Jira replacement.

## Fixed Scope Decisions

1. Work-item kinds: Story, Bug and Task. Create always starts in FUNNEL.
2. Required data: project id, caller-supplied immutable item key, kind, title,
   description and acceptance criteria. Store workflow status, optional sprint
   label, prerequisite keys, integer revision and audit entries.
3. Example keys are DEMO-1 and DEMO-2. The caller chooses keys in this first
   slice; automatic counters and Jira-compatible key allocation are excluded.
4. Identity is project plus item key. Identical keys in different projects must
   remain distinct. Project/key changes are not ordinary editable fields.
5. Keep one item per JSON file below a configurable durable root. Default:
   `data/local-backlog`; configure through `DURABLE_LOCAL_BACKLOG_PATH`.
   Wire the selected path consistently through CLI and the operator API.
6. Reuse existing durable storage, configuration and HTTP patterns where useful.
   Do not reuse BacklogDraft as if it already tracked mutable delivery state.
7. Linux/WSL/Docker is the required backend execution target for this slice.
   Preserve existing command behaviour on other supported platforms; do not
   introduce an unconditional OS-specific import that breaks unrelated commands.
8. Serve this feature through the existing local operator API and Docker image,
   not a new server, database, frontend, remote service or orchestration stack.

## Mutation And Dependency Contract

- Initial revision is 1. Mutations supply `expected_revision`, actor and a
  short reason; success increments once and records the actual change in audit.
- Duplicate create, stale revisions and conflicting concurrent writers return
  typed failures; HTTP uses 409 for conflict. CLI exits nonzero with safe output.
- Atomic file replacement alone is not concurrency control. Serialize the
  revision check and write for the supported execution target, including across
  processes. Do not silently drop successful changes.
- Ordinary updates edit content, sprint label or prerequisites, not status.
  Status changes use a separate transition operation and existing canonical
  status/event/actor rules. Reject unsupported routes without mutation.
- Reuse the canonical route matrix and compatible policy helpers. Do not invent
  a local workflow that skips established approval, review or testing stages.
  No actual review/merge/test evidence may be fabricated to unblock a demo.
- A prerequisite key refers to an existing item in the same project. If X lists
  Y as a prerequisite, Y blocks X. Reject unknown/self references and cycles.
  Keep dependency validation and mutation consistent under concurrent changes.
- New store mutations do not create agent assignments or grant worker pickup
  eligibility. Full worker/provider/evidence integration is a separate story.
- No delete endpoint, bulk mutation, import or silent data repair in this task.
- Validate keys and resolved file paths at the trust boundary; reject traversal
  and child-path symlink escapes. Responses must not expose absolute host paths,
  environment values or secrets.

## Interfaces

Add a small CLI group such as:

```text
agentic local-backlog create
agentic local-backlog get
agentic local-backlog list
agentic local-backlog update
agentic local-backlog transition
```

Use file arguments for structured item/update input if that matches current CLI
patterns. Keep JSON output machine-readable. Document exact flags after
implementation rather than claiming a proposed command already exists.

Add matching project-scoped local API operations under `/local-backlog` using
existing handler/error conventions. List supports project, status and optional
sprint-label filters. Missing items return 404; invalid input 400; conflicts 409.
Use one service/store contract for CLI and API rather than duplicating rules.

The existing operator Docker data mount must preserve the selected store root.
Document how a custom absolute root receives its own bind mount; do not assume
that naming a host path in .env automatically mounts it into a container.

## Acceptance Criteria

1. Valid items can be created/read/listed/edited using CLI and API, with matching
   persisted data. A fresh process reads previously created items.
2. Default/custom root handling and same-key/different-project isolation work.
3. Duplicate create and invalid content/keys/paths fail without data changes.
4. Revision conflict tests prove that two writers starting at one revision do
   not silently overwrite each other. Rejected operations do not append audit.
5. Normal updates cannot change identity/status; accepted transitions follow
   the canonical route rules, increment once and retain audit.
6. Prerequisite direction is correct; missing/self/cyclic links are rejected.
7. Unconfigured Jira/GitHub access does not block these local operations; tests
   prove no remote adapter calls are needed.
8. Existing planning drafts, Jira-mode configuration and unrelated endpoints
   remain compatible and pass regression.
9. A real Docker API create/read/update plus container recreation proves
   persistence through the configured mount. Use isolated synthetic data.
10. Final handoff includes actual commands/results, API/CLI usage, decisions,
    remaining limitations and local diff. No commits/pushes from the external
    agent and no claim that existing scheduler workers now run without Jira.

## Existing Context To Inspect

- `src/agentic_boilerplate/domain/backlog_draft.py`
- `src/agentic_boilerplate/storage/backlog_draft.py`
- `src/agentic_boilerplate/storage/po_inbox.py`
- `src/agentic_boilerplate/domain/story_processing_path_matrix.py`
- `src/agentic_boilerplate/domain/dependency_eligibility.py`
- `src/agentic_boilerplate/api/local.py`
- `src/agentic_boilerplate/api/live_local.py`
- `src/agentic_boilerplate/entrypoint.py`
- `src/agentic_boilerplate/cli.py`
- `src/agentic_boilerplate/config/settings.py`
- `docker-compose.yml`, `.env.example`, existing tests and storage patterns

Inspect actual callers and exports before editing; this list is context, not a
requirement to change every file. Isolate new implementation where possible.
Sprint Overview may touch the same API entrypoints: do not depend on its
uncommitted files or assume two patches merge without review.

## Explicit Non-Goals

No backlog UI, sprint CRUD, epics/subtasks/test issue management, Jira migration,
two-way sync, local JQL parser, removal of Jira dependencies from existing
workers, scheduler rewiring, role/model redesign, or new AI calls. No throughput
or token-savings claim without a benchmark. Do not start Sprint Overview again.

