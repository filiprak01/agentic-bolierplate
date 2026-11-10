"""Validation contract for bounded unattended runtime proof packages.

This module intentionally separates live Codex-backed proof from controlled
fixtures. A fake executor can validate the reporting shape, but it cannot satisfy
AGENT-967's live proof gate.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from agentic_boilerplate.domain import redact_failed_request_text


class RuntimeProofExecutionMode(str, Enum):
    """How a bounded runtime stage was executed."""

    LIVE_CODEX = "live_codex"
    CONTROLLED_FIXTURE = "controlled_fixture"
    DRY_RUN = "dry_run"


class RuntimeProofStageStatus(str, Enum):
    """Scenario-level result for one bounded stage."""

    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    NOT_RUN = "not_run"


class RuntimeProofRecoveryKind(str, Enum):
    """Recovery behavior that must be explicitly evidenced."""

    QUOTA_WAIT = "quota_wait"
    PO_WAIT = "po_wait"
    PERMISSION_WAIT = "permission_wait"
    RESTART_RECOVERY = "restart_recovery"


class RuntimeProofRecoveryStatus(str, Enum):
    """Scenario-level result for recovery validation."""

    PASSED = "passed"
    FAILED = "failed"
    NOT_RUN = "not_run"


@dataclass(frozen=True)
class RuntimeProofStageEvidence:
    """Evidence for one bounded host-side Codex stage."""

    stage_id: str
    assignment_id: str
    codex_job_id: str
    role: str
    execution_mode: RuntimeProofExecutionMode
    status: RuntimeProofStageStatus
    command: str
    started_at: str
    completed_at: str
    result_path: str
    log_path: str
    checkpoint_path: str
    handoff_reference: str
    limit_observation_id: str
    codex_invocation_reference: str = ""
    manual_prompt_dispatched: bool = False
    active_codex_conversation_required: bool = False
    expected_result: str = ""
    actual_result: str = ""


@dataclass(frozen=True)
class RuntimeProofRecoveryEvidence:
    """Evidence for one pause, wait, restart, or replay path."""

    kind: RuntimeProofRecoveryKind
    status: RuntimeProofRecoveryStatus
    expected_action: str
    actual_action: str
    failed_request_path: str = ""
    checkpoint_path: str = ""
    resume_after: str = ""
    preserved_output_path: str = ""
    duplicate_side_effect_prevented: bool = False
    injected_failure: bool = False


@dataclass(frozen=True)
class RuntimeProofBoundaryEvidence:
    """Security and Product Owner boundary assertions for the proof run."""

    subscription_auth_mode: str
    api_key_fallback_disabled: bool
    credentials_copied_to_container: bool
    approval_bypass_detected: bool
    logs_redacted: bool
    permitted_effects: tuple[str, ...] = ()
    unsupported_paths: tuple[str, ...] = ()
    human_interventions: tuple[str, ...] = ()


@dataclass(frozen=True)
class UnattendedRuntimeProofReport:
    """Complete AGENT-967 proof package supplied by a release/tester workflow."""

    jira_issue_key: str
    release: str
    sprint: str
    tested_main_sha: str
    fixture_repository: str
    fixture_approved_by: str
    startup_commands: tuple[str, ...]
    configuration_keys: tuple[str, ...]
    target_paths: tuple[str, ...]
    model_route: str
    quota_observation_ids: tuple[str, ...]
    agiletest_references: tuple[str, ...]
    stages: tuple[RuntimeProofStageEvidence, ...]
    recovery_cases: tuple[RuntimeProofRecoveryEvidence, ...]
    boundary: RuntimeProofBoundaryEvidence
    generated_at: str
    evidence_path: str
    operator_docs_updated: bool = False
    broader_chain_follow_up_recorded: bool = False


@dataclass(frozen=True)
class RuntimeProofValidationIssue:
    """One blocking or informational proof validation finding."""

    field: str
    message: str


@dataclass(frozen=True)
class RuntimeProofValidationResult:
    """Machine-readable validation result for operator and regression gates."""

    ready_for_regression: bool
    issues: tuple[RuntimeProofValidationIssue, ...]
    live_completed_stage_count: int
    controlled_completed_stage_count: int
    recovery_kind_count: int


REQUIRED_RECOVERY_KINDS: frozenset[RuntimeProofRecoveryKind] = frozenset(
    {
        RuntimeProofRecoveryKind.QUOTA_WAIT,
        RuntimeProofRecoveryKind.PO_WAIT,
        RuntimeProofRecoveryKind.PERMISSION_WAIT,
        RuntimeProofRecoveryKind.RESTART_RECOVERY,
    }
)


def validate_unattended_runtime_proof(report: UnattendedRuntimeProofReport) -> RuntimeProofValidationResult:
    """Validate that a proof package satisfies the AGENT-967 gate.

    The validator is deliberately strict. Controlled fixtures and dry runs are
    allowed as supporting evidence, but at least two completed live Codex stages
    are required before the package can unblock sprint regression.
    """

    issues: list[RuntimeProofValidationIssue] = []
    _require_text(issues, "jira_issue_key", report.jira_issue_key)
    _require_text(issues, "release", report.release)
    _require_text(issues, "sprint", report.sprint)
    _require_text(issues, "tested_main_sha", report.tested_main_sha)
    _require_text(issues, "fixture_repository", report.fixture_repository)
    _require_text(issues, "fixture_approved_by", report.fixture_approved_by)
    _require_text(issues, "model_route", report.model_route)
    _require_text(issues, "generated_at", report.generated_at)
    _require_text(issues, "evidence_path", report.evidence_path)
    _require_non_empty(issues, "startup_commands", report.startup_commands)
    _require_non_empty(issues, "configuration_keys", report.configuration_keys)
    _require_non_empty(issues, "target_paths", report.target_paths)
    _require_non_empty(issues, "quota_observation_ids", report.quota_observation_ids)
    _require_non_empty(issues, "agiletest_references", report.agiletest_references)

    live_completed = 0
    controlled_completed = 0
    for index, stage in enumerate(report.stages, start=1):
        prefix = f"stages[{index}]"
        _validate_stage(issues, prefix, stage)
        if stage.status is RuntimeProofStageStatus.COMPLETED:
            if stage.execution_mode is RuntimeProofExecutionMode.LIVE_CODEX:
                live_completed += 1
            else:
                controlled_completed += 1

    if live_completed < 2:
        issues.append(
            RuntimeProofValidationIssue(
                "stages",
                "At least two completed live Codex stages are required; controlled fixtures and dry runs do not satisfy live proof.",
            )
        )
    if controlled_completed and live_completed < 2:
        issues.append(
            RuntimeProofValidationIssue(
                "stages.execution_mode",
                "Controlled fixture stages were provided only as supporting evidence and cannot be reported as passed live execution.",
            )
        )

    passed_recovery_kinds = _passed_recovery_kinds(report.recovery_cases, issues)
    missing = REQUIRED_RECOVERY_KINDS - passed_recovery_kinds
    for kind in sorted(missing, key=lambda item: item.value):
        issues.append(
            RuntimeProofValidationIssue(
                "recovery_cases",
                f"Missing passed recovery evidence for {kind.value}.",
            )
        )

    _validate_boundary(issues, report.boundary)
    if not report.operator_docs_updated:
        issues.append(RuntimeProofValidationIssue("operator_docs_updated", "Operator/readiness docs must state exactly what was proven."))
    if not report.broader_chain_follow_up_recorded:
        issues.append(
            RuntimeProofValidationIssue(
                "broader_chain_follow_up_recorded",
                "The proof must keep the full multi-role chain as an explicit follow-up until separately demonstrated.",
            )
        )

    return RuntimeProofValidationResult(
        ready_for_regression=not issues,
        issues=tuple(issues),
        live_completed_stage_count=live_completed,
        controlled_completed_stage_count=controlled_completed,
        recovery_kind_count=len(passed_recovery_kinds),
    )


def runtime_proof_validation_to_dict(result: RuntimeProofValidationResult) -> dict[str, Any]:
    """Convert proof validation output into JSON-safe data."""

    return {
        "ready_for_regression": result.ready_for_regression,
        "issues": [issue.__dict__ for issue in result.issues],
        "live_completed_stage_count": result.live_completed_stage_count,
        "controlled_completed_stage_count": result.controlled_completed_stage_count,
        "recovery_kind_count": result.recovery_kind_count,
    }


def format_unattended_runtime_proof_validation(result: RuntimeProofValidationResult) -> str:
    """Render proof validation without leaking secret-like values."""

    if result.ready_for_regression:
        return (
            "Runtime proof ready for regression: "
            f"live_stages={result.live_completed_stage_count}, "
            f"recovery_kinds={result.recovery_kind_count}."
        )
    lines = ["Runtime proof is not ready for regression:"]
    for issue in result.issues:
        lines.append(f"- {issue.field}: {issue.message}")
    return redact_failed_request_text("\n".join(lines)).value


def _validate_stage(
    issues: list[RuntimeProofValidationIssue],
    prefix: str,
    stage: RuntimeProofStageEvidence,
) -> None:
    _require_text(issues, f"{prefix}.stage_id", stage.stage_id)
    _require_text(issues, f"{prefix}.assignment_id", stage.assignment_id)
    _require_text(issues, f"{prefix}.codex_job_id", stage.codex_job_id)
    _require_text(issues, f"{prefix}.role", stage.role)
    _require_text(issues, f"{prefix}.command", stage.command)
    _require_text(issues, f"{prefix}.started_at", stage.started_at)
    _require_text(issues, f"{prefix}.completed_at", stage.completed_at)
    _require_text(issues, f"{prefix}.result_path", stage.result_path)
    _require_text(issues, f"{prefix}.log_path", stage.log_path)
    _require_text(issues, f"{prefix}.checkpoint_path", stage.checkpoint_path)
    _require_text(issues, f"{prefix}.handoff_reference", stage.handoff_reference)
    _require_text(issues, f"{prefix}.limit_observation_id", stage.limit_observation_id)
    if stage.execution_mode is RuntimeProofExecutionMode.LIVE_CODEX:
        _require_text(issues, f"{prefix}.codex_invocation_reference", stage.codex_invocation_reference)
    if stage.status is not RuntimeProofStageStatus.COMPLETED:
        issues.append(RuntimeProofValidationIssue(f"{prefix}.status", "Stage must be completed before proof can pass."))
    if stage.manual_prompt_dispatched:
        issues.append(RuntimeProofValidationIssue(f"{prefix}.manual_prompt_dispatched", "Manual prompt dispatch is not unattended execution."))
    if stage.active_codex_conversation_required:
        issues.append(
            RuntimeProofValidationIssue(
                f"{prefix}.active_codex_conversation_required",
                "A running Codex chat cannot be required for unattended proof.",
            )
        )


def _passed_recovery_kinds(
    cases: Iterable[RuntimeProofRecoveryEvidence],
    issues: list[RuntimeProofValidationIssue],
) -> frozenset[RuntimeProofRecoveryKind]:
    passed: set[RuntimeProofRecoveryKind] = set()
    for index, case in enumerate(cases, start=1):
        prefix = f"recovery_cases[{index}]"
        _require_text(issues, f"{prefix}.expected_action", case.expected_action)
        _require_text(issues, f"{prefix}.actual_action", case.actual_action)
        if case.status is not RuntimeProofRecoveryStatus.PASSED:
            issues.append(RuntimeProofValidationIssue(f"{prefix}.status", "Recovery case must pass; NOT RUN/BLOCKED cannot become PASSED."))
            continue
        if not case.duplicate_side_effect_prevented:
            issues.append(RuntimeProofValidationIssue(f"{prefix}.duplicate_side_effect_prevented", "Recovery must prove duplicate side effects were prevented."))
            continue
        if case.kind in {RuntimeProofRecoveryKind.QUOTA_WAIT, RuntimeProofRecoveryKind.PERMISSION_WAIT}:
            _require_text(issues, f"{prefix}.failed_request_path", case.failed_request_path)
        if case.kind is RuntimeProofRecoveryKind.RESTART_RECOVERY:
            _require_text(issues, f"{prefix}.checkpoint_path", case.checkpoint_path)
            _require_text(issues, f"{prefix}.preserved_output_path", case.preserved_output_path)
        passed.add(case.kind)
    return frozenset(passed)


def _validate_boundary(issues: list[RuntimeProofValidationIssue], boundary: RuntimeProofBoundaryEvidence) -> None:
    mode = boundary.subscription_auth_mode.strip().lower()
    if mode not in {"chatgpt", "subscription", "chatgpt_subscription"}:
        issues.append(
            RuntimeProofValidationIssue(
                "boundary.subscription_auth_mode",
                "Runtime proof must use ChatGPT subscription authentication, not API key mode.",
            )
        )
    if not boundary.api_key_fallback_disabled:
        issues.append(RuntimeProofValidationIssue("boundary.api_key_fallback_disabled", "API-key fallback must be disabled."))
    if boundary.credentials_copied_to_container:
        issues.append(
            RuntimeProofValidationIssue(
                "boundary.credentials_copied_to_container",
                "Codex credentials must not be copied or mounted into generic worker containers.",
            )
        )
    if boundary.approval_bypass_detected:
        issues.append(RuntimeProofValidationIssue("boundary.approval_bypass_detected", "Approval bypass is not allowed."))
    if not boundary.logs_redacted:
        issues.append(RuntimeProofValidationIssue("boundary.logs_redacted", "Proof logs must be redacted."))
    if not boundary.permitted_effects:
        issues.append(RuntimeProofValidationIssue("boundary.permitted_effects", "Explicit permitted file/Git/Jira effects must be recorded."))


def _require_text(issues: list[RuntimeProofValidationIssue], field: str, value: str) -> None:
    if not value.strip():
        issues.append(RuntimeProofValidationIssue(field, "Required value is missing."))


def _require_non_empty(issues: list[RuntimeProofValidationIssue], field: str, values: tuple[str, ...]) -> None:
    if not tuple(value for value in values if value.strip()):
        issues.append(RuntimeProofValidationIssue(field, "At least one value is required."))
