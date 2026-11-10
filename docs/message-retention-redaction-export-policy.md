# Message Retention Redaction Export Policy

Status: implemented for `AGENT-680`

This policy applies to Product Owner inbox items, PO-to-agent messages, agent
communication messages, assignment logs, orchestration events, and exported JSON
bundles. It protects project context while still letting the Product Owner
inspect and export decisions from the local operator tools.

## Publication Channels

Default channels:

| Record | Local durable store | Operator UI | Jira comment | Confluence summary | JSON export |
| --- | --- | --- | --- | --- | --- |
| PO inbox item | Yes | Yes | Link or summary only | Summary only | Yes, redacted |
| PO-to-agent message | Yes | Yes | Link or summary only | Summary only | Yes, redacted |
| Agent communication message | Yes | Yes | Link or summary only | Summary only | Yes, redacted |
| Assignment log | Yes | Summary only | Summary only | Summary only | No raw export |
| Orchestration event | Yes | Yes | No raw payload | Summary only | No raw export by default |
| Export bundle metadata | Yes | Yes | Link only | Summary only | Yes, redacted |

Raw local files remain the recovery source of truth. Confluence receives
decision-safe summaries, not raw message payloads, unless the Product Owner
explicitly approves a broader publication. Jira comments should link or
summarize relevant decisions and evidence paths instead of embedding secrets,
raw logs, or full exported JSON.

## Retention States

Default lifecycle behavior:

| Message state | Retention action |
| --- | --- |
| `open`, `queued`, `processing`, `in_progress` | Keep active |
| `answered`, `approved`, `rejected`, `archived`, `processed`, `test_completed`, `accepted/done` | Archive terminal |
| `stale`, `obsolete`, `expired` | Require review before archive or delete |
| Unknown state | Keep local-only until a worker or Product Owner classifies it |

Terminal items are still retained locally for audit and replay, but normal UI
views may hide them unless the Product Owner selects archived or historical
records. Stale or obsolete items must not be deleted automatically; the worker
must create a PO inbox question when deletion or external publication is
unclear.

## Redaction Rules

The following fields or values must be redacted or blocked before export,
Confluence publication, Jira comments, or partner-facing summaries:

1. Tokens, credentials, passwords, API keys, OAuth values, SSH keys, private
   keys, and raw secret values.
2. Database URLs and broker URLs that include host, username, password, or
   internal network details.
3. Unsafe local absolute paths such as Windows user paths, WSL home paths, root
   paths, UNC paths, and mounted-drive paths.
4. Unrelated project context, especially messages from a different Jira key,
   project id, inbox namespace, context pack, or durable runtime folder.
5. Raw environment dumps, command traces, stack traces, or debug payloads that
   can contain secrets.

The domain policy lives in
`src/agentic_boilerplate/domain/message_export_policy.py`. Workers that prepare
message export payloads must call `evaluate_message_export_policy` and either
export the redacted payload from `redact_message_export_payload` or stop with a
PO inbox question when the intended audience is unclear.

## Multi-Project Exports

Every exported message payload must include explicit project identity, normally
`project_id`, `project_key`, or `project`. A single-project export must match
the active project. A multi-project export must keep records grouped by project
and must never merge unrelated project context into one flat message list.

The export shape should be:

```json
{
  "projects": [
    {
      "project_id": "AP",
      "messages": []
    }
  ]
}
```

When the export contains multiple projects, each project gets its own message
list. The UI may offer a single downloaded JSON file, but the file must preserve
the per-project boundaries.

## Operator UI And API Warnings

The Operator UI and local API must warn before exporting message data when:

1. The export contains terminal decision data.
2. The export contains more than one project.
3. The export was redacted.
4. The policy evaluator found forbidden fields or values.
5. Confluence or Jira publication would include raw local paths or secret-like
   values.

Warnings must be visible before the export is generated. A warning is not a
silent failure: the Product Owner can still export a redacted payload, but raw
payload export remains blocked by policy findings.

## References

This policy is required input for:

1. `docs/po-inbox-schema.md`
2. `docs/po-inbox-api.md`
3. `docs/operator-ui.md`
4. `docs/orchestration-event-queue.md`
5. `docs/docker-worker-triggering.md`
6. Future agent communication channel and PO-to-agent message implementation
   stories.
