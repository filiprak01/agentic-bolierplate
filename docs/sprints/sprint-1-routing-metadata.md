# Sprint 1 Routing Metadata

Release: `release-mvp`

Release version target: `1.0.0`

Sprint ring label: `sprint-ring-1`

Jira sprint: `MVP S1 Foundation`

## Purpose

This file mirrors the Sprint 1 Jira scope with the complexity metadata needed by
future schedulers, context-pack generation, and Codex routing.

The Release Manager and Scheduler should use this metadata with Jira status and
dependency checks. A story is executable only when it is in `READY TO START` and
all prerequisite links are satisfied.

## Sprint 1 Stories

| Issue | Summary | Complexity | Points | Model | Reasoning | Speed | Labels | Prerequisites |
| --- | --- | --- | ---: | --- | --- | --- | --- | --- |
| `AGENT-7` | Create Python Project Scaffold | C2 | 2 | `gpt-5.5` | medium | normal | `release-mvp`, `sprint-ring-1` | None |
| `AGENT-15` | Define Story Complexity And Codex Routing Model | C3 | 3 | `gpt-5.5` | high | normal | `release-mvp`, `sprint-ring-1` | `AGENT-7` |
| `AGENT-9` | Implement Configuration Loader | C3 | 3 | `gpt-5.5` | high | normal | `release-mvp`, `sprint-ring-1` | `AGENT-7`, `AGENT-15` |
| `AGENT-11` | Create Durable Directory Structure | C2 | 2 | `gpt-5.5` | medium | normal | `release-mvp`, `sprint-ring-1` | `AGENT-7`, `AGENT-15` |
| `AGENT-14` | Add Basic Test Setup | C1 | 1 | `gpt-5.4-mini` | medium | normal | `release-mvp`, `sprint-ring-1` | `AGENT-7` |

Total complexity: 11 points.

Target capacity range: 10-14 points.

## Context Pack Values

Each Sprint 1 story context pack should include:

1. `release_label`: `release-mvp`
2. `sprint_ring_label`: `sprint-ring-1`
3. `speed`: `normal`
4. `complexity`, `complexity_name`, and `complexity_points`
5. `model` and `reasoning`
6. `complexity_rationale`
7. `c4_justification`: empty for Sprint 1
8. `jira_issue_key`
9. `role`

## Jira Metadata Expectations

Jira should mirror this local metadata through issue labels, description text, or
future custom fields.

Required labels for Sprint 1 stories:

1. `release-mvp`
2. `sprint-ring-1`
3. `complexity-c1`, `complexity-c2`, or `complexity-c3`

Dependency links should be represented with Jira issue links where prerequisites
block dependent stories.

## Scope Guard

Sprint 1 is a foundation sprint. It should not grow past the hard warning
threshold of 15 complexity points without Product Owner approval and an updated
release/sprint planning note.
