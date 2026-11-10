# Codex Model Discovery And Routing

## Purpose

This contract decides whether an agent may start a Codex-backed assignment with
the requested model and reasoning level. It combines three inputs:

1. The static role/complexity matrix from `docs/story-complexity-model.md`.
2. Runtime `model/list` discovery from Codex App Server.
3. Durable quota state from `account/rateLimits/read` when the selected model
   has a separate metered bucket such as Spark.

Workers must not infer model availability from stale docs, UI memory, or a
previous project. Discovery is per host/account scope and must be refreshed
before assignment planning when the available model set is uncertain.

## Runtime Sequence

Before quota-spending work:

1. Load `AGENTS.md`, the role file, and `.agents/skills/codex-quota-guard/SKILL.md`.
2. Refresh Codex quota with `agentic codex-limits refresh` or a host-owned guard
   decision.
3. Read available models through `CodexAppServerModelReader`, which calls
   Codex App Server `model/list` over initialized JSON-RPC stdio.
4. Build a route config from defaults plus environment/config overrides.
5. Select a route with `select_codex_model_route`.
6. If the decision is `allowed`, continue with the assignment.
7. If the decision is `po_switch_required`, ask the Product Owner to switch the
   active Codex session model/reasoning and stop until confirmed.
8. If the decision is `blocked`, create or update a PO inbox blocker or durable
   worker diagnostic and do not spend quota.

Model routing does not replace the quota gate. A model can be available while
quota is blocked; in that case the quota decision wins.

## Environment Overrides

Defaults are conservative and role-first. Operators can override them with
these keys:

```text
CODEX_ROUTE_MODEL_<ROLE>=gpt-5.4
CODEX_ROUTE_REASONING_<ROLE>=high
CODEX_ROUTE_SPEED_<ROLE>=normal
CODEX_MODEL_ROLE_<ROLE>=gpt-5.4
CODEX_REASONING_ROLE_<ROLE>=high
CODEX_MODEL_<ROLE>=gpt-5.4
CODEX_REASONING_<ROLE>=high

CODEX_ROUTE_MODEL_COMPLEXITY_C1=gpt-5.4-mini
CODEX_ROUTE_REASONING_COMPLEXITY_C1=medium
CODEX_MODEL_COMPLEXITY_C1=gpt-5.4-mini
CODEX_REASONING_COMPLEXITY_C1=medium

CODEX_MODEL_FALLBACK_ORDER=gpt-5.5,gpt-5.4,gpt-5.4-mini
CODEX_MODEL_LIMIT_STOP_THRESHOLD_PERCENT=10
```

`<ROLE>` is the upper-case `AgentRole` value, for example `DEVELOPER`,
`PRODUCT_PLANNING`, `ARCHITECTURE`, `SECURITY`, `RELEASE_MANAGER`,
`DOCS_CONFLUENCE`, or `DEVOPS_PLATFORM`.

## Backbone Roles

Product Planning, Architecture, and Security are backbone roles. They do not
silently downgrade when their configured model or reasoning is unavailable.
They must ask the Product Owner to switch, wait for the configured model to be
available, or create a PO inbox blocker.

Developer, Review, Tester, Release Manager, Docs, UI/UX, DevOps/Platform, and
Data/Persistence may use fallback order only when the selected fallback supports
the required reasoning and the assignment is not blocked by quota or policy.

## Spark

Spark is optional and explicit:

```text
CODEX_SPARK_ENABLED=true
CODEX_SPARK_MODEL_ID=gpt-5.3-codex-spark
CODEX_SPARK_ALLOWED_ROLES=tester,release_manager,docs_confluence,ui_ux,review
CODEX_SPARK_ALLOWED_COMPLEXITIES=C1,C2
```

Spark may be selected only when all of these are true:

1. The route explicitly asks for the Spark model.
2. `CODEX_SPARK_ENABLED=true`.
3. The role and complexity are allowlisted.
4. `model/list` shows the Spark model and required reasoning effort.
5. `account/rateLimits/read` shows the related separate bucket and the selected
   gate allows `resume`.

Spark is not a default fallback for Product Planning, Architecture, Security,
Developer implementation, broad review, or risk-sensitive decisions.

## Evidence

Every route decision written to worker logs, PR bodies, Jira comments, or
completion evidence should include:

1. Decision status: `allowed`, `po_switch_required`, or `blocked`.
2. Role, Jira issue, project id, repository, and assignment/workspace identity.
3. Complexity level and routing source.
4. Selected model, reasoning, speed, and rationale.
5. Available model ids from the current discovery snapshot.
6. Limit bucket ids and required bucket id when applicable.
7. Current session model/reasoning when known.
8. Quota gate id/action when a quota record was used.

## Implementation Files

```text
src/agentic_boilerplate/domain/codex_model_routing.py
src/agentic_boilerplate/runtime/codex_model_reader.py
tests/test_codex_model_routing.py
```
