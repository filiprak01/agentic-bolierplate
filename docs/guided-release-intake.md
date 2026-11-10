# Guided Release Intake

Status: Release 1.2 planning and setup workflow.

Use `agentic setup intake` before Product Planning or Architecture agents create
release scope for a new target project. The command validates the target
project root, source document folders, Jira, AgileTest, Codex limit state,
durable data paths, and the target implementation repository. It writes a
durable JSON and Markdown readiness report and creates PO inbox blockers for
missing required setup.

## Command

```bash
PYTHONPATH=src python3 -m agentic_boilerplate.cli setup intake \
  --project-id ap \
  --project-name "Airline Project" \
  --release-id R1 \
  --project-root /home/user/business/airline-project \
  --target-repository example-org/airline-project \
  --jira-project-key AP \
  --jira-board-id 42 \
  --product-docs-root docs/product \
  --architecture-root docs/architecture \
  --evidence-root data/agent-logs \
  --durable-data-root data \
  --report-root data/intake-reports \
  --codex-limits-root data/codex-limits
```

Relative product, architecture, evidence, durable data, and report paths are
resolved from the target project root. Absolute paths are allowed for local
operator setups when a project needs custom folders.

## Required Inputs

The intake is ready only when:

- target project root exists;
- target repository is configured as `owner/name`;
- Jira project key, board id, integration email, and API token are configured;
- AgileTest client id and token are configured unless `--no-require-agiletest`
  is used;
- product docs root exists and contains at least one Markdown source document;
- architecture root exists;
- durable evidence, data, and report roots can be created under an existing
  parent directory;
- latest Codex limit availability allows new work.

Confluence is validated but not blocking by default because Release 1.2 moves
GitHub Pages to the default documentation publication surface. Use
`--require-confluence` only for projects where Confluence publication is a hard
requirement.

## Outputs

The command writes:

- `data/intake-reports/<project-id>/<release-id>/intake-report-<timestamp>.json`
- `data/intake-reports/<project-id>/<release-id>/intake-report-<timestamp>.md`

When required setup is missing, the command also creates durable PO inbox items
under `DURABLE_PO_INBOX_PATH/open`. The item id is stable for a project, release,
and failed check, so repeated intake runs report the same blocker instead of
creating duplicates.

Product Planning and Architecture agents must reference the intake report before
creating epics, stories, architecture plans, or context packs for the release.
