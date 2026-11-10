# Local Operator UI

Status: Release 1.2 dockerized operator surface

The local Operator UI is a Vite, React, and TypeScript frontend for Product
Owner and operator workflows. Release 1.2 runs the inbox through Docker Compose
so the Product Owner does not need host-side Node or npm for normal use.

## Scope

The UI is local-only. It is intended for an operator running the boilerplate on
their own machine.

The UI must read platform durable data through the configured local API. It
must not read target project runtime folders directly.

Release 1.1 assumes one active project inbox at a time. The shell displays
active project identity so future releases can extend the model to multiple
project inboxes without changing the primary navigation.

Operator UI implementation stories must include an accepted `Design Reference`
before frontend work starts. The accepted design may be a Figma frame, Canva
review, exported snapshot, or local HTML mockup, but it must be traceable from
the Jira story and evidence. The canonical gate is documented in
`docs/ui-design-gate.md`.

## Stack

Frontend stack:

1. Vite
2. React
3. TypeScript
4. Lucide icons

The stack is intentionally separated under `ui/operator/` so backend package
metadata and Python runtime behavior stay stable.

## Configuration

The UI reads only public Vite environment variables:

```text
VITE_AGENTIC_PROJECT_NAME
VITE_AGENTIC_JIRA_PROJECT_KEY
VITE_AGENTIC_API_BASE_URL
```

Do not expose GitHub, Jira, Confluence, AgileTest, OpenAI, Codex, or database
tokens through `VITE_` variables. Vite embeds `VITE_` values into the frontend
bundle.

`VITE_AGENTIC_API_BASE_URL` must be reachable from the Product Owner browser.
For local Docker it should normally stay `http://localhost:8000`; do not change
it to the Compose service name `http://api:8000`, because browser fetch calls do
not run on the Docker network.

## Docker Operator Stack

Start the complete local operator inbox:

```bash
docker compose --profile operator up --build -d
curl http://127.0.0.1:8000/health
curl "http://127.0.0.1:8000/po-inbox?status=open"
```

Open:

```text
http://localhost:5173
```

The operator profile starts:

1. `api`, serving the local PO inbox/operator API.
2. `operator-ui`, serving the built React app through Nginx.
3. Required unprofiled Compose dependencies, including durable local data
   mounts.

The API container explicitly uses:

```text
/workspace/data
/workspace/data/po-inbox
```

This keeps PO inbox items, status data, limit records, and logs durable across
container restarts through the repository `./data:/workspace/data` mount.

Stop the operator inbox without deleting durable data:

```bash
docker compose down
```

Only use `docker compose down --volumes` when PostgreSQL/Redis named volumes
should be removed. It does not remove the repository `./data` folder.

## Developer Fallback Commands

Start the local API used by the Operator UI:

```bash
docker compose up -d api
curl http://127.0.0.1:8000/health
```

The Compose service runs:

```bash
agentic api serve --host 0.0.0.0 --port 8000
```

The host port defaults to `AGENTIC_API_PORT=8000`.

Install dependencies:

```bash
npm --prefix ui/operator install
```

Run locally:

```bash
npm --prefix ui/operator run dev
```

Build:

```bash
npm --prefix ui/operator run build
```

Smoke test:

```bash
npm --prefix ui/operator run smoke
```

The host npm/Vite commands are for frontend development only. Product Owner
operation should use the Docker operator stack above.

## Navigation Foundation

Design Reference:

1. Jira story: `AGENT-669`
2. Design document: `docs/design/operator-shell-navigation-design.md`
3. Design artifact: `docs/design/operator-shell-navigation-options.html`
4. Selected shell: Option B - Compact Header With Hamburger Drawer
5. Implementation story: `AGENT-665`

The shell includes navigation for:

1. PO Inbox
2. Limits
3. Agent Status
4. Logs
5. Projects
6. Agent Messages
7. Settings

The AGENT-665 implementation replaces the original one-page operator view with
a compact header and hamburger drawer. The active section is shown in the
header, the configured Jira project key stays visible, and the main workspace
renders one active section at a time. Future sections can start as empty states
inside the same shell instead of adding more vertical dashboard panels.

The PO Inbox remains the default section because blocking decisions are the
Product Owner's primary daily action. Status, limits, and logs keep using the
same local API boundary and are routed into independent sections.

## PO Inbox List And Read

Design Reference:

1. Jira story: `AGENT-667`
2. Design document: `docs/design/compact-po-inbox-ux-design.md`
3. Design artifact: `docs/design/compact-po-inbox-ux-options.html`
4. Selected inbox layout: Option A - Compact Split Pane With Sticky Action Dock

The PO Inbox view reads open items from:

```text
GET /po-inbox?status=open
```

The detail view reads one item from:

```text
GET /po-inbox/{item_id}
```

The UI displays the item type, title, agent role, optional agent identifier,
project identity, status, and created time in the list. The detail view shows
message, business impact, recommendation, options, and audit events.

Unknown future inbox item types must be displayed as raw labels rather than
silently filtered out. Invalid inbox files or API errors must be shown as safe
operator-visible errors without exposing local paths or secrets.

Later stories attach answer, approve, reject, and resolve actions.

Message exports, PO-to-agent messages, and multi-project inbox views must follow
`docs/message-retention-redaction-export-policy.md`. The UI must warn before
exporting decision data and must not expose raw tokens, database URLs, unsafe
local absolute paths, or unrelated project context in browser-visible payloads.

AGENT-637 and AGENT-672 must reference the AGENT-667 inbox design before
changing the inbox layout, filters, aggregation, or JSON export controls.

AGENT-637 adds the multi-project inbox contract. In multi-project mode, the
operator UI reads `items`, `projects`, and `project_errors` from the same local
API. It shows an All Projects selector, project labels on each inbox row,
message type filters, agent role filters, and Jira issue filtering. Read and
decision actions use each item's `composite_id` when present, so duplicate item
ids in different project inboxes do not collide.

Safe per-project errors remain visible above the inbox list while healthy
project items continue to load.

### PO Inbox JSON Export

AGENT-672 adds project-scoped JSON export from the PO Inbox area. The export
controls follow the AGENT-667 selected design:

1. `Export Project` downloads one selected project export envelope.
2. `Export All` downloads an All Projects export envelope.
3. Export uses current message type, agent role, status, project, and Jira
   filters.
4. Export is separate from Answer, Approve, Reject, Resolve, and Archive.
5. Export must not mutate item status or audit events.
6. Export download filenames include scope and a safe timestamp.

The UI calls:

```text
GET /po-inbox/export
GET /po-inbox/export?status=open&project_id=AP
GET /po-inbox/export?status=open&project_id=all
```

Export envelopes are intended for Product Owner handoff to another Codex
session, another model, or ChatGPT Pro UI. The API provides only browser-safe
project identity, filters, items, options, answers, audit events, and safe
errors.

## PO Inbox Actions

The action view writes through the same local API used by the CLI:

```text
POST /po-inbox/{item_id}/answer
POST /po-inbox/{item_id}/approve
POST /po-inbox/{item_id}/reject
POST /po-inbox/{item_id}/resolve
```

The UI applies the same schema rules before submitting:

1. `blocking_question` and `assumption` items can be answered while open.
2. `approval_request` items can be approved or rejected while open.
3. `fyi` and `assumption` items can be archived while open.
4. Terminal or unsupported transitions are disabled and shown with a clear
   operator message.

Successful actions refresh the list from platform durable data so the CLI and
UI observe the same persisted result.

## Operator Status Views

Design Reference:

1. Jira story: `AGENT-671`
2. Design document:
   `docs/design/worker-dashboard-assignment-visibility-design.md`
3. Design artifact:
   `docs/design/worker-dashboard-assignment-visibility-options.html`
4. Selected dashboard layout: Option A - Split Dashboard With Lifecycle Rail
   And Timeline
5. Implementation stories: `AGENT-638`, `AGENT-675`, `AGENT-676`,
   `AGENT-679`

The status panel reads read-only platform summaries from:

```text
GET /operator-status
```

The API response contains only operational summaries:

1. Known worker roles and worker statuses.
2. Durable assignment statuses, Jira keys, worker ids, and branch names when
   present.
3. Latest recorded Codex short-window and broad quota capacity.
4. Recent durable log file metadata.

The UI must display empty states when no workers, assignments, limit records,
or logs exist. It must not display secret-bearing configuration, token values,
or log file contents. Durable log links are shown as platform-relative paths so
the operator can locate evidence without exposing local absolute paths in the
browser.

No-secret display rules:

1. Show operational state, issue keys, PR/branch identifiers, limit
   percentages, and relative evidence paths only after the local API has
   redacted secret-like keys and values.
2. Never render raw `.env` data, authorization headers, API tokens, passwords,
   client secrets, cookies, browser profile paths, or Codex session artifacts.
3. Never render raw log contents in the browser. Show metadata and relative
   evidence paths only.
4. Treat secret-like file names and free-text failure reasons as unsafe unless
   the API response has already redacted them.

Worker and assignment visibility must remain check-oriented. The Product Owner
should be able to select a project or Jira issue and see completed lifecycle
steps, skipped steps, remaining steps, the next expected agent, blocked/stuck
state, and safe artifact references without scrolling through a large one-page
dashboard.

AGENT-638 implements the first dashboard contract by extending
`GET /operator-status` with browser-safe assignment fields:

1. `artifact_refs`, containing safe context pack, Codex job, output, evidence,
   failed request, PO resume context, branch, and PO inbox references when
   present.
2. `story_lifecycle`, containing ordered lifecycle steps, step states, next
   expected step, blocked reason, sprint label, and needs-process-mapping
   fallback.
3. `codex_limit_gate`, containing the current limit gate decision and
   resume-after value.

AGENT-692 adds stacked PR operator visibility to the same endpoint. When an
assignment carries `AgentAssignment.stack_metadata`, the API includes a
`stack_lanes` collection with browser-safe lane rows:

1. Stack id, lane id, stack mode, resolver path version, and layer order.
2. Jira issue key, current agent role, current assignment status, and next
   expected step.
3. PR links when recorded by the assignment, or branch name when only branch
   metadata is available.
4. Blocked reason, stale/retest flag, and evidence state using `final`,
   `provisional`, `stale`, `blocked`, or `not-recorded`.

This stacked PR operator visibility lets the Product Owner see which stories
are independent, which are in a stack, which stack layer is next, and whether
Tester Agent evidence is final or still provisional before a lower layer
changes. The API model remains UI-ready even when the frontend is not open, so
CLI operators and future dashboards can consume the same `stack_lanes` data.

The UI groups assignments by project identity, shows blocked or waiting counts,
renders lifecycle rails per Jira issue, and shows safe artifact chips. If a
story lifecycle cannot be inferred from assignment role/status, the UI displays
`Needs process mapping` instead of guessing.

Detailed stack process rules live in
`docs/stacked-pr-operator-visibility.md`,
`docs/stacked-pr-sprint-path-resolver.md`, and
`docs/stacked-pr-ci-quality-gates.md`.

The Agent Messages route uses the same AGENT-671 design reference for
communication timeline and graph views. It must distinguish automated
agent-to-agent messages from Product Owner inbox blockers, show why the
Orchestrator sent or refused a `resume_request`, and preserve project identity
on every event.

AGENT-675 implements the first communication view through:

```text
GET /agent-messages
GET /agent-messages/{message_id}
```

The list endpoint accepts safe filters for `project_id`, `jira_issue_key`,
`assignment_id`, `role`, `message_type`, `status`, and `target_channel`. The
response contains browser-safe message summaries and a simple graph projection
with project, role, Jira issue, assignment, channel, and message nodes. The UI
renders the communication timeline next to that graph so the Product Owner can
see which agent handed off work, which issue or assignment was referenced, and
whether a message is automated, Product Owner-originated, or a PO-inbox blocker.

AGENT-676 adds Product Owner-originated message actions:

```text
POST /agent-messages
POST /agent-messages/{message_id}/acknowledge
POST /agent-messages/{message_id}/consume
POST /agent-messages/{message_id}/respond
```

The composer writes to durable agent communication channels and does not mutate PO inbox item status.
A Product Owner message can target a role, worker,
assignment, Jira issue, sprint, or project context by setting the matching
message fields. Supported PO-originated message types are `po_question_to_agent`,
`po_clarification`, `po_resume_instruction`, and `scope_change_candidate`.

Agent responses are stored as `agent_response_to_po` messages with causation
and correlation back to the original message. Resume instructions remain queued
messages; Orchestrator or Scheduler workers must still re-check Jira,
dependencies, linked bugs, locks, design gates, PO inbox blockers, and Codex
limits before consuming the instruction.

AGENT-679 adds operator rescue controls for stuck workers and stale locks:

```text
GET /operator-rescue
GET /operator-rescue/{assignment_id}
POST /operator-rescue/{assignment_id}/{action}
```

Supported actions are `pause`, `resume`, `retry`, `requeue`, `cancel`,
`clear-stale-lock`, and `refresh-diagnostics`. The API returns server-side
decisions for every action before the UI enables it. A blocked action returns a
safe `409` response with blocker reasons and does not mutate assignment state,
write audit files, or publish agent messages.

Allowed rescue actions write a durable audit file under platform data and a
durable agent communication message. Resume-like actions publish a
`resume_request`; pause, cancel, and diagnostics publish a `status_update`.
The UI never edits assignment JSON directly.

Safety gates:

1. Resume, retry, requeue, and stale-lock recovery require an open Codex limit
   gate.
2. Resume, retry, and requeue are blocked when another active assignment exists
   for the same project, Jira issue, and role.
3. Fresh worker locks are blocked from `clear-stale-lock`; the lock must be
   older than the configured stale-lock threshold unless the assignment is
   already terminal.
4. Completed assignments keep their Codex job id for traceability.
5. Rescue responses expose only safe assignment summaries, relative audit refs,
   and durable message ids.

## Codex Limits View

Design Reference:

1. Jira story: `AGENT-670`
2. Design document: `docs/design/codex-limits-form-design.md`
3. Design artifact: `docs/design/codex-limits-form-options.html`
4. Selected limits layout: Option A - Adaptive Limit Windows With Atomic Save
   Panel
5. Implementation story: `AGENT-664`

The limits view must support one-window Pro subscription plans and multi-window
short and broad quota plans. The UI shows each durable limit window as a compact
status tile with used percentage, remaining percentage, reset time, and a safe
status label.

The UI reads current limits from:

```text
GET /codex-limits
```

The UI writes Product Owner limit observations through one atomic endpoint:

```text
POST /codex-limits/records
```

The update form is atomic: the Product Owner enters all visible window values
and saves one coherent limit record. The implementation must keep typed values
visible after validation or API failure so the operator can correct the record
without retyping it.

The Local API applies its configured Codex account scope and bucket id whenever
the update omits those fields. Explicit scope values are accepted only when no
corresponding server scope is configured or when they exactly match it; a
configured-scope mismatch returns `400` and writes nothing. An identical retry
with the same explicit record id is idempotent. Reusing that id with different
immutable content returns a sanitized `409` without exposing the submitted id
or other request values.

Required states are loading, empty, available, low limit, limit reached, stale
record, unknown window, validation error, save success, and save failure. These
states must use safe copy and must not expose secrets, raw `.env` values, host
absolute paths, or Codex account artifacts.
