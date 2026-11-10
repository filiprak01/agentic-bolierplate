# Release 1.2 Operator Guide

Release 1.2 turns the boilerplate into a locally operable platform for
session-mode agents, Docker dry-run workers, the operator UI/API, evidence
publication, and release hardening.

## Start Order

1. Prepare the target project root outside generated worker workspaces.
2. Fill `.env` with project-specific Jira, GitHub, durable path, and optional
   provider settings.
3. Record current Codex limit availability by running the shared quota
   guard refresh, or record a labeled manual fallback, before starting worker
   actions.
4. Start the operator API/UI with the `operator` profile.
5. Start role workers only after stories are in `READY TO START`.
6. Keep Product Owner decisions in the PO inbox and Jira workflow.

## Required Local Boundaries

1. Source repo root: the project repository being worked on.
2. Durable data root: PO inbox, context packs, agent state, logs, Codex jobs,
   and evidence.
3. Worker workspace root: isolated worktrees/clones outside the source repo.
4. Documentation source: approved Markdown in `docs/`.
5. Published docs/reports: GitHub Pages by default.

The worker workspace root must not be inside the mutable source checkout.
The detached worker pilot for `AGENT-646` verified this gate by first failing
with `workspace-reuses-source`, then passing with an external workspace root.

## Windows WSL Path Preflight

When Codex is opened from a WSL UNC path such as
`\\wsl.localhost\Ubuntu\home\...`, local helper setup can fail before a shell
starts. This can make unrelated checks look broken, including Python discovery,
PO inbox access, and durable Codex limit reads.

Before a live runtime proof, host-side runner stage, or Docker worker diagnosis
on Windows, run the path preflight in
`docs/windows-wsl-codex-runtime-troubleshooting.md`:

1. Open Codex through the Product Owner validated Windows directory
   alias/junction path, not the failing UNC path.
2. Verify `git rev-parse --show-toplevel`, `git remote -v`, and
   `git status --short` resolve to the canonical repository.
3. Verify Python 3.11+ and `PYTHONPATH=src python -m agentic_boilerplate.cli`
   work from that same path.
4. Verify the session and Docker/API stack read the same `data/codex-limits` and
   `data/po-inbox` roots.

A failed path preflight blocks assignment pickup and live-proof claims. Record
the blocker as a path/setup diagnostic; do not report it as a Jira, GitHub, or
subscription-limit failure unless those probes fail after the path is fixed.

## Codex Quota Guard Operation

The platform repository provides
`.agents/skills/codex-quota-guard/SKILL.md`. Operators should make sure
session-mode roles load it from the platform repo, even when the active source
files live in a separate target-project worktree. Repository discovery does not
cross unrelated checkouts automatically.

Before assignments, retries, resumes, or visible stages that spend Codex quota,
use live `agentic codex-limits refresh` with the configured durable root,
account scope, and bucket. If the worker is hosted or containerized without
host Codex auth, have it request the host-owned guard decision and wait for the
durable result; do not mount Codex login folders into generic workers.

After completion, failure, or checkpoint, save results first, refresh quota
again, and write evidence with the decision id, source, UTC timestamp, store,
account scope, bucket/window, remaining/reset, action/reason, project, issue,
role, stage, workspace, branch, and result references. If the post-stage
refresh fails, mark quota unknown and block the next stage only.

## Unattended Runtime Proof

`AGENT-967` uses `docs/unattended-runtime-proof.md` as the Release 1.2 proof
contract for bounded host-assisted runtime execution.

Before sprint regression can claim this proof passed, the Release Manager or
Tester must validate an `UnattendedRuntimeProofReport` with
`validate_unattended_runtime_proof`. The report must include two completed live
Codex stages, quota/PO/permission/restart recovery evidence, subscription-auth
boundary checks, redacted logs, and traceable Jira/AgileTest references.
Controlled fixtures and dry runs can support confidence, but they cannot count
as live proof. If the proof package is missing live stages or reports NOT RUN,
BLOCKED, or FAILED evidence, keep the story blocked and create or link bugs as
needed.

## Daily Operation

1. Use Jira as the sprint/status board.
2. Use the operator UI for PO inbox and runtime visibility.
3. Use `.agents/skills/codex-quota-guard/SKILL.md` and
   `agentic codex-limits refresh` before and after Codex-spending work.
4. Use worker status and assignment lock commands when work looks stuck.
5. Use GitHub pull requests for source changes.
6. Use AgileTest/Test evidence for regression and story validation.

## Release Manager Controls

The Release Manager can prepare a release branch/tag checklist after regression
passes with the release branch automation planner. The automation remains gated:
no executable commands are emitted when regression fails, evidence is missing,
or blocking bugs exist.

## Evidence

Story test evidence, regression overviews, retros, closure notes, and partner
reports stay in durable local storage and can be published to GitHub Pages when
approved for the intended audience.
