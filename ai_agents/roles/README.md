# Core Agent Role Instructions

These files are the session-mode entry points for the current MVP worker roles.
Each Codex session should load `AGENTS.md` first, then the matching role file,
then the referenced workflow docs.

Release 1.1 supports Codex session-mode workers and Docker dry-run/runtime
foundations. These role files do not describe detached autonomous Docker Codex
execution.

## Core Roles

1. `orchestrator.md`
2. `architecture.md`
3. `product_planning.md`
4. `developer.md`
5. `review.md`
6. `tester.md`
7. `release_manager.md`

## Expanded Release 1.1 Roles

1. `frontend.md`
2. `ui_ux.md`
3. `security.md`
4. `docs_confluence.md`
5. `devops_platform.md`
6. `data_persistence.md`

Frontend, UI/UX, Security, and Docs/Confluence roles are mandatory for Release
1.1 validation. DevOps/Platform and Data/Persistence roles are included for
local runtime, durable data, and future project hardening.

## Common Rules

Every role must:

1. Load `.agents/skills/codex-quota-guard/SKILL.md` from the platform
   repository before and after visible stages that can spend Codex quota.
2. Check Jira status and dependency eligibility before starting a story.
3. Use the PO inbox for blocking business, architecture, scope, credential,
   or release questions.
4. Write durable evidence for non-simple work.
5. Keep local files and Confluence-aligned documentation separate from
   role-specific notes.
6. Keep quota guard decisions scoped to the current project identity, durable
   store, account scope, and bucket; do not carry project-specific memory or
   credentials between target projects.
7. Submit sprint retro input to the active sprint retro intake item when one
   exists, using separate airlines-project and agent/process sections.
