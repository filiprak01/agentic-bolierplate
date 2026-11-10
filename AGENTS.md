# Agentic Boilerplate - Codex Instructions

## Product Owner Control

The Product Owner is the business and process owner.

Do not make business decisions silently. If requirements, acceptance criteria,
architecture, non-functional requirements, credentials, target paths, Jira
workflow details, or release decisions are missing or imprecise, create a
Product Owner inbox question and wait for the answer to be documented.

## Jira Workflow

Default dogfooding project key: `AGENT`.

Executable work starts only after the Product Owner moves the Jira story, bug,
or task to `READY TO START`.

Workflow statuses:

1. `FUNNEL`
2. `READY TO START`
3. `IN PROGRESS`
4. `DEV COMPLETED`
5. `IN TESTING`
6. `TEST COMPLETED`
7. `ACCEPTED/DONE`

Agents must check Jira dependency links before starting work. A story is not
development-eligible while unresolved prerequisite links remain. A prerequisite
can unblock dependent development when it is merged to `main`, is in
`TEST COMPLETED`, and has no unresolved blocking bugs.

Dependency direction is always written and read as `blocker -> blocked`. If
story `X` depends on story `Y`, then Jira must store `Y blocks X`. Agents must
not create or repair dependency links as `X blocks Y`, and must stop for a
recorded blocker/PO confirmation when a live link appears reversed or cyclic.

`ACCEPTED/DONE` is the Product Owner sprint or release acceptance gate.

## Git And PR Flow

Default branch: `main`.

Feature branch format:

```text
feature/{JIRA_KEY}-{short-slug}
```

Agents must not implement or edit project files directly on `main`. Before
changing files for Jira-backed work, create or check out a dedicated working
branch from the correct base branch, normally
`feature/{JIRA_KEY}-{short-slug}`. Release and hotfix work must start from the
configured release or hotfix base and use a dedicated child branch for the
specific Jira issue.

Before implementation, create development subtasks under every code
implementation Jira story or bug unless the Product Owner or Orchestrator has
explicitly approved and recorded a no-subtask exception on the parent issue.
Each subtask must state its objective, affected area, validation expectation,
and completion evidence. Work one subtask at a time, commit each completed
stage, update the matching subtask with what changed, and move the subtask to
the closest done status only after relevant validation passes.

Create the pull request after development subtasks are complete. The Jira
handoff comment must list the created subtasks or name the approved no-subtask
exception. Review Agent uses a diff-first review scope and merges clean PRs
after checks and review pass. Tester Agent tests after merge to `main`.

Review Agent reports merge conflicts back to the Developer Agent that owns the
branch. Review Agent does not resolve conflicts directly.

For multi-repository work, use the repository lanes documented in
`docs/multi-repo-jira-github-traceability.md`. Each affected repository must
have Jira-keyed branches, commits, pull request titles, pull request bodies,
and a Jira-visible PR link. When Jira development-panel visibility is not
expected for a repository, add the explicit Jira PR link fallback comment before
moving the story to `DEV COMPLETED`.

## PO Inbox Rule

The local PO inbox is the source of truth for blocking questions, approvals,
assumption confirmations, and rejected/answered decisions when the UI is not
available.

Use the CLI documented in `docs/po-inbox-cli.md` and the schema documented in
`docs/po-inbox-schema.md`. Durable inbox storage is configured by
`DURABLE_PO_INBOX_PATH`.

Do not bury unresolved Product Owner questions only in chat, PR comments, or
local notes. Create or update a durable inbox item and reference the related
Jira issue when applicable.

## UI Design Gate

UI implementation work must not start from a visual or interaction assumption.
For every UI-facing implementation story, Product Planning or UI/UX work must
create or reference a dedicated design story first.

The design story must produce reviewable artifacts such as Figma frames, Canva
review designs, exported snapshots, or local HTML mockups. The design story is
complete only after the Product Owner accepts the design or documents an
explicit override.

Frontend implementation stories must include a `Design Reference` section with
the accepted design story key, artifact link or path, Product Owner acceptance
reference, and constraints. Jira `Blocks` links must make the accepted design
story block the implementation story.

If a Frontend Agent or Scheduler cannot find an accepted design reference, it
must stop and create a Product Owner inbox question instead of inventing the UI.

## Multi-Project Agent Context

Release 1.2 supports a shared pool of role workers across multiple target
projects only when each assignment is isolated.

Default policy: use pooled role capacity with one project-scoped assignment per
worker at a time. A worker must receive exactly one project identity, one Jira
issue, one context pack, one durable PO inbox namespace, and one isolated
workspace for the assignment it is currently handling.

Before accepting a new project assignment, the worker must release or reset all
project-specific assumptions, unresolved questions, credentials, local paths,
repository state, and conversation-derived context from the previous
assignment. Shared role instructions and boilerplate process docs may be reused;
target-project requirements must be loaded from the new assignment's context
pack and durable records.

Use dedicated per-project agents instead of pooled capacity when the project is
sensitive, has unusual architecture or credentials, requires long-running PO
collaboration, has strict operational separation, or when context reset cannot
be proven.

Scheduler and assignment records must show the current `project_id`,
`project_name`, `project_root`, `repository`, and `jira_project_key` so the
Product Owner can see which project each pooled worker is handling.

## Stacked PR Visibility

Stacked or parallel sprint work must be driven by
`docs/stacked-pr-sprint-path-resolver.md` and surfaced through
`docs/stacked-pr-operator-visibility.md`. Assignment metadata is the
operator-visible source for stack id, lane id, layer order, next agent,
blocked/stale state, and evidence finality. If the stack metadata is missing,
stale, or conflicts with Jira or GitHub, stop and create a PO inbox blocker.

## Session Mode And Docker Boundary

Release 1.1 supports Codex session-mode workers and Docker dry-run/runtime
foundations.

Current supported execution:

1. Codex sessions perform planning, implementation, review, testing, and
   release-manager work with the Product Owner supervising model/reasoning
   switches.
2. Docker Compose starts local service and worker containers for environment,
   durability, registry, assignment, and dry-run validation.
3. In-container workers can register, poll one assignment, check durable Codex
   limit state, and write logs.
4. Live Codex-backed execution remains delegated to the host-side/session
   boundary documented in `docs/host-side-codex-runner.md`.

Detached, fully autonomous Docker agents that execute Codex work without an
active Codex session are not Release 1.1 scope. Do not present them as
available capability until a later release implements and tests that boundary.

## Runtime Path And Setup Preflight

Before diagnosing Jira, GitHub, PO inbox, Python, or Codex quota as unavailable,
verify the runtime path layer. On Windows/WSL, opening Codex from a UNC path such
as `\\wsl.localhost\Ubuntu\...` can fail before local shell startup and can make
healthy credentials or durable limit records look broken.

Use `docs/windows-wsl-codex-runtime-troubleshooting.md` when local shell,
Python, PO inbox, Docker API, or Codex limit commands fail unexpectedly. The
validated workaround is to open Codex through a Windows directory
alias/junction to the same repository, then verify canonical Git root, remote,
Python 3.11+, and shared durable `data/po-inbox` / `data/codex-limits` paths.

If the path preflight fails, stop before claiming Jira work or spending Codex
quota. Record a path/setup blocker instead of reclassifying it as a Jira,
GitHub, or subscription-limit failure.

## Codex Limits

Before starting or resuming a story, stage, retry, role switch, or worker
action that can spend Codex quota, load the repository-scoped guard skill from
`.agents/skills/codex-quota-guard/SKILL.md` and use it to refresh and inspect
the durable Codex limit gate. If the selected observation is missing, limited,
stale, invalid, ambiguous, or recommends waiting/downgrading, pause safely and
ask the Product Owner or host-owned guard for updated limit input.

Use:

```bash
agentic codex-limits refresh --codex-limits-root data/codex-limits
agentic codex-limits latest --json --codex-limits-root data/codex-limits
agentic setup validate --project-root . --codex-limits-root data/codex-limits
```

Session-mode skill checks are best-effort checkpoints between visible stages;
mandatory runtime enforcement remains in the scheduler and host-side runner
before they issue Codex requests. The guard skill cannot interrupt every
internal model request, reserve quota for a whole story, or schedule background
wakeups.

When a session works inside a target-project worktree, load the shared guard
skill from the platform repository path. Repository discovery does not cross
into unrelated repositories automatically. Do not copy Codex credentials,
login folders, target-project secrets, unresolved assumptions, or
project-specific memory with the skill.

Role model/reasoning routing is documented in
`docs/story-complexity-model.md`, `docs/codex-model-routing.md`, and
`docs/codex-subscription-setup.md`. When the selected route differs from the
active Codex session, ask the Product Owner to switch manually before starting
the next work item. When runtime discovery is available, use Codex App Server
JSON-RPC `model/list` plus the quota guard result instead of stale docs,
undocumented gRPC calls, or UI scraping. Backbone Product Planning,
Architecture, and Security work must fail closed instead of silently
falling back to a cheaper model.

## Role-Specific Context

Load this file first, then load the matching core role instruction from
`ai_agents/roles/`, then use the role-specific documentation below:

1. Orchestrator: `ai_agents/roles/orchestrator.md`,
   `docs/scheduler-approved-scope-assignment.md`,
   `docs/role-specific-jira-pickup-profiles.md`,
   `docs/dependency-eligibility-checker.md`,
   `docs/definition-of-ready-gate.md`,
   `docs/stacked-pr-sprint-path-resolver.md`,
   `docs/stacked-pr-operator-visibility.md`
2. Product Planning: `ai_agents/roles/product_planning.md`,
   `docs/guided-release-intake.md`, `docs/backlog-draft-workflow.md`,
   `docs/jira-story-creation-workflow.md`, `docs/context-pack-generator.md`,
   `docs/ui-design-gate.md`,
   `docs/documentation-to-backlog-traceability-audit.md`
3. Architecture: `ai_agents/roles/architecture.md`,
   `docs/guided-release-intake.md`, `docs/architecture-templates.md`, `docs/nfr-workflow.md`,
   `docs/documentation-governance.md`, `docs/infrastructure-planning-template.md`
4. Developer: `ai_agents/roles/developer.md`,
   `docs/role-specific-jira-pickup-profiles.md`,
   `docs/developer-subtask-workflow.md`,
   `docs/developer-branch-commit-validation-workflow.md`,
   `docs/developer-pull-request-creation-workflow.md`,
   `docs/stacked-pr-sprint-path-resolver.md`,
   `docs/stacked-pr-operator-visibility.md`
5. Review: `ai_agents/roles/review.md`,
   `docs/role-specific-jira-pickup-profiles.md`,
   `docs/review-agent-pr-workflow.md`, `docs/review-records.md`,
   `docs/stacked-pr-sprint-path-resolver.md`,
   `docs/stacked-pr-operator-visibility.md`
6. Tester: `ai_agents/roles/tester.md`,
   `docs/role-specific-jira-pickup-profiles.md`,
   `docs/tester-manual-test-workflow.md`,
   `docs/tester-bug-retest-workflow.md`,
   `docs/test-evidence-artifact-workflow.md`,
   `docs/stacked-pr-sprint-path-resolver.md`,
   `docs/stacked-pr-operator-visibility.md`
7. Release Manager: `ai_agents/roles/release_manager.md`,
   `docs/role-specific-jira-pickup-profiles.md`,
   `docs/release-manager-scope-selection.md`,
   `docs/regression-manifest-builder.md`,
   `docs/sprint-regression-overview-workflow.md`,
   `docs/sprint-closure-publication-workflow.md`,
   `docs/stacked-pr-sprint-path-resolver.md`,
   `docs/stacked-pr-operator-visibility.md`,
   `docs/documentation-to-backlog-traceability-audit.md`
8. Platform/Scheduler: `docs/docker-worker-readiness.md`,
   `docs/worker-startup-diagnostics.md`,
   `docs/windows-wsl-codex-runtime-troubleshooting.md`,
   `docs/scheduler-approved-scope-assignment.md`,
   `docs/role-specific-jira-pickup-profiles.md`,
   `docs/dependency-eligibility-checker.md`,
   `docs/definition-of-ready-gate.md`,
   `docs/codex-limit-availability.md`, `docs/codex-model-routing.md`,
   `docs/ui-design-gate.md`,
   `docs/host-codex-supervisor.md`,
   `docs/infrastructure-planning-template.md`,
   `docs/stacked-pr-sprint-path-resolver.md`,
   `docs/stacked-pr-operator-visibility.md`

Expanded Release 1.1 role instructions live beside the core roles:
`ai_agents/roles/frontend.md`, `ai_agents/roles/ui_ux.md`,
`ai_agents/roles/security.md`, `ai_agents/roles/docs_confluence.md`,
`ai_agents/roles/devops_platform.md`, and
`ai_agents/roles/data_persistence.md`.

Short copy/paste prompts for starting role-specific Codex sessions live in
`ai_agents/session_starters/README.md`.

## Documentation Traceability And Evidence

Approved Markdown and configured publication targets hold AI/operator
knowledge for agents. Actionable implementation or reusable process changes
must stay traceable to Jira by direct issue reference, draft backlog candidate,
documented doc-only/deferred/rejected disposition, or PO inbox decision.

Use `docs/documentation-to-backlog-traceability-audit.md` before backlog
creation and release planning when scope comes from docs or Confluence mirrors.

Keep shared content separate from role-specific notes. When reusable decisions
are learned during work, propose shared documentation updates and create Jira
backlog candidates when implementation is required.

For non-simple stories, create timestamped Markdown evidence under durable
local storage and reference it in Jira.
