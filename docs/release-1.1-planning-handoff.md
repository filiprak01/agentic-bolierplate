# Release 1.1 Planning Handoff

Status: Release 1.1 planning handoff bundle for `AGENT-453`.

This bundle gives Product Owner, Orchestrator, Release Manager, and role agents
one stable reference for Release 1.1 scope, sprint slicing, dependencies, model
routing, and current cleanup notes.

## Release Identity

- Release key: `R11`
- Release version: `1.1.0`
- Release name: Session Agent And Operator UX Foundation
- Jira project: `AGENT`
- Default branch: `main`
- Release label: `release-1-1-0`

Release 1.1 improves Codex-session agent reliability, local operator usability,
role instructions, setup hardening, assignment safety, and Docker requirements
discovery.

Release 1.1 does not deliver fully autonomous detached Docker agents. Future
Docker execution remains a later-release capability after session-mode workers
and Product Owner control surfaces are proven.

Release 1.1 planning artifacts belong on `main` and Release 1.1 feature
branches. They must not be added to the `release/1.0.0` MVP snapshot branch
unless the Product Owner explicitly approves a `1.0.x` stabilization backport.

## Product Owner Gates

The Product Owner controls execution by moving Jira issues to
`READY TO START`.

After a sprint scope is approved and stories are `READY TO START`, agents may
continue through implementation, review, merge, testing, regression, retro, and
story acceptance without waiting for story-by-story Product Owner acceptance.

Agents must stop and create a PO inbox item when:

1. A requirement, acceptance criterion, architecture decision, credential, or
   path is missing or ambiguous.
2. A dependency blocks the selected story.
3. Codex limit records are missing, stale, limited, or near exhaustion.
4. Review, testing, security, or regression finds a blocking risk.

## Model Routing

Release 1.1 assumes Product Owner Pro-capacity routing unless the Product Owner
temporarily lowers model or reasoning to conserve limits.

| Role | Model | Reasoning |
| --- | --- | --- |
| Orchestrator / PM | `gpt-5.5` | high |
| Product Planning | `gpt-5.5` | extra high |
| Architecture | `gpt-5.5` | extra high |
| Developer | `gpt-5.4` | high |
| Review | `gpt-5.4` | high |
| Tester / Manual QA | `gpt-5.4-mini` | high |
| Release Manager | `gpt-5.4-mini` | high |
| Platform / DevOps | `gpt-5.4` | high |
| UI/UX | `gpt-5.4` | high |
| Frontend | `gpt-5.4` | high |
| Security | `gpt-5.5` | extra high |
| Docs / Confluence | `gpt-5.4-mini` | high |
| Data / Persistence | `gpt-5.4` | high |

## Epics

| Epic | Jira | Purpose |
| --- | --- | --- |
| R11-E01 | `AGENT-414` | Release and versioning discipline |
| R11-E02 | `AGENT-415` | First-project onboarding hardening |
| R11-E03 | `AGENT-416` | Codex agent instruction package |
| R11-E04 | `AGENT-417` | PO inbox and local operator UI |
| R11-E05 | `AGENT-418` | Expanded agent role catalog |
| R11-E06 | `AGENT-419` | Docker worker requirements discovery |
| R11-E07 | `AGENT-420` | Session-mode worker validation |
| R11-E08 | `AGENT-421` | Limit-aware status and pause/resume UX |
| R11-E09 | `AGENT-422` | Assignment locking and parallel safety |
| R11-E10 | `AGENT-423` | Security and credential governance |

## Sprint Slicing

### Sprint 1 - `R1.1 S1 Startup`

Goal: release line, setup, and agent startup baseline.

Stories:

1. `AGENT-424` - R11-S01 - Finalize release track and version policy.
2. `AGENT-425` - R11-S02 - Align package and release metadata.
3. `AGENT-427` - R11-S04 - Fix Docker API keepalive stability.
4. `AGENT-428` - R11-S05 - Add first-project setup validator.
5. `AGENT-430` - R11-S07 - Add root `AGENTS.md`.
6. `AGENT-433` - R11-S10 - Add session starter prompt templates.
7. `AGENT-453` - R11-S30 - Build Release 1.1 planning handoff bundle.
8. `AGENT-456` - R11-SP1-REG - Sprint 1 regression.
9. `AGENT-457` - R11-SP1-RETRO - Sprint 1 retro and closure.

### Sprint 2 - `R1.1 S2 Roles Inbox`

Goal: role instructions, PO inbox guard, model routing, and UI/UX handoff.

Stories:

1. `AGENT-429` - R11-S06 - Add target project preparation layout.
2. `AGENT-431` - R11-S08 - Add core role instruction files.
3. `AGENT-432` - R11-S09 - Add expanded role instruction files.
4. `AGENT-434` - R11-S11 - Add PO inbox path and schema guard.
5. `AGENT-439` - R11-S16 - Update model/reasoning matrix.
6. `AGENT-450` - R11-S27 - Add parallel session safety policy.
7. `AGENT-454` - R11-S32 - Define UI/UX design workflow and Figma decision.
8. `AGENT-458` - R11-SP2-REG - Sprint 2 regression.
9. `AGENT-459` - R11-SP2-RETRO - Sprint 2 retro and closure.

Sprint 2 also delivered pulled-forward process work:

1. `AGENT-447` - R11-S24 - Design assignment lock model.
2. `AGENT-483` - R11-S33 - Enforce sprint dependency co-scheduling eligibility.
3. `AGENT-484` - R11-S34 - Automate story acceptance and sprint closure
   lifecycle.

### Sprint 3 - `R1.1 S3 Operator UI`

Goal: local operator UI and limit status.

Stories:

1. `AGENT-426` - R11-S03 - Add release track documentation to operator docs.
2. `AGENT-435` - R11-S12 - Add local operator UI shell.
3. `AGENT-436` - R11-S13 - Implement PO inbox list and read UI.
4. `AGENT-437` - R11-S14 - Implement PO inbox answer and approval actions.
5. `AGENT-445` - R11-S22 - Improve Codex limit record CLI/status.
6. `AGENT-460` - R11-SP3-REG - Sprint 3 regression.
7. `AGENT-461` - R11-SP3-RETRO - Sprint 3 retro and closure.

### Sprint 4 - `R1.1 S4 Sec Docker`

Goal: status views, Docker requirements, assignment safety, and security.

Stories:

1. `AGENT-438` - R11-S15 - Add operator status views.
2. `AGENT-440` - R11-S17 - Define Docker worker requirements.
3. `AGENT-441` - R11-S18 - Define Docker credential and volume safety matrix.
4. `AGENT-447` - R11-S24 - Design assignment lock model.
5. `AGENT-451` - R11-S28 - Threat model session-mode and future Docker
   automation.
6. `AGENT-462` - R11-SP4-REG - Sprint 4 regression.
7. `AGENT-463` - R11-SP4-RETRO - Sprint 4 retro and closure.

Post-planning additions that require PO review before execution:

1. `AGENT-547` - R11-S35 - Design Docker worker trigger handoff mechanism.
2. Parallel workspace isolation is a Release 1.1 planning candidate when the
   Product Owner creates or approves the related Jira story.

### Sprint 5 - `R1.1 S5 Validation`

Goal: session-mode validation and security hardening.

Stories:

1. `AGENT-442` - R11-S19 - Add session-mode validation playbook.
2. `AGENT-443` - R11-S20 - Validate planning-to-development handoff in session
   mode.
3. `AGENT-444` - R11-S21 - Validate development/review/test/release session
   flow.
4. `AGENT-452` - R11-S29 - Add secret redaction and credential guidance.
5. `AGENT-464` - R11-SP5-REG - Sprint 5 regression.
6. `AGENT-465` - R11-SP5-RETRO - Sprint 5 retro and closure.

### Sprint 6 - `R1.1 S6 Closure`

Goal: assignment status commands, lock operations, and final release closure.

Stories:

1. `AGENT-446` - R11-S23 - Add blocked/paused assignment status command.
2. `AGENT-448` - R11-S25 - Implement file-backed assignment lock store.
3. `AGENT-449` - R11-S26 - Add stale lock release command.
4. `AGENT-455` - R11-S31 - Final Release 1.1 regression and retro package.
5. `AGENT-466` - R11-SP6-REG - Sprint 6 regression.
6. `AGENT-467` - R11-SP6-RETRO - Sprint 6 retro and closure.

## Dependency Rules

1. `AGENT-424` precedes all version-sensitive stories.
2. `AGENT-430` precedes role instruction and session validation stories.
3. `AGENT-434` precedes PO inbox UI and session validation.
4. `AGENT-435` precedes UI feature stories.
5. `AGENT-440` and `AGENT-441` precede the security threat model.
6. `AGENT-447` precedes lock implementation, stale lock commands, trigger
   design, and parallel workspace design.
7. `AGENT-442` precedes session-mode validation stories.
8. `AGENT-454` precedes local operator UI shell work.
9. `AGENT-453` blocks `AGENT-455` final Release 1.1 closure.

The scheduler must co-schedule or reject blocked stories using
`docs/sprint-dependency-coscheduling.md`; it must not leave blocked stories in
an executable sprint without their required blockers.

## Current Cleanup Notes

This handoff exists because the release board accumulated historical sprint
membership drift while dogfooding the process.

Known cleanup points:

1. `AGENT-453` was planned in Sprint 1, became blocked by later setup work, and
   must be completed before final release closure.
2. `AGENT-433` is a Sprint 1-labeled story that may appear in Sprint 2 in Jira.
3. `AGENT-447` was pulled forward and delivered for Sprint 2 dependency needs
   but may still appear in Sprint 4 planning views.
4. `AGENT-483` was delivered as a Sprint 2 retro follow-up and may not have a
   sprint assignment after board cleanup.

These are bookkeeping issues, not missing delivery evidence, unless a future
audit finds a non-accepted story without evidence.

## MVP Dogfooding Decisions

Release 1.1 includes fixes and improvements discovered while testing the MVP on
the first real target project.

Accepted dogfooding decisions:

1. Keep Release 1.1 focused on Codex session-mode agents, operator usability,
   role instructions, and setup safety before detached Docker execution.
2. Use the PO inbox as the durable source of truth for blocking questions, but
   make it easier to use through the local operator UI.
3. Keep platform runtime state under durable platform data folders, not inside
   target project source folders.
4. Require agents to check Codex limit records before quota-spending work.
5. Prefer sprint-level Product Owner acceptance after the PO moves stories to
   `READY TO START`; do not stop after every story unless a blocker appears.
6. Keep regression, retro, and release evidence durable and Confluence-ready.
7. Use story-backed changes, PR visibility, and test evidence for process
   changes as well as code changes.
8. Defer live autonomous Docker workers until the session-mode process is
   validated and the trigger/workspace requirements are designed.

## Durable Paths

Release 1.1 agents should treat these folders as durable coordination state:

1. `data/po-inbox`.
2. `data/agent-logs`.
3. `data/agent-state`.
4. `data/codex-limits`.
5. `data/codex-jobs`.
6. `data/codex-results`.
7. `data/context-packs`.

Target project folders should contain target project code and project-specific
preparation inputs, not platform runtime state.

Backlog drafts, planning bundles, context packs, and generated planning
artifacts default to platform durable data. A tracked documentation bundle may
mirror the same decisions for versioned release visibility, but durable runtime
state remains outside target project source folders.

## Next Execution Recommendation

After this handoff bundle is merged and tested:

1. Complete or clean up Sprint 3 closure if `AGENT-460` and `AGENT-461` are
   already accepted.
2. Move into Sprint 4 only after the Product Owner confirms which Sprint 4
   additions are accepted into scope.
3. Start Sprint 4 with dependencies first:
   `AGENT-440`, `AGENT-441`, and any not-yet-delivered assignment safety work.
4. Keep `AGENT-455` blocked until all selected Release 1.1 implementation
   stories, regression tasks, and retro tasks are complete.

## Handoff Consumers

Use this bundle for:

1. Orchestrator / PM sprint diagnosis.
2. Release Manager scope selection.
3. Product Planning context pack generation.
4. Architecture review of Release 1.2 Docker automation candidates.
5. Product Owner high-level release review.
