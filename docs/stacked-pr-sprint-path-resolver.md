# Stacked PR Sprint Path Resolver

Status: Release 1.2 process contract for `AGENT-687`.

This document defines how Orchestrator and Release Manager agents decide which
approved sprint stories can run independently, which can use stacked pull
requests, which must stay sequential, and which require Product Owner input.

## Inputs

For every sprint story, the resolver requires:

1. Jira issue key, status, summary, release label, and sprint label.
2. Target repository and trunk branch.
3. Acceptance criteria.
4. Context pack path.
5. Role route and next agent role.
6. Dependency links with dependency kind.
7. Design gate state for UI-facing implementation.
8. Credential and integration readiness state when the story needs external
   systems.

## Path Kinds

| Path kind | Meaning | Worker behavior |
| --- | --- | --- |
| `independent-parallel` | Story has no unresolved implementation dependency inside the sprint. | Scheduler may assign it to any available matching worker lane. |
| `stacked-dependent` | Story is part of a same-repository, same-trunk implementation dependency chain. | Agents must follow stack id, lane id, and order before review/merge/test decisions. |
| `sequential-only` | Story has dependency risk that is not safe for stacked PRs, such as cross-repo or trunk mismatch. | Scheduler keeps normal sequential dependency handling. |
| `blocked-needs-po` | Story lacks a required decision, AC, context pack, accepted design, credentials, or has an unresolved business dependency. | Agent creates or references a PO inbox question and stops. |

## Stacked PR Eligibility

A stacked-dependent path is allowed only when:

1. All stories in the stack are in the same sprint.
2. All stories target the same repository.
3. All stories target the same trunk branch.
4. Dependencies are implementation-layer dependencies.
5. No dependency represents an unresolved business decision, design approval,
   credential setup, unknown dependency, or cross-repo boundary.

GitHub stacked PR support is treated as an optional execution improvement. If
GitHub stacked PR tooling is unavailable or branch protection blocks stack
operations, agents fall back to normal branch/PR sequencing while preserving the
same resolver artifact.

CI and quality gate requirements for stacked PR layers and integrated stack
merges are defined in `docs/stacked-pr-ci-quality-gates.md`.
Product Owner and operator visibility requirements for stack lanes, evidence
finality, stale/retest state, and PR/branch references are defined in
`docs/stacked-pr-operator-visibility.md`.

## Durable Artifact

The resolver artifact must include one row per story:

1. `issue_key`
2. `path_kind`
3. `lane_id`
4. `stack_id`
5. `order`
6. `blockers`
7. `next_agent_role`
8. `testability_timing`
9. `prerequisite_keys`
10. `downstream_issue_keys`

Agents must not improvise a different sprint path. If the artifact is missing,
stale, or conflicts with Jira, the agent stops and creates a Product Owner inbox
question.

The context-pack generator and assignment store copy this artifact into durable
worker inputs:

1. `ContextPack.stack_metadata` carries branch, layer, parent/child story, PR,
   and testability data for Developer, Review, Tester, and Release Manager
   agents.
2. `AgentAssignment.stack_metadata` carries stack mode, resolver version,
   current layer, expected next agent, and stale/rebase-required state for
   scheduler and worker recovery.

When these fields are present, agents follow them as the deterministic sprint
path. When they are absent or empty, the story is treated as non-stacked and the
normal single-branch workflow applies.

## Testability Timing

| Timing | Meaning |
| --- | --- |
| `after-story-merge` | Independent story can be tested after its own PR merges to trunk. |
| `after-stack-layer-merge` | Stack layer can receive early validation after the layer merges, with full regression after stack completion. |
| `after-prerequisites-merge` | Sequential story waits for prerequisite merges before testing. |
| `after-po-decision` | Blocked story waits for Product Owner resolution before testing can be planned. |
