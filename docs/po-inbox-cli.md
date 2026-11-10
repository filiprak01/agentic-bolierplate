# PO Inbox CLI

Status: implemented for `AGENT-18`

The PO inbox CLI gives the Product Owner and local workers a durable way to
inspect and resolve inbox items before the web UI exists.

## Entry Points

After installing the package, both commands use the same CLI:

```bash
agentic po-inbox --help
agentic-boilerplate po-inbox --help
```

When running from source without installing:

```bash
PYTHONPATH=src python -m agentic_boilerplate.cli po-inbox --help
```

## Durable Inbox Root

By default the CLI reads `.env` and uses `DURABLE_PO_INBOX_PATH`.
Agents must use this CLI, the PO inbox API, or the shared store abstraction for
all PO inbox writes. Do not create or edit PO inbox JSON files directly from a
role prompt, target-project script, or target-project checkout.

For local testing, override the root:

```bash
PYTHONPATH=src python -m agentic_boilerplate.cli \
  --inbox-root /tmp/po-inbox \
  po-inbox list
```

The CLI does not print integration tokens or loaded settings.

The durable inbox root is platform-owned. It should resolve under the
boilerplate `data/` directory that is mounted into Docker, not under
`TARGET_PROJECT_PATH`.

## Commands

List open items:

```bash
PYTHONPATH=src python -m agentic_boilerplate.cli \
  po-inbox list --status open
```

Read one item as JSON:

```bash
PYTHONPATH=src python -m agentic_boilerplate.cli \
  po-inbox read question-001
```

Create a manual blocking question:

```bash
PYTHONPATH=src python -m agentic_boilerplate.cli \
  po-inbox create \
  --id question-001 \
  --type blocking_question \
  --title "Choose Jira status" \
  --message "Which status should drafts use?" \
  --business-impact "Controls PO workflow." \
  --recommendation "Use FUNNEL."
```

Create a worker blocker and pause the matching assignment:

```bash
PYTHONPATH=src python -m agentic_boilerplate.cli \
  --inbox-root data/po-inbox \
  worker pause-for-po \
  --assignment-store-root data/agent-state \
  --assignment-id assignment-AGENT-628 \
  --worker-id developer-1 \
  --project-id AP \
  --question "Which retry behavior should the worker use?" \
  --response-needed "Select retry policy before continuing." \
  --resume-context "Continue from the original context pack after the PO answer."
```

This command creates a `blocking_question`, writes a JSON resume context under
`data/agent-state/po-inbox-resume-contexts/`, stores the inbox item id on the
assignment, and moves the assignment to `paused_po`.

Answer a question or assumption:

```bash
PYTHONPATH=src python -m agentic_boilerplate.cli \
  po-inbox answer question-001 --answer "Use FUNNEL."
```

Requeue PO-blocked assignments after the item is answered or approved and the
normal Jira/dependency/design/limit gates still pass:

```bash
PYTHONPATH=src python -m agentic_boilerplate.cli \
  --inbox-root data/po-inbox \
  worker resume-po-inbox \
  --assignment-store-root data/agent-state \
  --eligible-issue-key AGENT-628
```

Use `--json` when the orchestrator or a Docker worker needs machine-readable
`po_resume_instruction` records. Open, rejected, missing, or ineligible inbox
items keep the assignment paused with a visible skip reason.

Approve or reject an approval request:

```bash
PYTHONPATH=src python -m agentic_boilerplate.cli \
  po-inbox approve approval-001 --answer "Approved."

PYTHONPATH=src python -m agentic_boilerplate.cli \
  po-inbox reject approval-002 --answer "Rejected."
```

Resolve a FYI or other archivable item:

```bash
PYTHONPATH=src python -m agentic_boilerplate.cli \
  po-inbox resolve fyi-001 --note "Seen."
```

Validate that a target project did not receive misplaced PO inbox files:

```bash
PYTHONPATH=src python -m agentic_boilerplate.cli \
  po-inbox validate-paths \
  --target-project-root /path/to/target/project
```

Import a schema-valid external question file into the configured durable inbox:

```bash
PYTHONPATH=src python -m agentic_boilerplate.cli \
  po-inbox import \
  --input /path/to/question.json
```

Imports validate the same schema as normal CLI-created items and reject invalid
or duplicate inbox records without moving them into the durable store.

## Status Rules

The CLI writes through `FilePOInboxStore`, so all schema rules still apply:

1. Blocking questions can be `open` or `answered`.
2. Approval requests can be `open`, `approved`, or `rejected`.
3. FYI items can be `open` or `archived`.
4. Assumptions can be `open`, `answered`, or `archived`.
5. Terminal decisions require schema-valid answer data where the schema
   requires it.

Invalid transitions fail with a concise error and do not modify the stored item.
