# Stacked PR Operator Visibility

Status: Release 1.2 process contract for `AGENT-692`.

Stacked PR operator visibility makes stacked, parallel, blocked, stale, and
waiting work readable from durable assignment records. It is a Product Owner
and operator surface; it does not replace Jira, GitHub PR review, AgileTest
evidence, or the deterministic sprint path resolver.

## Source Of Truth

Agents must use these sources in order:

1. `docs/stacked-pr-sprint-path-resolver.md` for path kind, stack id, lane id,
   layer order, and next role.
2. `ContextPack.stack_metadata` for story-specific worker context.
3. `AgentAssignment.stack_metadata` for operator status, recovery, and UI-ready
   stack lane display.
4. Jira links and statuses for dependency and workflow truth.
5. GitHub PR state for branch, review, merge, and conflict truth.

If these sources disagree, agents stop and create a Product Owner inbox item
instead of silently choosing one interpretation.

## Operator Status API

`GET /operator-status` includes `stack_lanes` when at least one durable
assignment has stack metadata.

Each lane row includes:

1. Stack id and lane id.
2. Stack mode and resolved path version.
3. Ordered stories with Jira key, assignment id, layer order, current agent,
   current assignment status, next step, and branch/PR references.
4. Blocked reason when the assignment is paused, failed, stale, or requires a
   rebase.
5. `stale_retest_required` so Tester Agent and Release Manager can see when
   previous evidence must be rerun.
6. `evidence_state`: `final`, `provisional`, `stale`, `blocked`, or
   `not-recorded`.

The frontend must render missing PR links as `PR not recorded`, not as a hidden
or successful state. Branch metadata can still be shown as a fallback so the
operator can trace work back to GitHub.

## Role Expectations

Orchestrator Agent reads the resolver artifact before assigning sprint work. It
can route independent stories in parallel, route stacked stories by lane/layer,
or pause when metadata is missing.

Developer Agent preserves stack id, lane id, layer order, base branch, branch
name, and context pack path in the handoff and assignment metadata. If an upper
layer becomes stale after a lower layer changes, Developer Agent owns the rebase
or branch refresh.

Review Agent reviews layer-local diffs against the configured layer base. It
publishes whether a finding is layer-local or caused by lower-layer changes and
marks upper layers stale when reviewed lower-layer SHAs no longer match.

Tester Agent can perform early validation only when the resolver says the layer
is testable. Early evidence is provisional until the required merge point is
reached. Any lower-layer change that can affect the tested behavior makes the
evidence stale and requires retest before final regression.

Release Manager uses stack lanes to prepare regression and closure visibility.
Sprint closure is blocked when a stack lane contains unresolved blockers,
stale evidence, missing final evidence for required behavior, or unmerged
required layers.

## GitHub Stacked PR Caveats

GitHub stacked PR support is optional. When a repository does not have a stable
stacked PR workflow, agents use fallback branch-chain mode:

1. Keep one feature branch per story.
2. Use lower-layer branches as upper-layer bases when safe.
3. Keep the same resolver artifact and assignment metadata.
4. Merge lower layers first.
5. Rebase or refresh upper layers after lower-layer merge when required.

Branch protection, merge queue support, and required checks must follow
`docs/stacked-pr-ci-quality-gates.md`.

## PO Visibility Rule

The Product Owner must be able to answer these questions from the operator
status screen or API response:

1. Which stack and lane is this story in?
2. Which layer is this story?
3. Which agent has it now, and what is the next expected agent?
4. Is the story blocked, waiting, stale, or ready for the next step?
5. Is tester evidence final, provisional, stale, blocked, or missing?
6. Which PR link or branch should be inspected?

If any answer is unavailable because the assignment lacks metadata, the UI
shows the missing state and the relevant agent records a process finding.
