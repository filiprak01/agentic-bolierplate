# Unattended Runtime Proof Gate

Status: Release 1.2 Sprint 8 proof contract for `AGENT-967`.

This guide defines the evidence required before the Release Manager may report
that the bounded host-assisted runtime was proven with real execution.

## Scope

The proof covers one bounded host-side execution slice:

1. Docker or scheduler-side worker state creates durable Codex job requests.
2. A host-side supervisor consumes queued jobs without a manual prompt dispatch.
3. Codex execution uses the host ChatGPT subscription boundary.
4. Results, checkpoints, handoffs, logs, quota observations, and recovery paths
   are durable and traceable.

This proof does not claim the full Planning/Architecture -> Developer -> Review
-> Tester -> Release Manager chain is detached or container-only. That broader
chain remains a separate release gate until every role is proven through the
same kind of evidence.

## Required Proof Package

A proof package is represented by
`UnattendedRuntimeProofReport` in
`agentic_boilerplate.runtime.unattended_runtime_proof`.

It must include:

1. Jira issue key, release, sprint, generated timestamp, and evidence path.
2. Tested `main` SHA.
3. Product Owner approved disposable fixture repository or sample project.
4. Startup commands and configuration keys used for the run.
5. Target paths for source, durable data, workspaces, logs, jobs, results, and
   context packs.
6. Model route and quota observation ids before and after quota-spending stages.
7. AgileTest or Jira evidence references.
8. At least two completed live Codex stage records.
9. Passed recovery evidence for quota wait, PO wait, permission wait, and
   restart recovery.
10. Boundary evidence for subscription authentication, no API-key fallback, no
    Codex credential copying into generic worker containers, no approval bypass,
    redacted logs, and explicit permitted effects.
11. Updated operator/readiness documentation.
12. An explicit follow-up that keeps the full multi-role chain unclaimed until
    separately demonstrated.
13. Environment preflight evidence for Windows/WSL path aliases, Python runtime,
    durable PO inbox root, and durable Codex limit root when applicable.

## Live Versus Controlled Evidence

`RuntimeProofExecutionMode.LIVE_CODEX` is the only execution mode that can count
as live proof. A stage marked as live must provide a Codex invocation reference,
assignment id, Codex job id, result path, log path, checkpoint path, handoff
reference, and limit observation id.

`CONTROLLED_FIXTURE` and `DRY_RUN` evidence may support regression, validator
coverage, and failure-path confidence, but they cannot satisfy the live proof
count. The validator intentionally blocks packages that try to pass with only
controlled stages.

## Recovery Evidence

The proof must show all recovery paths below. Injected failures must be labeled
as injected and kept separate from live endpoint behavior.

1. `quota_wait`: work pauses before spending quota, writes failed request or
   pause artifacts, and resumes only after a fresh allowed gate.
2. `po_wait`: work creates a PO inbox blocker and stops until the answer is
   recorded.
3. `permission_wait`: work stops before an unapproved external write and avoids
   side effects.
4. `restart_recovery`: the supervisor or worker resumes from a checkpoint after
   restart without losing completed output or duplicating side effects.

A NOT RUN, BLOCKED, or FAILED recovery case must remain visible as not passing.
It must not be converted into PASSED during regression.

## Validation

Use `validate_unattended_runtime_proof(report)` before sprint regression. The
result is ready only when:

1. `ready_for_regression` is `true`.
2. `live_completed_stage_count` is at least `2`.
3. `recovery_kind_count` is `4`.
4. No blocking validation issues are present.

Machine output can be serialized with `runtime_proof_validation_to_dict`. Human
and Jira comments can use `format_unattended_runtime_proof_validation`; secret
patterns are redacted before rendering.

## Operator Procedure

1. Confirm the story and fixture are approved in Jira.
2. If running on Windows/WSL, complete
   `docs/windows-wsl-codex-runtime-troubleshooting.md` first when Codex was
   opened through a UNC path or when shell/Python/limit checks fail.
3. Confirm the active path resolves to the canonical Git repository with
   `git rev-parse --show-toplevel`, the intended remote, and a clean or
   intentionally documented working tree.
4. Confirm Python 3.11+ and the source-mode `agentic` CLI command work from the
   same path used by Codex and the host supervisor.
5. Confirm the host session, Docker API/UI, and workers read the same
   `data/po-inbox` and `data/codex-limits` roots.
6. Confirm current Codex limits through the live App Server refresh or a valid
   durable fallback record.
7. Start the configured worker or scheduler path that queues the first bounded
   job.
8. Start the host supervisor command for one stage or bounded loop.
9. Capture startup commands, active branch, tested main SHA, job ids, assignment
   ids, result paths, log paths, checkpoints, handoff events, and quota record
   ids.
10. Repeat for a second bounded stage.
11. Run controlled fault cases for quota, PO blocker, permission blocker, and
    restart recovery without exhausting real quota.
12. Build the proof report and validate it.
13. Attach the report, command log, and validation output to Jira or AgileTest.
14. If validation fails, create or link a bug and block sprint regression.

## Current AGENT-967 Execution Evidence

On 2026-10-11, two Docker-queued bounded stages completed through the background
host supervisor on tested main `a1bf57aed36e636801f3f0ea9f8d8ad0564ac0fd`.
Both used Codex CLI 0.162.1, ChatGPT subscription authentication, the shared
quota skill, and real account-scoped `account/rateLimits/read` observations.
The endpoint reported one weekly pool; no five-hour window was fabricated.

Seven separately labeled controlled scenarios covered quota, PO and permission
waiting, queued restart, claimed-before-dispatch recovery, failed active
execution preservation, and unknown active-job duplicate prevention.
Claimed/unknown execution is not blindly replayed. A failed attempt that had
already written stage-one output was preserved and retried only after verifying
the exact existing output.

Jira traceability: `AGENT-1045` fixes and `AGENT-1070` proof publication.
Raw logs and job/checkpoint/handoff records remain durable local evidence.
The curated [Sprint 8 proof and regression report](reports/index.md)
states the tested boundary, warnings, and remaining release gate.

This is a bounded host-assisted proof, not a full multi-role project-delivery
proof or container-only Codex execution. Quota is enforced before/after each
supervisor stage, not guaranteed before every internal model request. No
release branch, tag, final acceptance, or sprint closure is authorized by this
evidence.

## AGENT-1045 Environment Blocker

`AGENT-1045` tracks a concrete blocker discovered while testing AGENT-967: local
shell execution could not start from the Codex app task opened on the WSL UNC
workspace path. The Product Owner identified a working local workaround by
opening Codex through a Windows directory alias/junction that points to the same
repository.

Resolving this blocker requires both:

1. Documented environment preflight evidence showing the alias path, canonical
   repository, Python executable, PO inbox root, and Codex limit root all point
   to the intended runtime locations.
2. A successful live proof package with two `LIVE_CODEX` stages and required
   recovery evidence.

The alias workaround, Python fix, or durable-path correction is necessary setup
evidence only. It does not satisfy the live proof by itself.
