# PO Inbox Store

Status: implemented for `AGENT-13`

The PO inbox store persists Product Owner communication records as local JSON
files. It is the MVP source of truth for agent questions, assumptions, FYI
messages, and approval requests.

## Storage Layout

Each inbox item is stored as one JSON file under the folder for its current
status:

```text
data/po-inbox/
  open/
    question-001.json
  answered/
  approved/
  rejected/
  archived/
```

Folder names follow the PO inbox schema:

| Status | Folder |
| --- | --- |
| `open` | `open` |
| `answered` | `answered` |
| `approved` | `approved` |
| `rejected` | `rejected` |
| `archived` | `archived` |

Item IDs may contain letters, numbers, dots, underscores, and hyphens. Path
traversal values are rejected before a file path is created.

## Store Operations

`FilePOInboxStore` supports:

1. `ensure_directories()` to create the full status-folder layout.
2. `create(item)` to validate and persist a new inbox item.
3. `read(item_id)` to locate and deserialize an item by ID.
4. `update(item_id, update_fn)` to load, modify, validate, and persist an item.
5. `move(item_id, status)` to move an item to another valid status.

Create rejects duplicate item IDs across all status folders. Updates must keep
the same item ID, and status moves remove the old status-file after the new file
has been written.

## Durability Rules

Writes are atomic:

1. The item is serialized to a temporary file in the target status folder.
2. The temporary file is flushed and synced.
3. The temporary file replaces the target JSON file.
4. Any leftover temporary file is removed during cleanup.

This keeps PO decisions recoverable if a worker stops because of a local
container shutdown, Codex limit pause, or process interruption.

## Validation

The store validates items through the PO inbox schema before write and after
read. Malformed JSON payloads or schema-invalid files fail fast instead of being
silently accepted.

Valid terminal decisions still need schema-required fields. For example, moving
a blocking question to `answered` requires `answer` and `answered_at`; callers
should use `update()` when adding the PO response and audit event.

## Agent Usage

Agents should use this store whenever they need durable PO communication:

1. Product Planning and Architecture Agents create blocking questions when
   requirements, dependencies, or non-functional requirements are unclear.
2. Developer, Review, Tester, and Release Manager Agents create FYI or approval
   items when the PO should see important process information.
3. Scheduler reads open inbox items before assigning dependent work.
4. Workers resume from stored inbox state after restart.

Jira and Confluence integrations may mirror these records later, but local
files remain the durable fallback for MVP.
