from dataclasses import replace

from agentic_boilerplate.runtime import (
    RuntimeProofBoundaryEvidence,
    RuntimeProofExecutionMode,
    RuntimeProofRecoveryEvidence,
    RuntimeProofRecoveryKind,
    RuntimeProofRecoveryStatus,
    RuntimeProofStageEvidence,
    RuntimeProofStageStatus,
    UnattendedRuntimeProofReport,
    format_unattended_runtime_proof_validation,
    runtime_proof_validation_to_dict,
    validate_unattended_runtime_proof,
)


def test_live_two_stage_proof_report_is_ready_for_regression() -> None:
    result = validate_unattended_runtime_proof(_valid_report())

    assert result.ready_for_regression is True
    assert result.live_completed_stage_count == 2
    assert result.controlled_completed_stage_count == 0
    assert result.recovery_kind_count == 4
    assert runtime_proof_validation_to_dict(result)["ready_for_regression"] is True
    assert "Runtime proof ready for regression" in format_unattended_runtime_proof_validation(result)


def test_controlled_fixture_stages_cannot_satisfy_live_proof() -> None:
    report = _valid_report(
        stages=(
            _stage("plan", RuntimeProofExecutionMode.CONTROLLED_FIXTURE),
            _stage("docs", RuntimeProofExecutionMode.CONTROLLED_FIXTURE),
        )
    )

    result = validate_unattended_runtime_proof(report)

    assert result.ready_for_regression is False
    assert result.live_completed_stage_count == 0
    assert result.controlled_completed_stage_count == 2
    assert any("controlled fixtures" in issue.message for issue in result.issues)


def test_missing_recovery_path_blocks_regression() -> None:
    report = _valid_report(
        recovery_cases=tuple(
            case for case in _recovery_cases() if case.kind is not RuntimeProofRecoveryKind.PERMISSION_WAIT
        )
    )

    result = validate_unattended_runtime_proof(report)

    assert result.ready_for_regression is False
    assert any("permission_wait" in issue.message for issue in result.issues)


def test_boundary_rejects_api_fallback_and_credential_copy() -> None:
    boundary = replace(
        _boundary(),
        subscription_auth_mode="api_key",
        api_key_fallback_disabled=False,
        credentials_copied_to_container=True,
        approval_bypass_detected=True,
        logs_redacted=False,
        permitted_effects=(),
    )
    result = validate_unattended_runtime_proof(_valid_report(boundary=boundary))
    rendered = format_unattended_runtime_proof_validation(result)

    assert result.ready_for_regression is False
    assert "API-key fallback" in rendered
    assert "credentials" in rendered
    assert "Approval bypass" in rendered
    assert "Proof logs" in rendered
    assert "permitted file/Git/Jira effects" in rendered


def test_not_run_stage_is_reported_instead_of_passed() -> None:
    report = _valid_report(
        stages=(
            _stage("plan", RuntimeProofExecutionMode.LIVE_CODEX),
            replace(_stage("docs", RuntimeProofExecutionMode.LIVE_CODEX), status=RuntimeProofStageStatus.NOT_RUN),
        )
    )

    result = validate_unattended_runtime_proof(report)

    assert result.ready_for_regression is False
    assert any(issue.field.endswith(".status") for issue in result.issues)
    assert result.live_completed_stage_count == 1


def _valid_report(
    *,
    stages: tuple[RuntimeProofStageEvidence, ...] | None = None,
    recovery_cases: tuple[RuntimeProofRecoveryEvidence, ...] | None = None,
    boundary: RuntimeProofBoundaryEvidence | None = None,
) -> UnattendedRuntimeProofReport:
    return UnattendedRuntimeProofReport(
        jira_issue_key="AGENT-967",
        release="1.2.0",
        sprint="R1.2 S8 Runtime Completion",
        tested_main_sha="c64dd17262b9ce76977284d635afe1528489438d",
        fixture_repository="example-org/agentic-runtime-fixture",
        fixture_approved_by="Product Owner",
        startup_commands=("agentic worker run-once --role developer --assignment AGENT-967",),
        configuration_keys=("CODEX_LIMIT_SENTINEL_ENABLED", "CODEX_LIMIT_APP_SERVER_COMMAND"),
        target_paths=("/workspace/project", "/workspace/data"),
        model_route="gpt-5.4/high for runtime worker stage",
        quota_observation_ids=("pre-stage-codex-primary", "post-stage-codex-primary"),
        agiletest_references=("AGENT-T967",),
        stages=stages
        or (
            _stage("plan", RuntimeProofExecutionMode.LIVE_CODEX),
            _stage("docs", RuntimeProofExecutionMode.LIVE_CODEX),
        ),
        recovery_cases=recovery_cases or _recovery_cases(),
        boundary=boundary or _boundary(),
        generated_at="2026-09-12T15:10:00Z",
        evidence_path="data/agent-logs/AGENT-967/runtime-proof-20260912T151000Z.md",
        operator_docs_updated=True,
        broader_chain_follow_up_recorded=True,
    )


def _stage(stage_id: str, mode: RuntimeProofExecutionMode) -> RuntimeProofStageEvidence:
    return RuntimeProofStageEvidence(
        stage_id=stage_id,
        assignment_id=f"assignment-967-{stage_id}",
        codex_job_id=f"job-967-{stage_id}",
        role="developer",
        execution_mode=mode,
        status=RuntimeProofStageStatus.COMPLETED,
        command="scripts/runtime/run_host_codex_supervisor.py run-once --json",
        started_at="2026-09-12T15:00:00Z",
        completed_at="2026-09-12T15:01:00Z",
        result_path=f"data/codex-results/AGENT-967/{stage_id}.json",
        log_path=f"data/agent-logs/AGENT-967/{stage_id}.log",
        checkpoint_path=f"data/agent-state/checkpoints/AGENT-967/{stage_id}.json",
        handoff_reference=f"event-assignment-completed-{stage_id}",
        limit_observation_id=f"limit-observation-{stage_id}",
        codex_invocation_reference=f"codex-subprocess-{stage_id}",
        expected_result="Stage reaches durable completed state.",
        actual_result="Stage completed and emitted assignment_completed event.",
    )


def _recovery_cases() -> tuple[RuntimeProofRecoveryEvidence, ...]:
    return (
        RuntimeProofRecoveryEvidence(
            kind=RuntimeProofRecoveryKind.QUOTA_WAIT,
            status=RuntimeProofRecoveryStatus.PASSED,
            expected_action="Pause before spending quota and resume after fresh allowed gate.",
            actual_action="Paused_limit artifact written, then requeued after gate allowed.",
            failed_request_path="data/codex-results/AGENT-967/failed-quota.json",
            resume_after="2026-09-12T18:00:00Z",
            duplicate_side_effect_prevented=True,
            injected_failure=True,
        ),
        RuntimeProofRecoveryEvidence(
            kind=RuntimeProofRecoveryKind.PO_WAIT,
            status=RuntimeProofRecoveryStatus.PASSED,
            expected_action="Create PO inbox blocker and stop until answered.",
            actual_action="Assignment paused_po and resumed from PO answer reference.",
            duplicate_side_effect_prevented=True,
            injected_failure=True,
        ),
        RuntimeProofRecoveryEvidence(
            kind=RuntimeProofRecoveryKind.PERMISSION_WAIT,
            status=RuntimeProofRecoveryStatus.PASSED,
            expected_action="Stop before unapproved external write.",
            actual_action="Permission blocker recorded with no Git/Jira side effect.",
            failed_request_path="data/codex-results/AGENT-967/failed-permission.json",
            duplicate_side_effect_prevented=True,
            injected_failure=True,
        ),
        RuntimeProofRecoveryEvidence(
            kind=RuntimeProofRecoveryKind.RESTART_RECOVERY,
            status=RuntimeProofRecoveryStatus.PASSED,
            expected_action="Resume from checkpoint after supervisor restart.",
            actual_action="Recovered assignment lock and completed next stage once gates passed.",
            checkpoint_path="data/agent-state/checkpoints/AGENT-967/restart.json",
            preserved_output_path="data/codex-results/AGENT-967/partial.json",
            duplicate_side_effect_prevented=True,
            injected_failure=True,
        ),
    )


def _boundary() -> RuntimeProofBoundaryEvidence:
    return RuntimeProofBoundaryEvidence(
        subscription_auth_mode="chatgpt_subscription",
        api_key_fallback_disabled=True,
        credentials_copied_to_container=False,
        approval_bypass_detected=False,
        logs_redacted=True,
        permitted_effects=("write fixture branch", "write Jira comments", "write durable evidence"),
        unsupported_paths=("full multi-role detached chain not claimed",),
        human_interventions=("PO approved disposable fixture repository",),
    )
