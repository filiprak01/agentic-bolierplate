# Codex Limits Form Design

Jira story: `AGENT-670`

Implementation reference: `AGENT-664`

Selected option: Option A - Adaptive Limit Windows With Atomic Save Panel

## Purpose

The Product Owner needs a compact local Operator UI view for reading current
Codex capacity and recording updated limit observations without using CLI flags.
The design must support both current single-pool Pro behavior and older
multi-window short and broad quota models.

## Target User

The primary user is the Product Owner operating local session-mode or worker
flows. The user wants to decide whether the next story can start, whether work
should pause under a low-limit threshold, and when paused work may resume.

## Screen Route

Route: `Limits`

Navigation source: AGENT-665 operator hamburger shell.

The route replaces the current placeholder content for limits. It uses the same
header and project identity context as the rest of the Operator UI.

## Selected Layout

Option A uses one screen with two stable regions:

1. Limit summary strip for current status and available windows.
2. Atomic update panel for entering a complete new observation.

The summary strip shows each detected quota window as a compact status tile.
For Pro single-pool plans, the strip shows one tile named `Current plan`. For
multi-window plans, it shows separate `Short window` and `Broad window` tiles.

The atomic update panel always saves a full coherent record. It does not allow
partial updates that would mix old percentages with new reset dates.

## One-Window Example

Use this state when the Codex account exposes one combined subscription limit:

```text
Current plan
Available
Used 18 percent
Remaining 82 percent
Resets Aug 11, 2026 04:00
```

The form displays one editable row:

```text
Window name: Current plan
Status: Available
Used percent: 18
Reset at: 2026-08-11 04:00
Cutoff percent: 90
```

## Multi-Window Example

Use this state when the account exposes separate short and broad quota windows:

```text
Short window
Low limit
Used 91 percent
Remaining 9 percent
Resets Aug 10, 2026 16:00

Broad window
Available
Used 42 percent
Remaining 58 percent
Resets Aug 17, 2026 16:00
```

The form displays one editable row per window. The save action writes every
visible row in one request.

## Atomic Update Controls

Required controls:

1. Status selector: `available`, `limited`, `unknown`.
2. Used percentage numeric input from 0 to 100.
3. Reset datetime input using local time.
4. Cutoff percentage numeric input from 1 to 100.
5. Optional operator note for context such as `Pro plan now uses one window`.
6. Single primary action: `Save limit record`.

Required save behavior:

1. Disable save until every visible row has valid values.
2. Show a preview of the record that will be saved.
3. Save all rows atomically.
4. After success, refresh the summary from durable API state.
5. On API failure, keep the typed values and show a recoverable error.

## Required States

The implementation story must cover these states:

1. Loading: summary skeleton with disabled form.
2. Empty: no record found and a guided empty form.
3. Available: safe to start the next task.
4. Low limit: below cutoff, warn before starting new work.
5. Limit reached: block new work until reset or Product Owner override.
6. Stale record: record age exceeds configured freshness threshold.
7. Unknown window: provider returned a shape the system does not recognize.
8. Validation error: percentage or reset datetime is invalid.
9. Save success: saved time and record id are visible.
10. Save failure: safe error message without secrets or local paths.

## Privacy And Data Boundary

The UI must never show:

1. API keys, GitHub tokens, Jira tokens, OpenAI keys, cookies, or authorization
   headers.
2. Raw `.env` content.
3. Absolute host paths such as `/home/...` or `C:\...`.
4. Codex session artifacts or account identifiers beyond safe plan/window
   labels.

The UI may show:

1. Window labels.
2. Used and remaining percentages.
3. Reset timestamps.
4. Safe status labels.
5. Durable record id.
6. Project id and Jira key.

## Accessibility

1. Status tiles must not rely on color alone.
2. Inputs need visible labels.
3. Validation messages must be associated with the relevant field.
4. The save button must be reachable by keyboard.
5. The summary must fit without horizontal scrolling at 360 px width.

## PO Acceptance Note

The Product Owner explicitly allowed this sprint to continue without waiting on
per-story visual approval. For AGENT-670, this design is accepted by sprint
execution override and can be used by AGENT-664 as its `Design Reference`.

## Design Reference

Frontend implementation stories must copy this reference:

```text
Design Reference:
- Design story: AGENT-670
- Design document: docs/design/codex-limits-form-design.md
- Design artifact: docs/design/codex-limits-form-options.html
- Selected option: Option A - Adaptive Limit Windows With Atomic Save Panel
- Acceptance: Product Owner sprint execution override recorded in AGENT-670
```
