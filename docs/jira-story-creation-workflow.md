# Product Planning Jira Story Creation Workflow

The Product Planning Jira story creation workflow turns Product Owner-approved
local backlog drafts into Jira issues.

The workflow preserves lineage from draft ids to Jira issue keys, creates
dependency links, and saves creation results locally for resume and audit.

## Inputs

The workflow requires:

1. Approved backlog draft.
2. Product Owner approval actor.
3. Product Owner approval timestamp.
4. Configured Jira project adapter.
5. Sprint label.
6. Sprint ring label.
7. Release label.
8. UI design gate classification for UI-facing requirements.

Drafts must be approved before Jira creation planning. Missing approval
metadata is rejected.
The session-mode validation path for this approval gate is documented in
`docs/session-mode-planning-handoff-validation.md`.

Before Jira issues are created, Product Planning must create a durable PO inbox
approval request with:

```bash
agentic backlog-draft request-approval \
  --draft-path data/backlog-drafts/{DRAFT_KEY}.json \
  --jira-issue-key {PLANNING_STORY} \
  --project-id {PROJECT_ID}
```

Jira creation is blocked until the approval gate returns `can_create_jira=true`:

```bash
agentic backlog-draft approval-gate \
  --draft-path data/backlog-drafts/{DRAFT_KEY}.json \
  --approval-item-id {DRAFT_KEY}-jira-creation-approval
```

Rejected or unanswered approval requests must not create Jira issues. Rejected
drafts should be regenerated or revised, then submitted as a new approval
request for the Product Owner to review.

Product Planning must also run
`docs/documentation-to-backlog-traceability-audit.md` before final Jira
creation. The approval request must show the traceability report path and
summary. Any `missing-jira-reflection` or `needs-po-decision` rows must be
created as draft backlog candidates, converted into PO inbox decisions, marked
doc-only, deferred, or rejected before issue creation proceeds.

## Creation Plan

The creation plan contains:

1. Jira issue plans for draft epics and stories.
2. Expected initial status from Jira configuration, normally `FUNNEL`.
3. Draft id lineage.
4. Parent draft id lineage for stories under epics.
5. Sprint, sprint ring, release, complexity, model, reasoning, and speed
   labels.
6. Acceptance criteria and dependency details in descriptions.
7. Blocks link plans for prerequisite stories.
8. `Design Reference` placeholders for UI implementation stories.
9. `Expected Repositories` for stories that may touch target, boilerplate,
   documentation, or automation repositories.
10. Sprint proposal and generated context-pack references in every story
    description.

The plan is local and reviewable before adapter execution.

## Execution

Execution uses the configured Jira adapter.

The workflow:

1. Creates parent epic issues first.
2. Creates child story issues with resolved parent Jira keys.
3. Records draft id to Jira key mappings.
4. Creates Blocks links from prerequisite stories to dependent stories.
5. Records created dependency links.

New Jira issues are expected to start in the configured default status,
normally `FUNNEL`.

## Durable Results

`FileJiraCreationResultStore` saves creation results as local JSON.

The result includes:

1. Draft key.
2. Project key.
3. Creation timestamp.
4. Created issue mappings.
5. Expected and actual initial statuses.
6. Parent Jira keys.
7. Created Blocks links.

Workers use the saved result to resume safely and avoid losing Jira lineage
after a container stop or Codex limit pause.

## Agent Behavior

Product Planning Agent should:

1. Create Jira issues only from Product Owner-approved drafts.
2. Preserve lineage and complexity metadata.
3. Create dependency links after all required issues exist.
4. Copy sprint proposal and context-pack references into each generated story
   description so later workers receive the right AI context.
5. Save creation results immediately after execution.

Scheduler should:

1. Use dependency links to avoid assigning blocked stories.
2. Treat missing creation results as an audit risk.

Product Owner should:

1. Review generated Jira stories in `FUNNEL`.
2. Move approved stories to `READY TO START`.

## UI Story Pairing

For UI-facing scope, Product Planning must create or reference a design story
before creating the frontend implementation story. The design story must block
the implementation story with a Jira `Blocks` link.

The frontend implementation story must include:

1. Design story key.
2. Artifact link or path.
3. Product Owner acceptance or override reference.
4. Responsive, accessibility, component, copy, and interaction constraints.

If the accepted design reference is not known during story creation, keep the
implementation story blocked and create a PO inbox question rather than
inventing the design. The canonical gate is documented in
`docs/ui-design-gate.md`.

## Multi-Repo Traceability

For any story that may touch more than one repository, Product Planning must add
the `Expected Repositories` section documented in
`docs/multi-repo-jira-github-traceability.md`.

The section must distinguish target implementation, boilerplate/process,
documentation, and automation repository lanes. If the boilerplate/process
repository is touched because of a target-project story, the description must
state why that process change belongs to the project story. If Jira development
panel visibility is not expected for a configured lane, the story must require a
manual Jira PR link comment.
