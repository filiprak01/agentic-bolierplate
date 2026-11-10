# PO Inbox Local API

Status: implemented for `AGENT-19`

The local API exposes health and PO inbox endpoints for workers and future UI
surfaces. It uses only the Python standard library for the MVP and writes
through `FilePOInboxStore`.

## Start Locally

Docker Compose starts the full operator inbox stack on ports 8000 and 5173 by
default:

```bash
docker compose --profile operator up --build -d
curl http://127.0.0.1:8000/health
curl "http://127.0.0.1:8000/po-inbox?status=open"
```

Open the Product Owner UI at:

```text
http://localhost:5173
```

The API service command is:

```bash
agentic --inbox-root /workspace/data/po-inbox api serve --data-root /workspace/data --host 0.0.0.0 --port 8000
```

Set `AGENTIC_API_PORT` or `AGENTIC_OPERATOR_UI_PORT` in `.env` when host ports
must be changed. Keep `VITE_AGENTIC_API_BASE_URL` browser-reachable, usually
`http://localhost:8000`.

Stop the local operator stack without deleting durable inbox files:

```bash
docker compose down
```

## Health

```text
GET /health
```

Response:

```json
{
  "external_systems_checked": false,
  "po_inbox_ready": true,
  "service": "agentic-boilerplate",
  "status": "ok"
}
```

The health endpoint does not call GitHub, Jira, Confluence, AgileTest, Codex, or
other external systems.

## List Inbox Items

```text
GET /po-inbox
GET /po-inbox?status=open
GET /po-inbox?status=open&project_id=AP
GET /po-inbox?status=open&agent_role=architecture
GET /po-inbox?status=open&message_type=blocking_question
GET /po-inbox?status=open&jira_issue_key=AP-29
```

Response body:

```json
{
  "items": [],
  "projects": [],
  "project_errors": []
}
```

Items are serialized using the PO inbox schema.
`project_id` filters the list to one target project namespace when present.

When `data/operator-projects.json` exists, the API aggregates inboxes from the
configured project roots. Each returned item includes:

```json
{
  "id": "question-001",
  "source_item_id": "question-001",
  "source_project_id": "AP",
  "composite_id": "AP::question-001",
  "project_identity": "Airline POC (AP)"
}
```

The browser and agents must use `composite_id` for read and decision endpoints
when it is present. This prevents item id collisions when two projects contain
the same inbox item id.

If one project inbox cannot be read, healthy project items still load and the
failed project appears in `project_errors`. Error objects contain public project
identity and safe text only; they do not include inbox paths or credentials.

Operator project configuration example:

```json
{
  "projects": [
    {
      "project_id": "AP",
      "project_name": "Airline POC",
      "jira_project_key": "AP",
      "repository": "example-org/airline-poc",
      "inbox_root": "projects/ap/po-inbox"
    },
    {
      "project_id": "AGENT",
      "project_name": "Agentic Boilerplate",
      "jira_project_key": "AGENT",
      "repository": "example-org/agentic-boilerplate",
      "inbox_root": "po-inbox"
    }
  ]
}
```

Relative `inbox_root` values resolve under the configured API `--data-root`.
Absolute roots are allowed for local operator setup but are never returned to
the browser.

## Read Inbox Item

```text
GET /po-inbox/{item_id}
GET /po-inbox/{composite_id}
```

Response body:

```json
{
  "item": {
    "id": "question-001"
  }
}
```

## Export Inbox Items

```text
GET /po-inbox/export
GET /po-inbox/export?status=open
GET /po-inbox/export?status=open&project_id=AP
GET /po-inbox/export?status=open&project_id=all
```

The export endpoint is read-only. It must not move inbox items, append audit
events, or write export records back into the inbox.

One selected project returns one project export object:

```json
{
  "schema_version": "po-inbox-export/v1",
  "generated_at": "2026-08-10T08:00:00Z",
  "scope": "project",
  "filters": {
    "status": "open",
    "project_id": "AP",
    "agent_role": "all",
    "message_type": "all",
    "jira_issue_key": ""
  },
  "project": {
    "project_id": "AP",
    "project_name": "Airline POC",
    "jira_project_key": "AP",
    "repository": "example-org/airline-poc"
  },
  "items": [],
  "errors": []
}
```

All Projects returns a list of project export objects:

```json
{
  "schema_version": "po-inbox-export/v1",
  "generated_at": "2026-08-10T08:00:00Z",
  "scope": "all_projects",
  "filters": {
    "status": "open",
    "project_id": "all",
    "agent_role": "all",
    "message_type": "all",
    "jira_issue_key": ""
  },
  "projects": [
    {
      "project": {
        "project_id": "AP"
      },
      "items": []
    }
  ],
  "errors": []
}
```

Exported items use the same safe serialization as list/read responses,
including `composite_id` when present. Export output excludes credentials,
tokens, database URLs, local inbox roots, and unsafe local absolute paths.

## Create Inbox Item

```text
POST /po-inbox
```

Example request body:

```json
{
  "id": "question-001",
  "message_type": "blocking_question",
  "title": "Choose Jira status",
  "message": "Which status should drafts use?",
  "project_id": "AP",
  "project_name": "Airline POC",
  "repository": "example-org/airline-poc",
  "jira_project_key": "AP",
  "business_impact": "Controls PO workflow.",
  "recommendation": "Use FUNNEL."
}
```

Created items start in `open` status and include an audit event.
Project identity fields are optional for backward compatibility, but new
multi-project worker-created records should populate them according to
`docs/multi-project-identity.md`.

## Decisions

Answer a question or assumption:

```text
POST /po-inbox/{item_id}/answer
POST /po-inbox/{composite_id}/answer
```

Approve or reject an approval request:

```text
POST /po-inbox/{item_id}/approve
POST /po-inbox/{item_id}/reject
```

Resolve an archivable item:

```text
POST /po-inbox/{item_id}/resolve
```

Decision bodies:

```json
{
  "answer": "Use FUNNEL.",
  "actor": "po"
}
```

Resolve bodies:

```json
{
  "actor": "po",
  "note": "Seen."
}
```

All decisions append audit events and persist through the file-backed store.

## Errors

Errors are small JSON objects:

```json
{
  "error": {
    "code": "bad_request",
    "message": "Missing required field: title."
  }
}
```

The API does not print or return integration tokens or loaded settings.
