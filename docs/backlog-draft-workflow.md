# Product Planning Backlog Draft Workflow

The Product Planning Agent creates local backlog drafts before Jira stories are
created for Product Owner review.

The workflow is intentionally local-first. Drafts are durable JSON artifacts so
work can resume after a container stop, Codex limit pause, or network failure.

## Requirement Input

Backlog drafts start from structured requirement input.

The input includes:

1. Requirement key.
2. Title.
3. Overview.
4. Epics.
5. Stories.
6. Acceptance criteria.
7. Prerequisite story ids.
8. Complexity level and rationale.
9. Sprint rings.
10. Missing business decisions.

The Product Planning Agent must not invent missing business choices. Missing
decisions become Product Owner questions.

## Draft Output

Generated drafts include:

1. Epic drafts.
2. Story drafts.
3. Acceptance criterion ids and descriptions.
4. Dependency drafts using prerequisite and dependent story ids.
5. Complexity routing metadata from the shared story complexity model.
6. Sprint rings that group stories by delivery scope.
7. Missing business decisions for PO review.

Drafts are not Jira issues yet. They are reviewable local artifacts that can
later feed the Jira story creation workflow after Product Owner approval.
Session-mode validation for this handoff is described in
`docs/session-mode-planning-handoff-validation.md`.

## CLI Generation

Generate or regenerate a durable draft from approved structured source JSON:

```bash
agentic backlog-draft generate \
  --input approved-backlog-source.json \
  --backlog-draft-root data/backlog-drafts \
  --project-id ap \
  --jira-issue-key AGENT-640
```

The command saves one JSON draft per draft key. It uses `save`, not Jira
creation, so repeated runs update the same local artifact and do not duplicate
Jira issues. Missing business decisions create stable PO inbox blockers; reruns
reuse the same blocker ids.

Source JSON is produced by the Product Planning Agent after reading approved PO
docs, architecture notes, NFRs, roadmap, and constraints. Required fields:

1. `key`, `title`, and `overview`.
2. `epics[].id`, `title`, `description`, and `stories`.
3. `stories[].id`, `title`, `description`, `acceptance_criteria`,
   `prerequisite_story_ids`, `complexity`, and `complexity_rationale`.
4. `sprint_rings[].id`, `name`, `goal`, and `story_ids`.
5. `missing_business_decisions[]` when contradictions or missing requirements
   can change scope, dependencies, acceptance criteria, priority, or sprint
   slicing.

Sprint rings must reference story ids that exist in the generated draft. This
keeps release slicing deterministic before Jira issue creation.

Before finalizing the draft for Product Owner approval, Product Planning must
run the documentation-to-backlog traceability audit described in
`docs/documentation-to-backlog-traceability-audit.md`. The draft may proceed
only when missing implementation-worthy commitments are either included as
draft stories, routed to PO inbox questions, marked doc-only, deferred, or
rejected with an explicit reason.

## PO Approval Before Jira Creation

After draft review, Product Planning asks the Product Owner to approve Jira
creation through the durable PO inbox:

```bash
agentic backlog-draft request-approval \
  --draft-path data/backlog-drafts/{DRAFT_KEY}.json \
  --jira-issue-key {PLANNING_STORY} \
  --project-id {PROJECT_ID}
```

Workers must check the approval gate before creating Jira issues:

```bash
agentic backlog-draft approval-gate \
  --draft-path data/backlog-drafts/{DRAFT_KEY}.json \
  --approval-item-id {DRAFT_KEY}-jira-creation-approval
```

`approved` allows Jira creation in `FUNNEL`. `waiting`, `missing`, and
`rejected` block Jira creation. Rejected items remain durable evidence that the
draft cannot be silently promoted.

The approval request should include or reference the latest traceability report
summary so the Product Owner can see covered, doc-only, deferred, rejected,
duplicate, PO-needed, and missing-Jira rows before approving Jira creation.

## Missing Business Decisions

Each missing business decision creates a PO inbox `blocking_question`.

The question includes:

1. Backlog draft title.
2. Affected draft story ids.
3. Business impact.
4. Recommendation.
5. Suggested Product Owner actions.
6. Optional Jira issue key for the planning story.
7. Optional context pack path.

Implementation and Jira story creation must wait when the missing decision
can change scope, acceptance criteria, dependencies, sprint slicing, or
priority.

## Durable Storage

`FileBacklogDraftStore` stores one JSON file per draft.

Supported operations:

1. `create`
2. `save`
3. `read`
4. `list_drafts`

Draft keys are restricted to path-safe characters so storage paths are
deterministic and safe for local worker volumes.

## Agent Behavior

Product Planning Agent should:

1. Convert structured requirements into local backlog drafts.
2. Preserve acceptance criteria and dependencies.
3. Apply shared complexity routing metadata.
4. Create PO inbox questions for missing business decisions.
5. Persist drafts before attempting Jira story creation.

Architecture Agent should:

1. Review draft dependencies and NFR-sensitive stories when needed.
2. Add missing NFR questions before risky implementation starts.

Developer Agent should:

1. Work only from Jira stories approved by the Product Owner.
2. Use draft metadata only after it has been promoted into approved Jira
   stories.

Release Manager should:

1. Use draft complexity and dependencies as planning input.
2. Keep sprint slicing scope-first and use complexity as limit-pressure
   metadata.
