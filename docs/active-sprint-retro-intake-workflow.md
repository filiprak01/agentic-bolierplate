# Active Sprint Retro Intake Workflow

This workflow gives each active sprint one visible retro intake item before
closure starts. It prevents retro input from being scattered across closure
tasks, chat, or local notes.

## Creation Timing

Create one board-visible retro intake Task during sprint setup, add it to the
active sprint before the first delivery item starts, and keep it open until
every participating role has submitted or explicitly skipped retro input.

The retro intake Task is separate from sprint closure publication. Delivery
stories may block the retro intake item so the Release Manager can tell which
roles participated before routing follow-up work.

## Comment Template

Each participating agent submits one Jira comment on the active sprint retro
item using this structure:

```text
## Retro Input - <agent-role>

### Airlines Project Element

Problematic elements:
- ...

Suggestions:
- ...

### Agent/Process Element

Problematic elements:
- ...

Suggestions:
- ...
```

The airlines-project element is for product, release, target-project,
acceptance, data, or operator-facing issues. The agent/process element is for
workflow, role routing, tool, evidence, board, or handoff issues.

## PO Approval Rule

For each submitted retro comment, Release Manager creates a PO inbox
`approval_request` linked to the active sprint retro issue before treating the
comment as accepted retro input.

Approved comments can be routed into closure notes, Confluence summaries,
existing Jira stories, or new `FUNNEL` follow-up candidates. Rejected comments
remain visible on Jira but must not create scope, workflow changes, or backlog
items unless the Product Owner later approves them.

If a comment is missing either required element, Release Manager asks the
participant to resubmit or creates a PO inbox clarification instead of routing
the comment silently.

## Follow-Up Routing

After PO approval, Release Manager classifies each retro finding:

1. Existing Jira story or task.
2. New backlog story in `FUNNEL` with `po-review-required`.
3. Documentation update under the current sprint support task.
4. Deferred roadmap note.
5. Rejected or no-action.

Implementation changes, automation, scripts, tests, configuration, and product
behavior changes require their own Jira story before any code work starts.

## Evidence

The retro intake item should receive:

1. The final participant list.
2. Links or IDs for PO approval inbox items.
3. Approved/rejected status per submitted comment.
4. Follow-up Jira keys or no-action notes.
5. Durable local evidence paths when used for sprint closure.
