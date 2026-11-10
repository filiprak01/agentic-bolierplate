# Jira Project Issue Adapter

The Jira adapter is the project-specific boundary used by workers when they
need to validate Jira access, read board metadata, search issues, create issues,
or update issue fields.

## Runtime Configuration

Configure the target Jira project through environment variables:

```text
JIRA_BASE_URL=https://your-site.atlassian.net
JIRA_EMAIL=integration-user@example.com
JIRA_API_TOKEN=<jira-cloud-api-token>
JIRA_PROJECT_KEY=<project-key>
JIRA_BOARD_ID=<scrum-board-id>
```

The current dogfooding project uses:

```text
JIRA_PROJECT_KEY=AGENT
JIRA_BOARD_ID=1
```

These values are examples for this boilerplate project only. New projects must
provide their own project key and board id in `.env` or the worker environment.
Agents must not hardcode `AGENT`, board `1`, or Filip's Atlassian site when
working on another project.

## Adapter Selection

Use `jira_cloud_adapter_from_settings(settings)` for live Jira Cloud work.

Use `MockJiraProjectIssueAdapter` for local tests, dry runs, and workflow
validation that must not call Jira Cloud.

Both adapters implement the same project issue contract:

1. Validate configured project, board, statuses, issue types, priorities, and
   link types.
2. Search issues with JQL.
3. Create issues in the configured project.
4. Update mutable issue fields.
5. Read sprint metadata from the configured board.
6. Read sprint issue membership for regression, retro, and closure checks.
7. Add required board-visible support issues to a sprint before closure.
8. Transition sprint lifecycle state through the Jira Agile API.

## Startup Validation

Workers should validate Jira access before accepting assignments that require
Jira writes. Validation should confirm:

1. The configured project key exists and is accessible.
2. The configured board id exists and belongs to the expected project.
3. Required issue types exist for the project workflow.
4. Required statuses exist for the workflow.
5. Required link types exist for dependency management.

If validation fails, the worker must pause before starting work and record the
configuration issue in durable local state or the PO inbox.

## Sprint Lifecycle Support

Sprint lifecycle operations must stay board-configurable. Workers must use the
configured `JIRA_PROJECT_KEY` and `JIRA_BOARD_ID` when they:

1. List future, active, or closed sprints.
2. Read the active sprint before closure checks.
3. Verify that board-visible regression and retro tasks belong to the sprint.
4. Add missing support tasks to the sprint before closure.
5. Start or close a sprint through the Jira Agile API.

This keeps the workflow reusable for future projects instead of binding the
implementation to the current `AGENT` dogfooding board.
