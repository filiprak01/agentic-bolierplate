# UI Design Gate

Status: Release 1.2 implementation baseline for `AGENT-668`.

The UI Design Gate prevents frontend implementation from starting before the
Product Owner has accepted the intended visual and interaction design.

The machine-checkable policy lives in
`src/agentic_boilerplate/domain/ui_design_gate.py`.

## Applies To

The gate applies to any story that changes:

1. User-facing screens or routes.
2. Navigation, menus, dashboards, panels, forms, tables, charts, or timelines.
3. User-visible copy hierarchy or interaction behavior.
4. Accessibility, responsive layout, or visual state behavior.
5. Operator UI screens for PO inbox, limits, agent status, communication, or
   logs.

Backend-only, documentation-only, and non-UI infrastructure stories do not need
the gate unless they change user-facing behavior.

## Required Story Pairing

Product Planning must create or reference a design story before the frontend
implementation story starts.

The design story must block the implementation story with a Jira `Blocks` link.
The implementation story remains assignment-blocked until the design story is in
an accepted design state or has an explicit Product Owner override.

Use these labels when possible:

1. `design-reference-required` on the implementation story.
2. `po-design-acceptance-gate` on both design and implementation stories.
3. `design-gate` on the design story.

## Design Reference Section

Every UI implementation story must include:

```text
Design Reference:
- Design story: <JIRA_KEY>
- Artifact: <Figma link, Canva link, exported snapshot, or local HTML mockup path>
- Product Owner acceptance: <Jira comment, PO inbox item, or override reference>
- Constraints: <responsive, accessibility, component, copy, and interaction notes>
```

## Accepted Design States

A design reference is accepted when one of these is true:

1. The design story is `TEST COMPLETED` or `ACCEPTED/DONE` and includes the
   artifact reference.
2. The Product Owner records an explicit override in Jira or PO inbox.

`DEV COMPLETED` is not enough for frontend implementation because it means the
design artifact was prepared but not accepted. DEV COMPLETED is not enough
without Product Owner acceptance or an explicit Product Owner override.

## Agent Responsibilities

Product Planning:

1. Detect UI-facing scope.
2. Create or reference the design story.
3. Add the `Design Reference` placeholder to the implementation story.
4. Create the Jira `Blocks` dependency from design story to implementation
   story.

UI/UX:

1. Produce reviewable design artifacts.
2. Record responsive, accessibility, interaction, and copy constraints.
3. Ask PO inbox questions when design decisions are missing.
4. Leave a complete handoff for frontend implementation.

Frontend:

1. Read the `Design Reference` before editing UI code.
2. Stop if the design story, artifact, PO acceptance, or dependency link is
   missing.
3. Implement against the accepted design rather than inventing UI behavior.

Scheduler/Orchestrator:

1. Treat missing accepted design references as Definition-of-Ready blockers.
2. Prefer another eligible story from the same approved sprint when a UI story
   is blocked by design.
3. Create a PO inbox blocker when no eligible replacement exists.

## Operator UI Requirement

Operator UI stories must show their design reference in Jira and evidence so the
Product Owner can trace what was accepted before implementation.
