# Target Project Agent Instructions

This file is the target-project starter template copied from the agentic
boilerplate. Replace bracketed placeholders before starting project work.

## Project Identity

- Project name: `[PROJECT_NAME]`
- Jira project key: `[JIRA_PROJECT_KEY]`
- Jira board id: `[JIRA_BOARD_ID]`
- Repository: `[GITHUB_REPOSITORY]`
- Default branch: `main`
- Platform durable root: `[PLATFORM_DURABLE_ROOT]`

## Product Owner Control

The Product Owner owns business decisions, sprint scope approval, release
approval, and unclear requirement resolution.

If requirements, acceptance criteria, architecture, credentials, paths,
dependencies, release decisions, or non-functional requirements are missing or
unclear, create a PO inbox item through the configured platform CLI/API and
stop the work until the answer is recorded.

## Source Context

Load target-project context from these project folders when present:

- `docs/product/`
- `docs/architecture/`
- `docs/nfr/`
- `docs/release-scope/`
- `docs/samples/`
- `docs/decisions/`

Generated worker state, PO inbox messages, context packs, Codex jobs/results,
limits, logs, sprint records, and shared publication mirrors belong in the
agentic boilerplate durable data root, not in this target project checkout.

## Required Worker Handoff

Every executable Jira story must have:

1. Jira status `READY TO START`.
2. Resolved dependency links.
3. A generated context pack under platform durable storage.
4. Role instructions from the agentic boilerplate `ai_agents/roles/` folder.
5. A feature branch named `feature/{JIRA_KEY}-{short-slug}` for code work.
6. Validation evidence written to the platform durable evidence path.

## Local Safety

Do not commit secrets. Do not create hidden runtime state inside this target
project unless the Product Owner explicitly approves it. Keep process state in
the platform durable data root so workers can stop, resume, and report without
losing context.
