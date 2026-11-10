# Definition Of Ready Gate

Status: Release 1.2 implementation baseline for `AGENT-681`.

The Definition of Ready gate is the last machine-checkable guard before a
Scheduler or Orchestrator creates a worker assignment.

The implementation lives in
`src/agentic_boilerplate/domain/definition_of_ready.py`.

## Required Inputs

A story, bug, or task is assignable only when it has:

1. Jira status `READY TO START`.
2. Release and sprint labels, or Jira sprint membership.
3. At least one acceptance criterion.
4. Approved context pack path.
5. Role route.
6. Model and reasoning route.
7. Target repository.
8. Target workspace path.
9. Passing dependency gate.
10. No unresolved linked bugs.
11. Passing setup/integration validation.
12. Fresh Codex limit state.

UI-facing implementation also requires:

1. Accepted design reference.
2. Blocking dependency to the design story or approved PO override.

The canonical UI gate is documented in `docs/ui-design-gate.md`.

Multi-repo work also requires a repository change map that names which change
belongs to which repository.

## Blocker Codes

The gate returns machine-readable blocker kinds:

1. `status_not_ready`
2. `missing_release_or_sprint`
3. `missing_acceptance_criteria`
4. `missing_context_pack`
5. `missing_role_route`
6. `missing_model_route`
7. `missing_target_repository`
8. `missing_target_workspace`
9. `unresolved_dependency`
10. `unresolved_linked_bug`
11. `missing_setup_validation`
12. `stale_limit_state`
13. `missing_design_reference`
14. `missing_design_dependency`
15. `missing_multi_repo_change_map`

## Scheduler Behavior

Scheduler must not assign a candidate when the Definition of Ready decision is
not ready.

When the preferred story fails the gate, Scheduler records the PO-visible
reason and scans the same approved sprint for another `READY TO START` story
whose dependency, lock, limit, workspace, and Definition of Ready gates pass.

Scheduler must not pull stories from another sprint without Product Owner
override.

## PO-Visible Explanation

Use `render_definition_of_ready_explanation` when a blocked story needs a Jira
comment, PO inbox message, operator UI row, or durable evidence artifact.

The explanation includes:

1. Jira issue key.
2. Ready yes/no.
3. Reasons.
4. Blocker codes.
5. Related dependency or bug keys when available.

## Relationship To Other Gates

Definition of Ready does not replace:

1. Dependency eligibility.
2. Assignment locks.
3. Codex limit availability.
4. Design acceptance gates.
5. DevSecOps preflight.
6. Story processing path matrix.
7. Live integration readiness diagnostics.

It aggregates those outputs into one assignment-facing decision so workers do
not start from incomplete context.

Live readiness is documented in `docs/live-integration-readiness.md`. A failed
live readiness report maps to `missing_setup_validation` because the worker
cannot safely execute until project paths, Jira, GitHub, documentation, testing,
and required optional design integrations are ready.
