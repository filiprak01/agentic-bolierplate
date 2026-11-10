# Compact PO Inbox UX Design

Jira: AGENT-667
Status: Accepted for implementation by PO sprint-level override on 2026-08-10
Selected option: Option A - Compact Split Pane With Sticky Action Dock
Implementation references: AGENT-637, AGENT-672, AGENT-664, AGENT-638
Artifact: `docs/design/compact-po-inbox-ux-options.html`

## Design Goals

The PO Inbox must be fast to scan and answer during agent-driven delivery. The
Product Owner should not need to scroll through a long page to read the message,
see project identity, understand impact, and answer, approve, reject, resolve,
or export.

The design builds on the AGENT-669 / AGENT-665 operator shell:

1. Use the compact header and hamburger drawer as the outer shell.
2. Keep PO Inbox as the default active section.
3. Keep project identity, failed API states, and critical blockers visible above
   the inbox content.
4. Show one selected inbox item at a time in a dense detail pane.
5. Keep action controls near the detail content.
6. Support one active project now and multi-project filters later.

## Option A - Compact Split Pane With Sticky Action Dock

Desktop layout:

1. Header row with All Projects selector, status filters, search, refresh, and
   export.
2. Left queue pane with compact inbox rows.
3. Right detail pane with message, recommendation, impact, options, audit, and
   a sticky action dock.
4. Project label and agent role are visible in both list row and detail header.
5. Long message content scrolls inside the detail body, while actions stay
   reachable.

Strengths:

1. Best for fast PO answering and approvals.
2. Keeps action buttons visible without pushing them below long text.
3. Scales to many items because the queue is independent from the detail body.
4. Works naturally with multi-project filters and per-project errors.

Tradeoffs:

1. Requires careful responsive behavior below tablet width.
2. Needs truncation rules for dense queue rows.

Decision:

Use Option A for implementation. It directly solves the scrolling problem and
supports AGENT-637 multi-project aggregation plus AGENT-672 JSON export.

## Option B - Queue First With Drawer Detail

Desktop layout:

1. Full-width queue table with filters and project chips.
2. Selecting an item opens a right-side detail drawer.
3. Action dock is sticky inside the drawer.
4. The queue remains readable when the drawer is closed.

Strengths:

1. Gives maximum width to the queue.
2. Useful when the operator is triaging many low-detail items.
3. Similar drawer behavior to the shell navigation model.

Tradeoffs:

1. Adds an extra interaction for every answer.
2. Long messages still compete with drawer width.
3. Less efficient for PO review sessions where each item needs a decision.

## Required States

The implementation stories must represent these states:

1. Loading: skeleton rows and disabled action dock.
2. Empty: no open inbox items, with project filter still visible.
3. Failed API: safe error banner that does not expose paths or secrets.
4. Per-project error: one project can fail without hiding other projects.
5. Long message: detail body scrolls independently, action dock remains visible.
6. Many items: queue pane scrolls independently.
7. Answered/approved/rejected/resolved: terminal state row label and disabled
   invalid actions.
8. Multi-project view: All Projects selector, project chips, and item project
   labels.
9. Active project view: same controls, scoped to a single project.

## Action Dock

Action controls stay near the selected item:

1. Answer
2. Approve
3. Reject
4. Resolve
5. Export selected item
6. Refresh

Actions must remain disabled when the item status or message type does not
allow that transition. Disabled states must show safe operator text.

## Implementation References

AGENT-637 must reference this design when it implements multi-project inbox
aggregation and filters.

AGENT-672 must reference this design when it implements project-scoped JSON
export.

AGENT-664 and AGENT-638 should reuse the same compact toolbar and sticky action
patterns where they expose limits and worker actions.

Design Reference:

```text
Design Reference:
- AGENT-667
- docs/design/compact-po-inbox-ux-design.md
- docs/design/compact-po-inbox-ux-options.html
- Selected: Option A - Compact Split Pane With Sticky Action Dock
```

## PO Acceptance Note

The Product Owner instructed the sprint agent to continue implementation without
stopping for generic approval gates. For this design story, that instruction is
recorded as sprint-level acceptance for the selected direction so dependent
stories can proceed. Final release acceptance remains the Product Owner gate.
