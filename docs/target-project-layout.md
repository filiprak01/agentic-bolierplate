# Target Project Preparation Layout

Status: Release 1.1 setup convention

This document defines what belongs inside the target project checkout and what
belongs in the agentic boilerplate platform durable data.

## Ownership Rule

The target project checkout is for target product code and project-specific
source preparation inputs.

The agentic boilerplate repository owns runtime state, worker state, PO inbox
items, generated context packs, Codex jobs/results, sprint records, regression
evidence, and Confluence mirrors under durable platform data paths.

Do not store platform runtime state inside the target project checkout.

## Standard Target Project Folders

Create these folders in the target project when the project needs them:

```text
docs/product/
docs/architecture/
docs/nfr/
docs/release-scope/
docs/samples/
docs/decisions/
```

Recommended use:

1. `docs/product/` - Product Owner vision, business goals, personas, domain
   terms, assumptions, and source requirements.
2. `docs/architecture/` - architecture drafts, diagrams, integration notes,
   constraints, and target system decisions.
3. `docs/nfr/` - non-functional requirements such as security, performance,
   reliability, observability, privacy, cost, and token optimization goals.
4. `docs/release-scope/` - release goals, phase plans, milestone notes, and
   scope boundaries used by Product Planning and Release Manager agents.
5. `docs/samples/` - sample files, payloads, screenshots, fixtures, anonymized
   customer examples, and source material used to clarify expected behavior.
6. `docs/decisions/` - project-specific ADRs or PO-approved decisions that
   should travel with the target product repository.

Target project application code should stay in the target project's normal
language/framework structure, for example `src/`, `app/`, `services/`,
`frontend/`, `backend/`, `tests/`, or the existing project convention.

## Platform Durable Data

These artifacts belong in the agentic boilerplate platform durable data, not in
the target project checkout:

```text
data/po-inbox/
data/context-packs/
data/codex-jobs/
data/codex-results/
data/codex-limits/
data/agent-state/
data/agent-logs/
data/po-decisions/
data/sprints/
data/confluence-mirror/
```

The PO inbox is explicitly platform-owned. It should be configured by
`DURABLE_PO_INBOX_PATH` and accessed through the platform CLI/API or future UI.
Agents must not write `data/po-inbox/`, `.agentic/po-inbox/`, or `po-inbox/`
inside `TARGET_PROJECT_PATH`. If a worker receives an external question file
from a target project, it must import it through the platform PO inbox import
command so schema validation and duplicate detection run before the item becomes
actionable.

Backlog drafts and generated planning bundles default to platform durable data.
They may include references to target project docs, but generated worker
runtime artifacts stay in the platform repository unless the Product Owner
approves a different integration pattern.

## Setup Error Examples

Treat these as setup errors:

1. `TARGET_PROJECT_PATH` points at the boilerplate repository instead of the
   target product checkout.
2. `data/po-inbox/` is created under the target product repository.
3. `data/codex-jobs/` or `data/codex-results/` is created under the target
   product repository.
4. Context packs are generated into target product docs instead of platform
   durable data.
5. Regression evidence or sprint performance logs are stored only in the target
   project without a platform durable reference.

## Worker Context Rule

Workers may read target project preparation docs as source context. Workers
write execution state, generated context packs, logs, questions, and evidence
to platform durable data.

When implementation runs from an isolated worktree, evidence paths in Jira,
pull requests, manifests, and handoffs still point to the platform durable
root, not the temporary worktree. Use these canonical relative paths:

```text
data/agent-logs/<JIRA_ISSUE>/...
data/confluence-mirror/<SPACE_KEY>/<PAGE_ID>.md
```

If an isolated worktree creates local validation evidence before handoff, the
agent must copy or write the final evidence artifact into the platform durable
path and reference that path in Jira. Worktree-local evidence without a
platform durable reference is not enough for sprint closure or later context
generation.

When a target project source document becomes a shared reusable decision, the
agent should propose a Confluence update and keep the local platform mirror in
sync through the documentation workflow.

## First Project Checklist

Before starting agents on a new target project:

1. Create or clone the target product repository.
2. Add the relevant `docs/product/`, `docs/architecture/`, `docs/nfr/`,
   `docs/release-scope/`, `docs/samples/`, and `docs/decisions/` folders.
3. Put Product Owner source material and architecture inputs in those folders.
4. Set `TARGET_PROJECT_PATH` to the target product checkout.
5. Copy `docs/templates/target-project-AGENTS.md` from the boilerplate to
   `${TARGET_PROJECT_PATH}/AGENTS.md` and replace the placeholders.
6. Keep platform durable paths under the boilerplate `data/` directory.
7. Record current Codex limits in `data/codex-limits/`.
8. Run:

```bash
agentic setup validate --project-root . --codex-limits-root data/codex-limits
```

Agents must not start target project work until this setup validation passes or
the Product Owner explicitly records a waiver.

Docker workers validate the platform instruction bundle and generated context
pack before accepting assignments. The exact gate is documented in
`docs/worker-instruction-context-loading.md`.

If the project uses more than one repository, configure the repository lanes in
the platform `.env` before story creation:

```text
TARGET_IMPLEMENTATION_REPOSITORY=<owner>/<repo>
BOILERPLATE_PROCESS_REPOSITORY=<owner>/<repo>
DOCUMENTATION_REPOSITORY=<owner>/<repo>
AUTOMATION_REPOSITORY=<owner>/<repo>
```

Product Planning uses these values to add `Expected Repositories` to stories,
and Developer/Review agents use them to verify Jira-keyed branches, commits,
PRs, and manual Jira PR link fallback comments. The full policy is documented
in `docs/multi-repo-jira-github-traceability.md`.

For PO inbox-specific checks, also run:

```bash
agentic po-inbox validate-paths --target-project-root "$TARGET_PROJECT_PATH"
```
