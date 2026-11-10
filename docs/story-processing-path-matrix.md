# Story Processing Path Matrix

Status: Release 1.2 canonical process baseline for `AGENT-683`.

This document is the source of truth for deterministic story routing. Domain
fixtures live in `src/agentic_boilerplate/domain/story_processing_path_matrix.py`.
If another workflow document conflicts with this matrix, this matrix wins and
the conflicting document must be updated by the same story or a linked follow-up.

## Handoff Decision

Review Agent does not move a merged story to `IN TESTING`.

The canonical handoff is:

1. Developer completes implementation, opens the PR, and moves the story to
   `DEV COMPLETED`.
2. Review Agent reviews, resolves approval, merges clean PRs, confirms the
   story remains `DEV COMPLETED`, and emits `test_requested`.
3. Tester Agent starts from merged `DEV COMPLETED`, moves the story to
   `IN TESTING`, validates acceptance criteria, and then moves passed work to
   `TEST COMPLETED`.

This keeps Review ownership focused on PR quality and merge, and keeps Tester
ownership focused on validation state.

## Identity Required For Every Route

Every route must carry:

1. `project_id`
2. `jira_issue_key`
3. `assignment_id`
4. `workspace_path`
5. `context_pack_path`
6. `evidence_path`
7. `communication_channel_id`

These fields keep multi-project and parallel-worker processing isolated and
traceable.

## Canonical Routes

| Route | From | Event | Owner | To | Next role | Message | Required artifacts |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `funnel.scope-approved` | `FUNNEL` | `po_scope_approved` | Product Owner | `READY TO START` | Scheduler | `backlog_ready` | approved scope, acceptance criteria, dependency links |
| `ready.assignment-started` | `READY TO START` | `assignment_started` | Scheduler | `IN PROGRESS` | Developer | `assignment_started` | assignment record, context pack, dependency gate, limit gate, assignment lock |
| `ready.dependency-blocked` | `READY TO START` | `dependency_blocked` | Orchestrator | `READY TO START` | Scheduler | `assignment_blocked` | dependency gate report, blocked issue keys |
| `ready.context-missing` | `READY TO START` | `context_missing` | Orchestrator | `READY TO START` | Product Planning | `assignment_blocked` | missing context report, PO inbox item or follow-up story |
| `ready.design-reference-missing` | `READY TO START` | `design_reference_missing` | Orchestrator | `READY TO START` | Product Planning | `assignment_blocked` | design gate report, design story or PO override |
| `ready.integration-readiness-missing` | `READY TO START` | `integration_readiness_missing` | Orchestrator | `READY TO START` | Operator | `assignment_blocked` | integration readiness report, setup diagnostic |
| `in-progress.development-completed` | `IN PROGRESS` | `development_completed` | Developer | `DEV COMPLETED` | Review | `pr_ready_for_review` | completed subtasks, developer validation, PR URL, Jira PR link |
| `dev-completed.review-changes-requested` | `DEV COMPLETED` | `review_changes_requested` | Review | `DEV COMPLETED` | Developer | `review_rework_requested` | review record, requested changes, finding history |
| `dev-completed.merge-conflict-detected` | `DEV COMPLETED` | `merge_conflict_detected` | Review | `DEV COMPLETED` | Developer | `review_rework_requested` | review record, conflict report, finding history |
| `dev-completed.review-merged` | `DEV COMPLETED` | `review_merged` | Review | `DEV COMPLETED` | Tester | `test_requested` | review record, merged PR, merge SHA, test requested handoff |
| `dev-completed.testing-started` | `DEV COMPLETED` | `testing_started` | Tester | `IN TESTING` | Tester | `testing_started` | test plan, acceptance criteria, merged PR, evidence path |
| `in-testing.testing-passed` | `IN TESTING` | `testing_passed` | Tester | `TEST COMPLETED` | Release Manager | `testing_completed` | test evidence, test case or one-time validation, coverage mapping |
| `in-testing.testing-failed` | `IN TESTING` | `testing_failed` | Tester | `DEV COMPLETED` | Developer | `bug_rework_requested` | linked bug, failed test evidence, bug-related labels, retest scope |
| `test-completed.regression-passed` | `TEST COMPLETED` | `regression_passed` | Release Manager | `TEST COMPLETED` | Release Manager | `regression_completed` | regression manifest, regression evidence, test execution links |
| `test-completed.regression-failed` | `TEST COMPLETED` | `regression_failed` | Release Manager | `DEV COMPLETED` | Developer | `regression_rework_requested` | linked bug, regression evidence, affected scope, retest scope |
| `test-completed.retro-completed` | `TEST COMPLETED` | `retro_completed` | Release Manager | `TEST COMPLETED` | Release Manager | `retro_requested` | retro notes, agent retro responses, follow-up backlog candidates |
| `test-completed.closure-completed` | `TEST COMPLETED` | `closure_completed` | Release Manager | `ACCEPTED/DONE` | Product Owner | `closure_ready` | closure package, PO batch acceptance, release notes or sprint summary |
| `in-progress.limit-paused` | `IN PROGRESS` | `limit_paused` | Scheduler | `IN PROGRESS` | Scheduler | `limit_paused` | paused assignment, failed request, resume after, limit record |
| `in-progress.po-question-created` | `IN PROGRESS` | `po_question_created` | Orchestrator | `IN PROGRESS` | Product Owner | `po_question` | PO inbox item, paused assignment, decision context |
| `in-progress.po-answer-received` | `IN PROGRESS` | `po_answer_received` | Orchestrator | `IN PROGRESS` | Scheduler | `po_resume_instruction` | answered PO inbox item, gate recheck, resume request |
| `in-progress.worker-crashed` | `IN PROGRESS` | `worker_crashed` | Scheduler | `IN PROGRESS` | Operator | `operator_rescue_required` | checkpoint, failed request, worker log, resume metadata |
| `in-progress.stale-assignment-found` | `IN PROGRESS` | `stale_assignment_found` | Operator | `READY TO START` | Scheduler | `operator_rescue_required` | stale lock report, operator rescue decision, assignment release record |
| `ready.dependency-unblocked` | `READY TO START` | `dependency_unblocked` | Orchestrator | `READY TO START` | Scheduler | `dependency_unblocked` | dependency gate report, eligible story scan, same sprint selection |
| `accepted-done.release-archived` | `ACCEPTED/DONE` | `release_archived` | Release Manager | `ACCEPTED/DONE` | Product Owner | `release_archived` | release tag, published docs, archive index |

## Loop Rules

Review rework:

1. Review records findings or conflict.
2. Review emits `review_rework_requested`.
3. Developer updates the same branch or stack according to the PR policy.
4. Review rechecks with finding history.
5. Repeated identical findings escalate after the configured threshold.

Tester bug loop:

1. Tester fails validation.
2. Tester creates or links a Bug and evidence.
3. Story returns to `DEV COMPLETED`.
4. Developer fixes through PR/review.
5. Tester retests linked bug scope before `TEST COMPLETED`.

Regression bug loop:

1. Release Manager or Tester records regression failure.
2. A Bug is linked to the affected story or release scope.
3. Developer fixes, Review merges, Tester retests.
4. Regression status is refreshed before closure.

PO pause/resume:

1. Missing business/process input creates a PO inbox item.
2. Work pauses with assignment and decision context.
3. Orchestrator consumes the answer.
4. Orchestrator emits `po_resume_instruction` and rechecks gates.
5. Scheduler resumes the paused assignment or selects another eligible story.

## Invalid Route Handling

If no route exists for a status/event pair, the agent must not improvise. It
must record an assignment blocker or PO inbox item with:

1. Current status.
2. Requested event.
3. Actor.
4. Target status if known.
5. Missing route reason.
6. Suggested owner to extend the matrix.

Tests in `tests/test_story_processing_path_matrix.py` prove valid routes and
invalid route rejection.

## Sprint Path Resolver

The status/event matrix defines legal transitions. Before assignment,
Orchestrator and Release Manager agents also resolve sprint working paths using
[Stacked PR Sprint Path Resolver](stacked-pr-sprint-path-resolver.md).

That resolver decides whether each approved story is:

1. independent and parallel-safe,
2. part of a same-repository stacked PR chain,
3. sequential-only, or
4. blocked until Product Owner input.

Agents must follow the durable resolver artifact before picking work. If the
artifact conflicts with Jira dependency links, design gates, context packs, or
credential readiness, the agent stops and creates a Product Owner inbox item.
