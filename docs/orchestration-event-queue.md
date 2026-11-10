# Orchestration Event Queue

Status: implemented for AGENT-629

The orchestration event queue is the durable trigger backbone for Release 1.2
worker handoffs. It gives session-mode and future Docker workers a shared
at-least-once event stream without requiring live in-memory state.

## Event Vocabulary

The queue supports these trigger events:

1. `assignment_completed`
2. `pr_ready`
3. `pr_merged`
4. `development_completed`
5. `review_completed`
6. `review_blocked`
7. `test_requested`
8. `test_passed`
9. `test_failed`
10. `testing_completed`
11. `testing_failed`
12. `bug_created`
13. `regression_requested`
14. `regression_completed`
15. `retro_requested`
16. `retro_response_received`
17. `limit_paused`
18. `po_blocked`
19. `po_question_created`
20. `worker_idle`

## Durable Event Fields

Each event stores:

1. Event id.
2. Event type.
3. Queue status.
4. Idempotency key.
5. Source role.
6. Optional target role.
7. Jira issue key.
8. Source assignment id.
9. Correlation id.
10. Scope key, such as sprint or release id.
11. Project identity fields: `project_id`, `project_name`, `project_root`,
    `repository`, and `jira_project_key`.
12. JSON payload.
13. Evidence paths.
14. Created, updated, processed, and rejected metadata.

The idempotency key is the duplicate-delivery guard. The default format is:

```text
<event_type>:<JIRA_ISSUE_KEY|->:<assignment_id|->:<scope_key|->
```

When a repeated event arrives with the same idempotency key, the file-backed
queue returns the existing event instead of creating another active trigger.

## Status Flow

Supported statuses:

1. `queued`
2. `processing`
3. `processed`
4. `rejected`

Allowed transitions:

1. `queued` -> `processing`
2. `queued` -> `processed`
3. `queued` -> `rejected`
4. `processing` -> `processed`
5. `processing` -> `rejected`

`processed` and `rejected` are terminal. Invalid transitions fail loudly so
agents do not silently replay already-finished work.

## CLI Usage

Enqueue:

```bash
agentic orchestration-events enqueue \
  --id event-AGENT-629-pr-merged \
  --type pr_merged \
  --source-role review \
  --target-role tester \
  --jira-issue-key AGENT-629 \
  --source-assignment-id assignment-AGENT-629 \
  --scope-key r12-s3 \
  --payload-json '{"pr": 159}'
```

List for UI/operator inspection:

```bash
agentic orchestration-events list --status queued --json
agentic orchestration-events list --project-id AP --json
```

Claim next event:

```bash
agentic orchestration-events claim-next --json
```

Complete or reject:

```bash
agentic orchestration-events complete event-AGENT-629-pr-merged
agentic orchestration-events reject event-AGENT-629-pr-merged --reason "target role is no longer eligible"
```

## Relationship To Later Stories

AGENT-629 only introduces the durable event contract, store, and CLI
inspection/claiming surface. Later orchestration stories consume the queue to
perform role-specific handoffs:

1. Developer -> Review -> Tester.
2. Tester failure -> Bug creation -> Developer rework.
3. Blocked story fallback to another eligible sprint item.
4. Regression and retro trigger requests.
5. Multi-project agent communication channels.

Before creating follow-up assignments from a queue event, the scheduler must
still re-check Jira status, dependencies, assignment locks, Codex limits,
Definition of Ready, and PO inbox blockers.

Event payloads and evidence paths are covered by
`docs/message-retention-redaction-export-policy.md`. Agent communication and
PO-to-agent message stories must evaluate event payloads before exposing them in
the Operator UI, exporting JSON, or publishing summaries to Confluence.

Project identity fields are defined in `docs/multi-project-identity.md`.
