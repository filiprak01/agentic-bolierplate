# Local Backlog v1 - Three External-Agent Prompts

Tracking: AGENT-1082. These prompts are for the same continuing task checkout.
Read the [bounded specification](r13-local-backlog-task.md).
Each stage ends at its planned boundary; it does not ask for PO approval.

## Prompt 1 - Design, Store And Unit Tests

```text
Implement Stage 1 of AGENT-1082, Local Backlog v1, in the current public
filiprak01/agentic-bolierplate checkout.

Read docs/planning/r13-local-backlog-task.md. It is the complete fixed scope.
Do not request private Jira/Figma access or start the unrelated Sprint Overview.
If that document is absent, use this fixed fallback scope without asking:
Story/Bug/Task records have project_id, caller-supplied immutable key, kind,
title, description, acceptance criteria, workflow status, optional sprint label,
prerequisite keys, revision and audit. Required content must be nonempty.
Create starts in FUNNEL at revision 1. Store one JSON file per project/item
under DURABLE_LOCAL_BACKLOG_PATH, default data/local-backlog.
All mutations require expected_revision; serialize check/write across processes,
use atomic replacement and return conflicts for stale/duplicate writes.
Normal edits cannot change identity/status; separate transitions use existing
canonical status/event/actor rules. Reject unsafe resolved paths and missing/
self/cyclic prerequisites. Identical keys in different projects are valid and
must stay isolated. CLI/API share these rules.
No delete, UI, automatic key numbering, migration, JQL or scheduler changes.
Linux/WSL/Docker is the required target; preserve unrelated platform behaviour.

PO AUTHORIZATION FOR THIS THREE-STAGE TASK:
I approve this local implementation and delegate unspecified in-scope decisions.
Do not ask questions, create PO inbox questions or wait for Jira readiness,
remote tickets, design acceptance, model switches or another approval.
Record decisions locally and continue. This waiver applies only to this task:
do not change global policies or weaken the product's own workflow controls.
Use the active model. Missing private credentials, remote systems or historical
platform quota records are not prerequisites for local coding/tests.
Actual permissions/provider limits, secret handling, input validation,
concurrency protection and tests still apply; never fabricate evidence.

Keep all work local. Do not commit, push, create a PR, merge or release.
Preserve unrelated work. Use a non-main task branch where available.
Do not restore the intentionally omitted root AGENTS.md or CLAUDE.md.

This invocation has at most 80 tool actions. Aim for 55-60, reserving the rest
for checks and a durable checkpoint. Do not exhaust the budget on exploration.
Do not pack large unsafe commands merely to game the action count.

Inspect the relevant callers, storage/config patterns and canonical workflow.
Write a concise local design/decision note, then IMPLEMENT the work-item model
and file-backed store with atomic, serialized revision-checked mutations,
project/key isolation, audit and dependency validation.
Keys are caller-supplied and immutable; create starts in FUNNEL. Do not add a
counter, UI, Jira migration, scheduler integration or a new database.
Add and run focused unit tests, including conflict/concurrency, path safety,
missing/self/cyclic prerequisites and persistence. Fix failures now.

Before the stage/action boundary, save data/agent-logs/AGENT-1082/stage-1.md:
changed files, decisions, commands/results, unfinished work, action count and
precise Stage 2 entry point. Keep runtime evidence out of tracked docs.
End with Stage 1's actual results, not a question or a proposal. Stage 2 is
intentionally deferred to my next prompt; do not implement it in this run.
```

## Prompt 2 - CLI, API And Integration

```text
Continue Stage 2 of AGENT-1082 in the same checkout without restarting Stage 1.
Read docs/planning/r13-local-backlog-task.md and the Stage 1 checkpoint, then
inspect the actual files. Recover missing context from code instead of asking.

My task-scoped delegation remains active: make in-scope decisions, record them,
and do not wait for PO questions, Jira tickets, design/model-switch approval or
private credentials. Do not disable tests, security or actual permissions.
No commits, pushes, PRs, merges or releases.

Budget: at most 80 tool actions; target 55-60 plus validation/checkpoint reserve.
Complete necessary Stage 1 fixes, then IMPLEMENT CLI create/get/list/update/
transition operations and matching project-scoped API endpoints through one
service/store. Add DURABLE_LOCAL_BACKLOG_PATH consistently to configuration,
CLI and API bootstrap without making Jira credentials required for this path.
Keep ordinary updates separate from status transitions; reuse canonical rules.
Use existing error conventions: invalid input 400, missing item 404, conflict
409. Rejected mutations must not change data or audit.
Document and wire default/custom durable paths and Docker bind mounts.
Do not introduce UI, JQL parsing, migration or automatic worker pickup.

Run focused CLI/API/config integration tests with temporary synthetic data.
Verify project isolation, no remote adapter calls, revision conflict responses,
invalid transitions, restart-readable state and compatibility of old endpoints.
Fix failures; do not settle for stub endpoints or disabled checks.

Save data/agent-logs/AGENT-1082/stage-2.md with changed files, exact commands/
results, decisions, remaining work, action count and Stage 3 entry point.
Finish at this stage boundary without a question or another plan.
```

## Prompt 3 - Review, Regression, Docker Proof And Handoff

```text
Finish Stage 3 of AGENT-1082 from the current local implementation.
Read the bounded specification and both checkpoints. Do not recreate completed
work or start Sprint Overview. The same PO delegation/no-question exception
remains active, without disabling tests, security or actual permissions.
Keep changes local: no commits, pushes, PRs, merges or releases.

Budget: at most 80 tool actions; reserve the final 15-20 for evidence/handoff.
Review the diff and connected callers, fix correctness/compatibility issues,
then run focused tests and the full existing Python regression suite.
Validate documentation and the affected Docker configuration.
Use existing Docker images/builds where suitable. Start only the operator API
needed for this task, on unused loopback ports, with isolated synthetic data
and durable mounts; do not start agents or disturb existing user containers.
Prove create/read/update through the real API and CLI, recreate the API
container without deleting its durable storage, and read the same item again.
Check custom-root mapping, status/dependency errors and stale-write conflicts.
Do not claim native Windows backend support or live Jira integration unless
actually tested. No browser/UI build is needed: this task has no UI changes.

Complete usage/configuration docs and acceptance-criteria evidence.
Save data/agent-logs/AGENT-1082/stage-3.md with actual commands/results and
remaining limitations. Report changed files, a local diff/patch, decisions,
AC coverage, tested startup commands and how to stop only test containers.
Stop your temporary containers without deleting user data.

If a genuine environment/tool restriction prevents a check, try a safe
alternative, finish every unaffected part and clearly report the missing
verification; do not ask me a question, bypass access controls or invent a pass.
If the action limit approaches, checkpoint immediately and honestly mark any
unfinished work. Never label incomplete work as complete to satisfy the budget.
End with implementation and evidence, not a request to approve another step.
```

## Interpretation

The no-question exception is Product Owner delegation of task decisions, not a
capability to override operating-system permissions or provider quotas.
Planning estimates cannot guarantee completion in a third-party tool's exact
action/time budget. A partial result must stay explicitly partial.

