# Release 1.2 Migration Guide

This guide helps an existing Release 1.1 or MVP test project move onto Release
1.2 without losing local durable data.

## Before Upgrade

1. Commit or intentionally ignore local project source changes.
2. Back up the durable data folder that contains PO inbox, agent logs, context
   packs, Codex limits, Codex jobs, and agent state.
3. Confirm the target project root and worker workspace root are different
   directories.
4. Confirm GitHub token or SSH settings are project-appropriate.
5. Confirm Jira project key, board id, and workflow statuses match the target
   project.

## Environment Changes

Review these settings for each project:

1. `TARGET_PROJECT_PATH`
2. `AGENTIC_WORKSPACES_ROOT`
3. `DURABLE_PO_INBOX_PATH`
4. `DURABLE_CONTEXT_PACKS_PATH`
5. `DURABLE_CODEX_LIMITS_PATH`
6. `DURABLE_AGENT_STATE_PATH`
7. `DURABLE_AGENT_LOGS_PATH`
8. `GITHUB_REPOSITORY`
9. `GITHUB_AUTH_MODE`
10. `DOCUMENTATION_PROVIDER`

Release 1.2 defaults documentation publication to GitHub Pages. Confluence is
optional and should be enabled only when the project requires it.

## Validation After Upgrade

Run:

```bash
agentic setup validate --project-root . --codex-limits-root data/codex-limits
agentic docs-site validate --docs-root docs
agentic worker run-once --role developer --worker-id migration-dry-run
```

The worker dry-run should not claim live work unless the assignment queue and
limit state allow it.

## Rollback

If the upgrade blocks work:

1. Stop worker containers.
2. Preserve the current durable data folder for investigation.
3. Restore the previous release branch or tag.
4. Restore the backed-up durable data folder if needed.
5. Create a Jira bug with setup validation output and worker evidence.
