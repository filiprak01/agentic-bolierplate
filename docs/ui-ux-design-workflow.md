# UI/UX Design Workflow

## Purpose

UI/UX work must create inspectable design context before Frontend Agent
implementation starts. This keeps frontend stories from inventing screens,
copy, accessibility behavior, or interaction rules during implementation.

## Required Artifacts

Before frontend work starts, the UI/UX Agent should provide:

1. Target user and primary workflow summary.
2. Screen or route list.
3. User flow or interaction notes.
4. Layout, responsive, and accessibility expectations.
5. Copy or copy-decision placeholders.
6. Component, state, and validation notes.
7. Design handoff reference, such as a Figma link, exported frames, or local
   screenshots.
8. Known open Product Owner questions.

Frontend stories can reference these artifacts by path or link without requiring paid Figma API usage.

## Product Owner-Accepted Design Gate

Every UI-facing implementation story must have a paired design story or an
explicitly reused accepted design reference. The design story blocks the
implementation story through Jira `Blocks`.

Implementation starts only after the design story is accepted by the Product
Owner or the Product Owner records an explicit override. The implementation
story must include the `Design Reference` section described in
`docs/ui-design-gate.md`.

## Figma Preference

Figma is the preferred UI/UX design and handoff tool when a project needs
inspectable UI artifacts.

Preferred handoff:

1. Figma file or page link.
2. Frame names matching story, epic, or screen names.
3. Exported PNG/PDF snapshots saved in the target project's documentation area
   when direct Figma access is not guaranteed.
4. Notes for responsive breakpoints, accessibility, and component reuse.

## Release 1.1 Baseline

Release 1.1 uses a manual Figma link/export workflow by default.

Automated Figma API or plugin integration must not be assumed. Before committing
to automation, the UI/UX Agent must confirm with the Product Owner:

1. Figma workspace access.
2. API or plugin availability.
3. Cost or paid-plan impact.
4. Permission model for agents or service accounts.
5. Whether generated assets can be stored in the target project repository.

If any of those are unknown, use manual links/exports and create a PO inbox
question instead of implementing automation.

## Frontend Handoff

Frontend stories should include one of:

1. Figma link plus frame names.
2. Local exported design path.
3. Approved design note path.

The Product Planning or UI/UX Agent must copy the accepted design handoff into
the story context pack as `design_references`. Each reference should identify
the source type, URL when available, frame or screen name, optional exported
artifact path, short description, and whether it is required for execution.

The Frontend Agent may start only when the story acceptance criteria identify
the expected UI behavior or the UI/UX artifacts answer it.

The Frontend Agent must stop when the accepted design reference, design artifact,
Product Owner acceptance, or blocking design dependency is missing.

## PO Inbox Questions

The UI/UX Agent must create PO inbox questions for:

1. Missing target user or primary workflow.
2. Unclear brand, visual direction, copy, or accessibility target.
3. Missing Figma access or unclear paid-tool cost.
4. Automation requests that require API/plugin permissions.
5. Conflicting design and product requirements.
6. Any frontend behavior that would otherwise be invented.
