# Session-Mode Planning Handoff Validation

Status: Release 1.1 validation baseline for `AGENT-443`

This guide validates the supervised handoff from Architecture and Product
Planning sessions into development-ready Jira work. It proves that early
planning can be reviewed without code implementation and that Codex session
findings become durable artifacts before development starts.

Use this guide with `docs/session-mode-validation-playbook.md`.

## Scenario Boundary

The validation covers:

1. Architecture discovers an unclear requirement or NFR.
2. Architecture creates a PO inbox `blocking_question` in the configured
   platform inbox, not in the target project checkout.
3. Product Planning uses approved requirements and PO inbox answers to create a
   local backlog draft.
4. The Product Owner reviews the draft before Jira issue creation.
5. Product Planning creates Jira-ready draft or Jira issues only after approval.
6. A context pack is prepared only after Jira work is approved, dependencies
   are satisfied, and the issue is `READY TO START`.

The validation does not require code implementation. Draft review happens from
durable planning artifacts, Jira descriptions, documentation references, and
context-pack previews.

## Required Inputs

1. Platform repository path.
2. Target project path.
3. Jira planning or validation issue key.
4. Approved product requirement or architecture note.
5. Durable PO inbox root from `DURABLE_PO_INBOX_PATH`.
6. Backlog draft root from the configured durable data directory.
7. Context pack root from the configured durable data directory.

Stop if any path points under the wrong project boundary. PO inbox, backlog
drafts, and context packs are platform-owned durable artifacts. Target project
directories contain target project code and project-specific product docs.

## Architecture Validation

Startup prompt: `## Architecture` in `ai_agents/session_starters/README.md`.

The Architecture session passes when it:

1. Loads `AGENTS.md` and `ai_agents/roles/architecture.md`.
2. Checks Codex limits before analysis.
3. Identifies at least one concrete decision that would affect scope, NFRs,
   dependencies, data, security, cost, or deployment.
4. Creates a PO inbox `blocking_question` through the CLI, API, or store
   abstraction.
5. References the related Jira planning issue or context pack path when
   available.
6. Stops instead of inventing the missing decision.

Expected PO inbox command shape:

```bash
agentic po-inbox create \
  --id architecture-question-<timestamp> \
  --type blocking_question \
  --title "Clarify architecture decision" \
  --message "Describe the missing NFR or architecture decision." \
  --business-impact "Explain which stories or architecture outputs can change." \
  --recommendation "State the recommended Product Owner choice."
```

## Product Planning Validation

Startup prompt: `## Product Planning` in
`ai_agents/session_starters/README.md`.

The Product Planning session passes when it:

1. Loads `AGENTS.md` and `ai_agents/roles/product_planning.md`.
2. Uses approved requirements, Architecture outputs, and answered PO inbox
   decisions only.
3. Creates a reviewable backlog draft with epics, stories, acceptance criteria,
   dependencies, complexity metadata, and missing decisions.
4. Keeps the draft local and reviewable before Jira creation.
5. Marks missing business choices as PO inbox questions instead of generating
   executable work.

Reviewable draft content must include enough context for the Product Owner to
decide whether the story belongs in `FUNNEL`, needs rework, or should be
discarded.

## PO Approval Gate

The approval gate is before Jira story creation.

1. Product Planning creates or updates local backlog drafts.
2. Product Owner reviews the draft and answers open PO inbox items.
3. Product Owner approval metadata is recorded with actor and timestamp.
4. Jira creation planning starts only from approved drafts.
5. Jira issues start in `FUNNEL`.
6. Development starts only after the Product Owner moves Jira work to
   `READY TO START`.

This gate lets drafts be reviewed without code changes, branches, pull
requests, or developer subtasks.

## Context Pack Preparation

Context packs are prepared after Jira approval and before agent execution.

Use `docs/context-pack-generator.md` to verify:

1. Issue key, summary, status, sprint, and branch metadata exist.
2. Acceptance criteria are present.
3. Documentation references are approved.
4. Dependencies are satisfied.
5. Model/reasoning routing is explicit.
6. Manual switch prompt exists when required.
7. No open PO inbox questions remain.

If context is missing, create a PO inbox question and stop. Do not let a
Developer Agent start from incomplete context.

## Findings Record

Record findings in durable evidence under
`data/agent-logs/<JIRA_ISSUE>/planning-handoff-validation-<timestamp>.md`.

The evidence must list:

1. Architecture PO inbox question path or `not required`.
2. Backlog draft path or Jira-ready draft path.
3. PO approval status.
4. Jira creation status.
5. Context pack path or reason it was not generated.
6. Any missing behavior that should become a backlog story in `FUNNEL`.

Findings that improve future Docker or detached-worker behavior should also
reference `docs/docker-worker-requirements.md` or
`docs/docker-worker-triggering.md`.
