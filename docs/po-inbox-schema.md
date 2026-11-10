# PO Inbox Schema

Status: implemented for `AGENT-12`

The PO inbox schema defines durable Product Owner communication records. The
store, CLI, and API build on this contract in later Sprint 2 stories.

## Message Types

Supported values:

1. `blocking_question`
2. `assumption`
3. `fyi`
4. `approval_request`

## Statuses

Supported values and durable folder names:

| Status | Folder |
| --- | --- |
| `open` | `open` |
| `answered` | `answered` |
| `approved` | `approved` |
| `rejected` | `rejected` |
| `archived` | `archived` |

Allowed combinations:

| Message Type | Allowed Statuses |
| --- | --- |
| `blocking_question` | `open`, `answered` |
| `assumption` | `open`, `answered`, `archived` |
| `fyi` | `open`, `archived` |
| `approval_request` | `open`, `approved`, `rejected` |

## Fields

Required core fields:

1. `id`
2. `message_type`
3. `status`
4. `title`
5. `message`
6. `agent_role`
7. `created_at`

Traceability fields:

1. `agent_id`
2. `jira_issue_key`
3. `project_id`
4. `project_name`
5. `project_root`
6. `repository`
7. `jira_project_key`
8. `confluence_page_id`
9. `context_pack_path`

Worker blocker metadata is carried in the inbox item text fields and in the
assignment reference until the multi-project inbox schema adds first-class
columns. A worker-created `blocking_question` must include project id,
assignment id, role, Jira issue key, question, response needed, resume context,
and resume context path in `message`, while `jira_issue_key`,
`context_pack_path`, `project_id`, and `agent_id` remain populated for
filtering.

Decision-support fields:

1. `business_impact`
2. `recommendation`
3. `options`
4. `answer`
5. `answered_at`

Audit fields:

1. `timestamp`
2. `actor`
3. `action`
4. `note`

`blocking_question` and `approval_request` items require `business_impact` and
`recommendation` so the Product Owner can decide without reverse-engineering
the agent's intent.

Terminal decision statuses `answered`, `approved`, and `rejected` require
`answer` and `answered_at`. Open items must not contain answer values.

## Agent Roles

Supported values:

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

## Serialization

The schema is JSON-compatible. Enums are stored as strings, options and audit
events are stored as arrays, and validation runs when data is loaded back into a
`POInboxItem`.

## Retention And Export Safety

PO inbox items are covered by
`docs/message-retention-redaction-export-policy.md`. Workers and UI/API export
paths must preserve project identity, redact configured secret-like values, and
warn the Product Owner before exporting decision data. Raw credentials, tokens,
database URLs, unsafe local absolute paths, and unrelated project context must
not be written into exported inbox JSON or shared documentation.

Project identity fields are defined in `docs/multi-project-identity.md`.
Existing single-project records without project identity still load with blank
identity values.

## Export Envelope

AGENT-672 defines the read-only PO inbox JSON export envelope used for
Product Owner handoff to another Codex session, another model, or ChatGPT Pro
UI.

Required envelope fields:

1. `schema_version` - currently `po-inbox-export/v1`.
2. `generated_at` - UTC timestamp.
3. `scope` - `project` or `all_projects`.
4. `filters` - status, project, role, message type, and Jira issue filters.
5. `items` - for `project` scope only.
6. `project` - for `project` scope only.
7. `projects` - for `all_projects` scope only.
8. `errors` - safe per-project export errors.

Exported items must include project identity and should include `composite_id`
when records are aggregated from configured project inboxes. Export generation
must not change inbox item status or audit history.

The export envelope is browser-visible. It must not contain raw credentials,
tokens, database URLs, local inbox roots, unsafe absolute paths, or unrelated
project context.
