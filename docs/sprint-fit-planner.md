# Sprint Fit Planner

Status: implemented for MVP Sprint 6

The sprint fit planner evaluates whether a sprint ring is likely to fit the
configured Codex Plus working window while preserving coherent deliverable
scope as the primary planning boundary.

Complexity is warning and model-routing metadata. It should not automatically
split a coherent sprint scope without Product Owner or Release Manager review.

## Inputs

The planner uses:

1. A `ReleaseScope`.
2. A sprint ring number.
3. A coherent deliverable scope description.
4. A `SprintFitCapacity` configuration.
5. A release label.
6. Optional capacity override details.

`SprintFitCapacity` includes:

1. Codex working-window name.
2. Maximum complexity points.
3. Maximum story count.

## Complexity Points

The planner uses the shared story complexity routing:

| Complexity | Warning Points |
| --- | ---: |
| C1 | 1 |
| C2 | 2 |
| C3 | 3 |
| C4 | 5 |

These points forecast limit risk and model routing. They are not the primary
release/sprint slicing rule.

## Warnings

The planner emits warnings when:

1. The sprint ring complexity total exceeds the configured target.
2. The sprint ring story count exceeds the configured target.

Warnings do not split scope automatically. The Release Manager can keep the
coherent scope together by recording an override reason.

## Labels

The planner prepares labels for each story:

1. Release label, such as `release-mvp`.
2. Sprint ring label, such as `sprint-ring-06`.
3. Sprint label, such as `mvp-sprint-06`.
4. Optional `sprint-fit-warning` label when warnings exist.

Jira updates remain adapter-level behavior. The planner only returns the label
plan.
