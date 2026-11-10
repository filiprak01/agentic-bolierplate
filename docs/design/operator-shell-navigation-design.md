# Operator Shell Navigation Design

Jira: AGENT-669
Status: Accepted for implementation by PO sprint-level override on 2026-08-10
Selected option: Option B - Compact Header With Hamburger Drawer
Implementation reference: AGENT-665
Artifact: `docs/design/operator-shell-navigation-options.html`

## Design Goals

The operator UI must stop behaving like one long dashboard as Release 1.2 adds
PO inbox, Codex limits, worker status, logs, multi-project views, and agent
communication. The Product Owner needs a compact console that keeps blocking
work visible while leaving the main area for reading and answering.

## Primary Sections

1. PO Inbox
2. Codex Limits
3. Workers
4. Logs
5. Projects
6. Agent Communication
7. Settings

The first Release 1.2 implementation may keep unavailable sections as disabled
or empty states, but they must be represented in the navigation model so later
stories plug into the same shell.

## Option A - Persistent Rail With Collapsible Labels

Desktop layout keeps a narrow left rail visible at all times. The hamburger
button expands labels and secondary actions. The active project sits in the top
bar. This is efficient for frequent navigation but keeps a permanent visual
column on the screen.

Strengths:

1. Fast repeated switching.
2. Strong active-section orientation.
3. Works well on wide desktop screens.

Tradeoffs:

1. Consumes horizontal space.
2. Still feels close to the existing sidebar pattern.
3. Narrow screens need a separate drawer behavior.

## Option B - Compact Header With Hamburger Drawer

Desktop and narrow screens share a compact top header. The hamburger opens a
navigation drawer with primary sections, section status counters, and secondary
actions. The main content area shows one active section at a time.

Strengths:

1. Gives the inbox and detail views more vertical reading space.
2. Keeps current project, active section, blockers, and limit warnings visible
   above the content.
3. Scales naturally to multi-project navigation and future role dashboards.
4. Uses the same interaction model on desktop and narrower screens.

Tradeoffs:

1. One extra click to switch sections when the drawer is closed.
2. Requires clear active-section text in the header.

Decision:

Use Option B for AGENT-665. It directly addresses the Product Owner pain point
that the current UI requires too much scrolling and gives the future
multi-project inbox a cleaner home.

## Shell Anatomy

Top header:

1. Hamburger menu button.
2. Product name: Agentic Console.
3. Active section label.
4. Active project selector or project chip.
5. Critical status strip for blockers, Codex limit state, and API connection.

Navigation drawer:

1. Primary section buttons with icons.
2. Optional counters such as open inbox items, blocked workers, stale locks.
3. Disabled future sections shown only when they clarify roadmap placement.
4. Settings at the bottom.

Content area:

1. One active section at a time.
2. Section-level action bar near the top.
3. Detail panes or split views inside the section when useful.
4. Empty, loading, disconnected, and error states remain in-section.

Contextual actions:

1. PO Inbox: answer, approve, reject, resolve, export, refresh.
2. Codex Limits: record/update, refresh from sentinel, set threshold.
3. Workers: pause, resume, release stale lock, open logs.
4. Logs: filter, copy reference, export.
5. Projects: switch active project, inspect config.

## Accessibility And Responsive Notes

1. Hamburger button must have an accessible label and keyboard focus state.
2. Drawer must close with Escape and focus should return to the trigger.
3. Active section must be text-visible, not color-only.
4. Critical blockers and limit warnings must stay above the content fold.
5. Buttons use icons with labels or tooltips when the icon alone is unclear.
6. On narrow screens, the drawer overlays content and closes after selection.

## Design Reference For AGENT-665

AGENT-665 must reference this design and the HTML artifact in its Jira
description or implementation comment:

```text
Design Reference:
- AGENT-669
- docs/design/operator-shell-navigation-design.md
- docs/design/operator-shell-navigation-options.html
- Selected: Option B - Compact Header With Hamburger Drawer
```

PO acceptance note:

The Product Owner instructed the agent to continue sprint implementation
without stopping for additional model/reasoning or generic approval gates. For
this design story, that instruction is recorded as a sprint-level acceptance
override so AGENT-665 can proceed with the selected shell design.

Jira propagation:

The Design Reference must be copied to AGENT-665 before implementation starts.
The implementation story should not replace the selected option unless a later
Product Owner comment explicitly changes the design direction.
