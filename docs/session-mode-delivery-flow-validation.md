# Session-Mode Delivery Flow Validation

Status: Release 1.1 validation baseline for `AGENT-444`

This guide validates the supervised delivery flow from an approved Jira story
through Developer, Review, Tester, and Release Manager sessions. It is used
after planning handoff validation confirms that stories, dependencies, and
context packs are ready for execution.

Use this guide with:

1. `docs/session-mode-validation-playbook.md`
2. `docs/session-mode-planning-handoff-validation.md`
3. `docs/developer-subtask-workflow.md`
4. `docs/review-agent-pr-workflow.md`
5. `docs/tester-manual-test-workflow.md`
6. `docs/tester-bug-retest-workflow.md`
7. `docs/sprint-regression-overview-workflow.md`
8. `docs/sprint-closure-publication-workflow.md`
9. `docs/devsecops-preflight-checklist.md`

## Delivery Scenario

The validation covers one Jira Story or Bug that is already approved by the
Product Owner.

1. The issue is in `READY TO START`.
2. Dependency links are satisfied.
3. Durable Codex limits allow work.
4. A context pack or equivalent approved documentation references exist.
5. DevSecOps preflight is complete when the story touches auth/session ownership,
   upload/file-processing, persistence, secrets, deployment, provider review,
   logs, exports, backups, or cleanup.
6. Developer creates subtasks and a feature branch.
7. Review inspects the pull request diff before merge.
8. Tester tests only after merge to `main`.
9. Release Manager prepares regression and closure artifacts after tested scope
   is complete.

## DevSecOps Preflight Validation

Use `docs/devsecops-preflight-checklist.md` before implementation starts when
the story touches sensitive data handling, authentication or authorization,
session ownership, upload/file-processing, persistence, secrets, deployment,
provider review, logs, exports, backups, or cleanup.

The preflight passes when it:

1. Confirms the Jira story is `READY TO START`, dependencies are eligible, and
   durable Codex limits allow the selected route.
2. Confirms the story has context pack or approved documentation references.
3. Records whether Security routing is required for threat modeling,
   authorization design, credential architecture, production access,
   compliance, or residual-risk analysis.
4. Preserves synthetic/redacted-data-only, no permanent original document storage,
   no document-content logging, and no full-filename logging constraints until
   the Product Owner explicitly approves a change.
5. Creates PO inbox questions for missing data sensitivity, retention,
   deletion, provider, deployment, compliance, or risk-acceptance decisions.

Stop when the preflight finds an unresolved Product Owner decision or a required
manual model/reasoning switch. Do not let a Developer session infer security,
privacy, cost, or production-access decisions from implementation convenience.

## Developer Session Validation

Startup prompt: `## Developer` in `ai_agents/session_starters/README.md`.

The Developer session passes when it:

1. Starts only from an approved Jira Story or Bug in `READY TO START`.
2. Checks dependency eligibility and Codex limits before implementation.
3. Creates visible Jira subtasks before changing files.
4. Uses `feature/{JIRA_KEY}-{short-slug}` branch naming.
5. Commits one validated implementation stage at a time.
6. Updates each subtask with changed files, commit SHA, and validation results.
7. Opens a pull request linked to the Jira story.
8. Moves the parent issue to `DEV COMPLETED` only after development validation
   and pull request creation.

Stop when the story is not approved, dependencies are unresolved, context is
missing, limits are closed, tests fail, or a PO decision is needed.

## Review Session Validation

Startup prompt: `## Review` in `ai_agents/session_starters/README.md`.

The Review session passes when it:

1. Reviews the pull request diff first.
2. Checks changed files against acceptance criteria and direct contracts.
3. Verifies validation evidence and Jira pull request visibility.
4. Checks mergeability and conflict status.
5. Requests changes for correctness, security, missing tests, unrelated files,
   or conflicts.
6. Merges only after review findings, checks, and conflicts are clean.
7. Records PR URL, merge SHA, and `test_requested` handoff guidance in Jira.
8. Confirms the story remains in `DEV COMPLETED`; Tester owns the move to
   `IN TESTING`.

Review findings are not product bugs unless they represent a product defect
already merged or released. Merge conflicts are sent back to the Developer
Agent that owns the branch.

## Tester Session Validation

Startup prompt: `## Tester` in `ai_agents/session_starters/README.md`.

The Tester session passes when it:

1. Starts only after the story is merged to `main`, Review has emitted
   `test_requested`, and the story is in `DEV COMPLETED`.
2. Moves the story to `IN TESTING`.
3. Tests each acceptance criterion against merged code or documentation.
4. Creates or updates an AgileTest-style Jira `Test` issue for reusable
   coverage unless the story is explicitly one-time validation.
5. Saves timestamped evidence under `data/agent-logs/<JIRA_ISSUE>/`.
6. Moves the story to `TEST COMPLETED` when all checks pass.
7. Creates and links a Bug when testing fails, then moves the story back to
   `DEV COMPLETED` for developer pickup.

The Developer Agent must treat a `DEV COMPLETED` story with linked open bugs as
rework-ready and should not wait for a new story when the bug blocks the sprint
scope.

## Release Manager Session Validation

Startup prompt: `## Release Manager` in
`ai_agents/session_starters/README.md`.

The Release Manager session passes when it:

1. Waits until sprint implementation stories are tested or blocked by visible
   bugs.
2. Builds regression scope from reusable Test issues and changed behavior.
3. Runs or records sprint regression evidence.
4. Creates closure notes with delivered scope, regression result, PO
   acceptance summary, and sprint fit.
5. Keeps retro follow-up implementation stories in `FUNNEL` when Product Owner
   review is needed before the next sprint.
6. Closes the sprint only after tested scope, regression, closure evidence, and
   accepted status are consistent.

## Bug And PO Question Routing

Use bugs for failed implemented behavior. Use the PO inbox for missing business
decisions.

1. Tester-created bugs link to the failed story and Test issue.
2. Failed stories move back to `DEV COMPLETED` so Developer sessions can pick
   up rework.
3. Developer rework uses the same branch and PR discipline as normal work.
4. Retest evidence references the bug and original story.
5. Product questions are written to the durable PO inbox when expected behavior,
   acceptance criteria, scope, credentials, or release decisions are unclear.
6. Work pauses only for blockers that can change business scope or correctness.

## Findings Classification

Findings from the validation run become one of these outcomes:

1. Release 1.1 fix: create or update a Jira story/bug in the current release
   when the supervised session process is broken or unclear.
2. Release 1.2 Docker requirement: create a `FUNNEL` backlog story when the
   finding belongs to future detached worker automation.
3. Documentation-only improvement: update shared docs through the current Jira
   story when the fix only clarifies the validated process.
4. PO decision: create a PO inbox item and stop the affected work.

Do not hide findings in local notes. The evidence must list each finding and
the selected classification.

## Evidence Template

Save evidence under
`data/agent-logs/<JIRA_ISSUE>/delivery-flow-validation-<timestamp>.md`.

Include:

1. Developer session result and PR link.
2. Review session result and merge SHA.
3. Tester session result and Test issue key.
4. Release Manager result and regression/closure artifact paths.
5. Bugs created, retested, and linked.
6. PO inbox questions created or `none`.
7. Findings classification for Release 1.1 or Release 1.2.
