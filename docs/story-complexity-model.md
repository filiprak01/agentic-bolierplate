# Story Complexity And Codex Routing

## Purpose

Story complexity tells the platform how much model/reasoning budget a task
should receive before a Codex job or future API call is created.

Complexity is not the same as business priority. A small but security-sensitive
story can have high complexity, while a large documentation task can remain
medium.

## Routing Rules

Default speed is `normal`.

Do not use faster speed by default because the Product Owner wants to preserve
limited Codex usage.

Role-based routing is evaluated before complexity fallback for execution work.
Complexity remains the fallback when the worker role is unknown or when a
planning artifact is prepared before assignment.

Approved role matrix:

| Role | Default Model | Reasoning |
| --- | --- | --- |
| `scheduler` | `gpt-5.5` | `high` |
| `product_planning` | `gpt-5.5` | `xhigh` |
| `architecture` | `gpt-5.5` | `xhigh` |
| `developer` | `gpt-5.4` | `high` |
| `review` | `gpt-5.4` | `high` |
| `tester` | `gpt-5.4-mini` | `high` |
| `release_manager` | `gpt-5.4-mini` | `high` |
| `platform` | `gpt-5.4` | `high` |
| `frontend` | `gpt-5.4` | `high` |
| `ui_ux` | `gpt-5.4` | `high` |
| `security` | `gpt-5.5` | `xhigh` |
| `docs_confluence` | `gpt-5.4-mini` | `high` |
| `devops_platform` | `gpt-5.4` | `high` |
| `data_persistence` | `gpt-5.4` | `high` |

No Release 1.1 role defaults to `medium` reasoning. A worker may use medium
only when the Product Owner approves a limit-saving override for a specific
assignment and the context pack records the override reason.

| Level | Name | Use When | Default Model | Reasoning |
| --- | --- | --- | --- | --- |
| C1 | Simple | Small docs, formatting, smoke tests, or isolated low-risk changes | `gpt-5.4-mini` | `medium` |
| C2 | Standard | Normal implementation with clear acceptance criteria and limited architecture risk | `gpt-5.5` | `medium` |
| C3 | Complex | Config, persistence, integrations, model routing, security-sensitive behavior, or cross-module contracts | `gpt-5.5` | `high` |
| C4 | Critical Audit | One-time broad audits, architecture/security reviews, or repeated hard failures | `gpt-5.5` | `xhigh` |

## Complexity Points

Complexity points are used for sprint sizing and token-spend control.

| Level | Points |
| --- | ---: |
| C1 | 1 |
| C2 | 2 |
| C3 | 3 |
| C4 | 5 |

Recommended sprint-ring capacity for the MVP:

1. Target range: 10-14 complexity points.
2. Hard warning threshold: 15 complexity points.
3. Maximum story count: 5 stories per sprint ring by default.
4. Maximum C3 stories: 4 per sprint ring by default.
5. C4 stories should be audit-only and need explicit Product Owner approval.

The capacity model is intentionally configurable. Future projects can adjust
target points, maximum stories, C3 count, C4 allowance, and model-routing rules
based on subscription limits, available workers, and token-spending rate.

## Escalation Rules

1. Architecture, security, data model, persistence, and external integration
   stories should be reviewed for C3 complexity.
2. Role-based routing should be selected before complexity fallback for
   execution workers.
3. When the selected routing differs from the current Codex session, the worker
   must create a manual switch checkpoint for the Product Owner before work
   starts.
4. Codex cannot switch the active UI or session model automatically.
5. C4 or any extra-high reasoning requires an explicit reason in the context
   pack or review note.
6. If a C2 story discovers missing requirements, it pauses and creates a
   Product Owner question instead of silently escalating business scope.
7. If a story reaches Codex limits, the worker saves the failed request, context
   pack, partial output, logs, and assignment state before pausing.

## Required Story Metadata

Each story should expose:

1. Complexity level.
2. Recommended model.
3. Recommended reasoning.
4. Speed.
5. Complexity rationale.
6. Whether C4 escalation is allowed.
7. Complexity points.
8. Release label.
9. Sprint-ring label.
10. Routing source.
11. Worker role when the role matrix selected the route.

This metadata should be stored locally, copied into Jira descriptions or labels,
and included in generated context packs.

## Context Pack Fields

Every generated context pack should include these routing fields:

1. `complexity`
2. `complexity_name`
3. `complexity_points`
4. `model`
5. `reasoning`
6. `speed`
7. `complexity_rationale`
8. `c4_justification`
9. `release_label`
10. `sprint_ring_label`
11. `jira_issue_key`
12. `role`
13. `routing_source`
14. `routing_rationale`
15. `manual_switch_required`
16. `manual_switch_prompt`
17. `role_instruction_path`
18. `role_instruction_version`
19. `role_routing_override_reason`

`c4_justification` is required when `complexity` is `C4`. For all other levels
it should be empty unless the Architecture Agent or Release Manager wants to
record extra review context.

`role_instruction_path` points to the role file loaded for the assignment, such
as `ai_agents/roles/frontend.md`. `role_routing_override_reason` is required
when a story intentionally deviates from the role matrix.

## Runtime Model Discovery

Release 1.2 adds runtime model discovery on top of this static matrix. The
static matrix remains the requested route; the runtime route decision verifies
that the requested model exists, supports the requested reasoning effort, and is
allowed by quota/policy before work starts.

Use `docs/codex-model-routing.md` for the machine-readable sequence and env
keys. The implementation must use Codex App Server JSON-RPC `model/list` for
model inventory and `account/rateLimits/read` through the quota guard for
separate model buckets. Do not use undocumented gRPC calls, UI scraping, or
stale session memory as a routing source.

Product Planning, Architecture, and Security are backbone roles. They fail
closed instead of silently falling back to a cheaper model. Other roles may use
configured fallback order only when the fallback model supports the required
reasoning and the quota gate allows the assignment.

## Implementation Boundary

The default routing values are also represented in code:

```text
src/agentic_boilerplate/domain/story_complexity.py
src/agentic_boilerplate/domain/codex_model_routing.py
src/agentic_boilerplate/runtime/codex_model_reader.py
```

The code model is intentionally dependency-free so configuration loading,
planning, scheduling, and context-pack generation can reuse it without creating
framework coupling.
