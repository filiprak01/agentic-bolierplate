# PO Inbox Permissions

Status: active MVP dogfooding policy for `AP-31`

The durable Product Owner inbox lives under the configured
`DURABLE_PO_INBOX_PATH`, which defaults to:

```text
data/po-inbox
```

## Ownership Rule

The repository user and the runtime that executes `agentic po-inbox` must be
able to create, update, move, and delete JSON files in every inbox status
folder:

```text
open
answered
approved
rejected
archived
```

The status folders must not be left owned by `root` when the host-side Codex
session, local CLI, or non-root Docker worker is expected to update inbox
items. A root-owned status folder can make the root `data/po-inbox` directory
look healthy while still preventing blocker cleanup when an item is answered
or approved.

## Docker And Host Boundary

Docker containers may create or modify durable files through the mounted
`data/` directory. After container or root-side maintenance, verify that the
host user can still write to the inbox status folders before starting agents.

For the local WSL dogfooding setup, the expected owner is the normal workspace
user:

```bash
chown -R "$USER:$USER" data/po-inbox
```

When running this from outside WSL or after files were created as root, run the
same ownership repair as the appropriate administrator/root user and then
validate startup again.

## Validation

Run startup validation before agent work:

```bash
PYTHONPATH=src python3 -m agentic_boilerplate.cli setup validate \
  --project-root . \
  --codex-limits-root data/codex-limits
```

Run worker startup validation when checking a role worker:

```bash
PYTHONPATH=src python3 -m agentic_boilerplate.cli worker run-once \
  --role platform \
  --worker-id permission-check \
  --workspace-path . \
  --check-integrations
```

The startup validator checks each PO inbox status folder directly. A failure
such as `paths.po_inbox.answered.writable` means the folder exists but the
current runtime cannot write there.

