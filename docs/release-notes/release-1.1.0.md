# Release 1.1.0 Notes

Status: release candidate closure package for `AGENT-455`

Release 1.1.0 strengthens the MVP with supervised Codex session-mode workers,
local operator visibility, expanded role instructions, release-track discipline,
first-project setup hardening, and security/credential guardrails.

## Completed Scope

Release/versioning:

1. AGENT-424 - Finalize release track and version policy.
2. AGENT-425 - Align package and release metadata.
3. AGENT-426 - Add release track documentation to operator docs.

First-project onboarding:

1. AGENT-427 - Fix Docker API keepalive stability.
2. AGENT-428 - Add first-project setup validator.
3. AGENT-429 - Add target project preparation layout.

Codex agent instruction package:

1. AGENT-430 - Add root AGENTS.md.
2. AGENT-431 - Add core role instruction files.
3. AGENT-432 - Add expanded role instruction files.
4. AGENT-433 - Add session starter prompt templates.

PO inbox and operator UI:

1. AGENT-434 - Add PO inbox path and schema guard.
2. AGENT-435 - Add local operator UI shell.
3. AGENT-436 - Implement PO inbox list and read UI.
4. AGENT-437 - Implement PO inbox answer and approval actions.
5. AGENT-438 - Add operator status views.
6. AGENT-454 - Define UI/UX design workflow and Figma decision.

Model routing, limits, and session validation:

1. AGENT-439 - Update model/reasoning matrix for expanded roles.
2. AGENT-442 - Add session-mode validation playbook.
3. AGENT-443 - Validate planning-to-development handoff in session mode.
4. AGENT-444 - Validate development/review/test/release session flow.
5. AGENT-445 - Improve Codex limit record CLI/status.

Docker worker requirements and parallel safety:

1. AGENT-440 - Define Docker worker requirements.
2. AGENT-441 - Define Docker credential and volume safety matrix.
3. AGENT-450 - Add parallel session safety policy.
4. AGENT-547 - Docker worker trigger handoff design.
5. AGENT-548 - Design parallel agent workspace isolation.

Security and release handoff:

1. AGENT-451 - Threat model session-mode and future Docker automation.
2. AGENT-452 - Add secret redaction and credential guidance.
3. AGENT-453 - Build Release 1.1 planning handoff bundle.
4. AGENT-483 - Enforce sprint dependency co-scheduling eligibility.
5. AGENT-484 - Automate story acceptance and sprint closure lifecycle.

## Excluded Or Deferred Work

These Release 1.1 backlog items were not approved into executable scope at
closure time and are excluded from the Release 1.1.0 candidate:

1. AGENT-446 - Add blocked/paused assignment status command.
2. AGENT-448 - Implement file-backed assignment lock store.
3. AGENT-449 - Add stale lock release command.
4. AGENT-466 - Release 1.1 Sprint 6 Regression Overview.
5. AGENT-467 - Release 1.1 Sprint 6 Retro And Closure.

Epics AGENT-414 through AGENT-423 remain planning containers in `FUNNEL`; they
are not executable release blockers by themselves.

## Dependency Gate Summary

The release closure story is intentionally last:

1. R11-S01 precedes version-sensitive work.
2. R11-S07 precedes role instruction and session validation work.
3. R11-S11 precedes PO inbox UI and session validation.
4. R11-S12 precedes UI feature stories.
5. R11-S17 and R11-S18 precede the security threat model.
6. R11-S24 precedes any future lock implementation and stale-lock command.
7. R11-S19 precedes session-mode validation stories.
8. R11-S32 precedes local operator UI shell work.
9. R11-S31 is release closure and must be last.

Unapproved Funnel items are listed as excluded work instead of silently blocking
the release candidate.

## Release Acceptance Position

Product Owner can approve Release 1.1.0 as a whole when:

1. Sprint 6 closure package is tested.
2. Final regression evidence is accepted.
3. Excluded work is accepted as deferred.
4. Any Release 1.2 Docker automation follow-ups are reviewed in `FUNNEL`.
