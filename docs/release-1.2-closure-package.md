# Release 1.2 Closure Package

This package is the Release Manager handoff for Product Owner review before
Release 1.2 branch/tag creation.

## Closure Status

Product Owner release approval was received on 2026-10-17. The final closure
record is
[`docs/reports/1.2.0/R12-S8/release-closure-20261017.md`](reports/index.md).
The branch/tag gate passed with the AgileTest publication limitation retained
as an explicit non-blocking warning.

## Required Inputs

1. Sprint regression overview with no unresolved blocking bugs.
2. Story evidence for all completed Release 1.2 stories.
3. AgileTest Test/Execution references for reusable regression coverage.
4. Accepted Product Owner decisions or PO inbox blockers resolved.
5. GitHub PR links and merge SHAs for source changes.
6. Release branch/tag checklist from the regression-gated automation planner.
7. Runtime proof package for `AGENT-967` when Sprint 8 claims bounded
   unattended execution passed.
8. Updated `README.md` and `CLAUDE.md` with Product Owner startup guidance,
   current capability boundaries, latest-release switching, Docker setup,
   agent setup, credential setup, and subscription behavior.
9. Windows/WSL path, Python executable, PO inbox root, and Codex limit root
   verification when the release proof or operator setup ran from Windows.

## Runtime Completion Evidence

Sprint 8 runtime-completion closure must include the proof contract from
`docs/unattended-runtime-proof.md` and the troubleshooting path from
`docs/windows-wsl-codex-runtime-troubleshooting.md`.

The Release Manager must not mark live unattended runtime proof as passed unless
`validate_unattended_runtime_proof` returns `ready_for_regression=true` with at
least two completed live Codex stages, all four required recovery kinds, and the
subscription-auth/no-credential-copying boundary checks passing. Controlled
fixtures, dry runs, CI-only validator coverage, or a fixed Windows path alias are
supporting evidence only.

A Windows directory alias/junction, Python PATH fix, or durable root correction
can unblock the environment, but it is not itself proof that Codex executed an
unattended live stage.

## Release Evidence Index

For each sprint included in Release 1.2, the closure package must reference:

1. Sprint goal and included Jira issues.
2. Story evidence paths.
3. Regression evidence path.
4. Retro/closure evidence path.
5. PR URLs and merge SHAs.
6. Blocking bugs resolved during the sprint.
7. Accepted follow-up stories created from retro or dogfooding findings.

Sprint 6 evidence must include the hardening stories `AGENT-644`, `AGENT-645`,
`AGENT-646`, and `AGENT-751` so release closure can prove the documentation
archive policy, branch/tag automation, detached worker pilot evidence, and Review
Agent approval fallback diagnostics were retained through later closure edits.

Sprint 8 must additionally reference `AGENT-967` proof evidence and any open or
resolved blocker such as `AGENT-1045`.

## Closure Checklist

1. Confirm every included Release 1.2 story is in `TEST COMPLETED` or later.
2. Confirm every blocking bug is resolved, accepted, or explicitly deferred by
   Product Owner decision.
3. Run release regression and publish the evidence.
4. Run sprint/release retro and capture only immediate process changes in the
   active sprint; future improvements go to `FUNNEL`.
5. Confirm README and CLAUDE handoff docs are current and do not overclaim
   unproven Docker/Codex capability.
6. Confirm operator setup evidence covers Docker API/UI, target project path,
   durable data roots, Python version, Git repository identity, and Codex
   subscription boundary.
7. Build the release branch/tag checklist after regression passes.
8. Publish release notes, operator guide, migration guide, README/CLAUDE links,
   and closure summary to GitHub Pages.
9. Product Owner performs release-level acceptance after the full release is
   ready.

## Branch/Tag Gate

The release branch/tag automation must not emit executable commands while any
of these are true:

1. Regression has not passed.
2. Regression evidence path is missing.
3. Blocking bugs remain unresolved.
4. Release scope has no included work items.
5. Sprint 8 claims live unattended runtime proof but the AGENT-967 proof package
   is missing or not ready for regression.
6. README or CLAUDE setup guidance still describes future work as available
   capability.
7. Windows/WSL path, Python, PO inbox, or Codex limit root failures remain open
   for the environment used to produce the release proof.

When the gate passes, the Release Manager may proceed with the generated
branch/tag checklist.
