# Multi-Project Identity

Status: implemented for `AGENT-636`

Release 1.2 prepares the boilerplate for one operator surface and shared worker
pool to manage multiple target projects without mixing context.

## Identity Fields

Durable project-aware records use these optional fields:

1. `project_id` - stable local project namespace, such as `AP`.
2. `project_name` - Product Owner readable project name.
3. `project_root` - target project root used by the worker assignment.
4. `repository` - GitHub repository owner/name for the target or process repo.
5. `jira_project_key` - Jira project key used for issue routing.

`project_id` is the primary filter key. Existing single-project records that do
not contain these fields remain valid and load with blank identity values.

## Covered Records

Project identity is serialized on:

1. Product Owner inbox items.
2. Agent assignments and assignment status summaries.
3. Detached worker checkpoints.
4. Orchestration events.

Future communication-channel records and exported inbox bundles must reuse the
same field names.

## Filters

Current filters:

```bash
agentic po-inbox list --project-id AP
agentic worker status --project-id AP
agentic orchestration-events list --project-id AP
```

The local API supports:

```text
GET /po-inbox?status=open&project_id=AP
```

New records should populate identity fields at creation time. When the worker
does not know a value, it should leave the field blank rather than infer from a
different project or previous assignment.

## Operator Inbox Aggregation

Release 1.2 operator inbox aggregation uses `data/operator-projects.json` to
map public project identity to local durable inbox roots. The file is local
operator configuration and must not contain tokens.

Each configured project entry uses:

1. `project_id`
2. `project_name`
3. `jira_project_key`
4. `repository`
5. `inbox_root`

The API returns collision-safe item references as `composite_id`, using the
format `{project_id}::{item_id}`. Browser actions and agent UI tooling must use
`composite_id` when present so a decision is written back to the source project
inbox, not the current default project.

The API also returns `projects` and `project_errors` in list responses. A
per-project read failure must not hide healthy projects from the Product Owner.
Project errors are browser-safe and do not include local inbox roots,
credentials, database URLs, or secret values.
