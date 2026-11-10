# Agent Communication Channels

Status: implemented for `AGENT-674`

This document defines durable project-scoped communication messages for agent
handoffs, resume requests, Product Owner outbox messages, regression routing,
retro collection, and closure readiness.

Agent communication does not replace Jira, GitHub, AgileTest, Confluence,
or the PO inbox. Jira remains the workflow source of truth. The PO inbox
remains the blocker and approval queue. Agent messages are machine-readable
coordination records that explain why work moved, stopped, resumed, or needs a
different role.

## Channel Scopes

Supported scopes:

1. `project`
2. `sprint`
3. `jira_issue`
4. `role`
5. `assignment`
6. `orchestrator`
7. `product_owner_outbox`

Every message is project-scoped and must include `project_id`. Multi-project
operator views and pooled workers must filter by project before acting on a
message.

## Message Types

Supported message types:

1. `status_update`
2. `handoff_request`
3. `artifact_available`
4. `blocked`
5. `resume_request`
6. `po_required`
7. `review_requested`
8. `changes_requested`
9. `test_requested`
10. `bug_fix_requested`
11. `regression_ready`
12. `regression_requested`
13. `retro_requested`
14. `retro_response`
15. `closure_ready`
16. `po_clarification`
17. `po_question_to_agent`
18. `po_resume_instruction`
19. `agent_response_to_po`
20. `scope_change_candidate`

## Envelope

The durable envelope stores:

1. Message id and idempotency key.
2. Message type, priority, delivery status, and timestamps.
3. Correlation and causation ids for reconstructing loops after retries.
4. Project identity: `project_id`, `project_name`, `project_root`,
   `repository`, and `jira_project_key`.
5. Sprint id/name, Jira issue key, assignment id, source role, target role,
   target worker, and target channel.
6. Payload and artifact references.
7. Acknowledgement, consumption, rejection, and expiry state.

Messages are durable and replayable after container restart. Duplicate delivery
is deduplicated by idempotency key.

## CLI

Publish a deterministic story-path handoff:

```bash
agentic agent-messages publish-handoff \
  --id AP-29-dev-review-handoff \
  --current-status "IN PROGRESS" \
  --event development_completed \
  --actor developer \
  --target-status "DEV COMPLETED" \
  --project-id AP \
  --jira-project-key AP \
  --jira-issue-key AP-29 \
  --assignment-id assignment-AP-29-dev \
  --workspace-path /workspaces/AP-29 \
  --context-pack-path data/context-packs/AP-29/context.md \
  --evidence-path data/agent-logs/AP-29/developer-evidence.md \
  --communication-channel-id workflow-AP-29 \
  --pull-request-url https://github.com/org/repo/pull/1 \
  --artifact completed_subtasks=AP-101,AP-102 \
  --artifact jira_pr_link=https://github.com/org/repo/pull/1
```

`publish-handoff` validates the canonical story processing path matrix and the
route's required artifacts before creating the agent message. If the route is
invalid or required artifacts are missing, it creates a durable `blocked`
message for Orchestrator unless `--no-blocked-message` is supplied.

Publish a Review handoff:

```bash
agentic agent-messages publish \
  --id AP-29-review-request \
  --type review_requested \
  --source-role developer \
  --target-role review \
  --target-channel role \
  --project-id AP \
  --jira-project-key AP \
  --jira-issue-key AP-29 \
  --assignment-id assignment-AP-29-dev \
  --correlation-id workflow-AP-29 \
  --payload-json '{"pr_url":"https://github.com/org/repo/pull/1"}' \
  --artifact-ref data/agent-logs/AP-29/dev-evidence.md
```

List project messages:

```bash
agentic agent-messages list --project-id AP --json
```

Acknowledge and consume:

```bash
agentic agent-messages ack AP-29-review-request
agentic agent-messages consume AP-29-review-request
```

## Handoff And Rework Loops

Required loops:

1. Developer completion creates `review_requested` for the Review role.
2. Review changes create `changes_requested` for Developer and include
   finding-history references.
3. Review merge creates `test_requested` for Tester after merge to `main`.
4. Tester failure creates or links a Bug and emits `bug_fix_requested` for
   Developer.
5. Tester retest or Review rereview may emit `artifact_available` with
   evidence references.

Messages do not move Jira status by themselves. Each receiving role must still
re-check Jira status, dependencies, linked bugs, assignment locks, design gates,
and Codex limits before starting work.

## Regression Retro And Closure

Orchestrator emits `regression_requested` to the Tester role pool only after
regression gates pass and a regression manifest is available. It must not
request regression while unresolved bugs, missing manifests, missing PO
approvals, stale locks, or closed Codex limit gates block execution.

After regression reaches a durable stop point, Orchestrator emits
`retro_requested` to participating role agents. Agents respond with
`retro_response` containing observations, blockers, risks, process
improvements, and evidence references.

Scope-changing retro findings must route to Product Planning, Architecture, or
the PO inbox. `closure_ready` is emitted only after regression and required
retro responses are received or explicitly waived by the Product Owner.

## PO Outbox Separation

Product Owner messages to agents use the `product_owner_outbox` channel and
message types such as `po_clarification`, `po_question_to_agent`, and
`po_resume_instruction`.

Use PO inbox items when an agent needs a Product Owner decision before work can
continue. Use PO outbox messages when the Product Owner initiates context,
clarification, status questions, or resume instructions.

## Resume Gate

Orchestrator may emit `resume_request` only after these gates pass:

1. Codex limit gate allows work when quota is needed.
2. Jira status is eligible.
3. Dependency gate passes.
4. Linked bugs are clear.
5. Assignment locks are clear.
6. Required Product Owner answers are recorded.
7. Required artifacts are available.

When any gate fails, Orchestrator emits `blocked` or leaves the assignment
paused with a visible reason instead of sending `resume_request`.

## Redaction

Durable message publication redacts sensitive payload and artifact data before
write. Raw credentials, token-like values, database URLs, private keys, and
unsafe local absolute paths must not be persisted in agent message payloads.
