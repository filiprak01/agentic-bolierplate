"""Worker-facing bridge for host-side Codex execution requests."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path

from agentic_boilerplate.domain import (
    AgentAssignment,
    AssignmentStatus,
    CodexEffortMode,
    CodexFailedRequestArtifact,
    CodexJobArtifact,
    CodexJobStatus,
    CodexPauseReason,
    CodexResumeAction,
    ReasoningLevel,
    assign_worker,
    fail_assignment,
)
from agentic_boilerplate.storage import (
    CODEX_JOB_FILE,
    CodexJobAlreadyExistsError,
    FileAgentAssignmentStore,
    FileCodexJobStore,
    FileCodexPauseStore,
)


class CodexExecutionBridgeMode(str, Enum):
    """Supported execution bridge modes."""

    HOST_SIDE = "host_side"
    DIRECT_CONTAINER = "direct_container"


@dataclass(frozen=True)
class CodexExecutionBridgeOutcome:
    """Visible result of converting a worker assignment into a Codex job."""

    assignment: AgentAssignment
    status: AssignmentStatus
    message: str
    mode: CodexExecutionBridgeMode
    codex_job: CodexJobArtifact | None = None
    codex_job_path: Path | None = None
    failed_request_path: Path | None = None


class HostSideCodexExecutionBridge:
    """Create durable host-side Codex jobs for worker assignments."""

    def __init__(
        self,
        *,
        assignment_store: FileAgentAssignmentStore,
        job_store: FileCodexJobStore,
        pause_store: FileCodexPauseStore,
        mode: CodexExecutionBridgeMode | str = CodexExecutionBridgeMode.HOST_SIDE,
    ) -> None:
        self.assignment_store = assignment_store
        self.job_store = job_store
        self.pause_store = pause_store
        self.mode = _coerce_mode(mode)

    def create_request(
        self,
        assignment: AgentAssignment,
        *,
        worker_id: str,
        target_repo_path: str,
        model: str,
        reasoning: ReasoningLevel | str,
        speed: str,
        effort_mode: CodexEffortMode | str,
        created_at: str,
    ) -> CodexExecutionBridgeOutcome:
        """Persist a host-side Codex request or fail unsupported modes safely."""

        if self.mode != CodexExecutionBridgeMode.HOST_SIDE:
            return self._fail_unsupported_mode(assignment, worker_id=worker_id, failed_at=created_at)

        job_id = assignment.codex_job_id or _job_id_from_assignment(assignment)
        job = CodexJobArtifact(
            id=job_id,
            jira_issue_key=assignment.jira_issue_key,
            role=assignment.role,
            target_repo_path=target_repo_path.strip(),
            branch_name=assignment.branch_name,
            context_pack_path=assignment.paths.context_pack_path,
            output_path=assignment.paths.output_path,
            model=model.strip(),
            reasoning=_coerce_reasoning(reasoning),
            speed=speed.strip(),
            effort_mode=_coerce_effort_mode(effort_mode),
            status=CodexJobStatus.QUEUED,
            created_at=created_at.strip(),
            updated_at=created_at.strip(),
            attempt_count=0,
        )
        try:
            job_location = self.job_store.create(job)
        except CodexJobAlreadyExistsError:
            restored_job = self.job_store.read(job.id)
            job = restored_job
            job_location = self.job_store.write(restored_job)

        updated_assignment = assignment
        if assignment.status == AssignmentStatus.QUEUED:
            updated_assignment = assign_worker(
                assignment,
                worker_id=worker_id,
                codex_job_id=job.id,
                started_at=created_at,
                updated_at=created_at,
            )
        elif assignment.status in {AssignmentStatus.ASSIGNED, AssignmentStatus.IN_PROGRESS}:
            updated_assignment = replace(
                assignment,
                worker_id=assignment.worker_id or worker_id,
                codex_job_id=assignment.codex_job_id or job.id,
                updated_at=created_at,
            )
        self.assignment_store.save_assignment(updated_assignment)

        return CodexExecutionBridgeOutcome(
            assignment=updated_assignment,
            status=updated_assignment.status,
            message=(
                "Host-side Codex execution request created. "
                "A host runner can process the queued job without mounting Codex session secrets into Docker."
            ),
            mode=self.mode,
            codex_job=job,
            codex_job_path=job_location.path,
        )

    def _fail_unsupported_mode(
        self,
        assignment: AgentAssignment,
        *,
        worker_id: str,
        failed_at: str,
    ) -> CodexExecutionBridgeOutcome:
        message = (
            "Direct in-container Codex execution is not supported by this release. "
            "Use the host_side bridge mode so Codex subscription/session secrets stay outside Docker."
        )
        failed_request = CodexFailedRequestArtifact(
            id=f"failed-{assignment.id}-{uuid.uuid5(uuid.NAMESPACE_URL, assignment.id + failed_at).hex[:8]}",
            codex_job_id=assignment.codex_job_id or _job_id_from_assignment(assignment),
            jira_issue_key=assignment.jira_issue_key,
            worker_role=assignment.role,
            reason=CodexPauseReason.EXECUTION_FAILED,
            failed_at=failed_at,
            request_summary=(
                f"assignment={assignment.id} issue={assignment.jira_issue_key} "
                f"role={assignment.role.value} mode={self.mode.value}"
            ),
            error_summary=message,
            next_action=CodexResumeAction.MANUAL_REVIEW,
            stage_id="codex_execution_bridge.unsupported_mode",
            retry_policy="switch_to_host_side_mode_before_retry",
            suggested_next_role_action="operator_update_worker_codex_execution_mode",
            side_effect_idempotency_key=f"{assignment.jira_issue_key}:{assignment.id}:unsupported:{self.mode.value}",
        )
        failed_location = self.pause_store.create_failed_request(failed_request)
        assignment_with_failure_path = replace(
            assignment,
            worker_id=assignment.worker_id or worker_id,
            codex_job_id=assignment.codex_job_id or failed_request.codex_job_id,
            paths=replace(assignment.paths, failed_request_path=str(failed_location.path)),
        )
        failed_assignment = fail_assignment(
            assignment_with_failure_path,
            failure_reason=message,
            updated_at=failed_at,
        )
        self.assignment_store.save_assignment(failed_assignment)
        return CodexExecutionBridgeOutcome(
            assignment=failed_assignment,
            status=failed_assignment.status,
            message=message,
            mode=self.mode,
            failed_request_path=failed_location.path,
        )


def _job_id_from_assignment(assignment: AgentAssignment) -> str:
    configured_path = Path(assignment.paths.codex_job_path)
    if configured_path.name == CODEX_JOB_FILE and configured_path.parent.name:
        return configured_path.parent.name
    return configured_path.stem or f"codex-job-{assignment.jira_issue_key}"


def _coerce_mode(value: CodexExecutionBridgeMode | str) -> CodexExecutionBridgeMode:
    if isinstance(value, CodexExecutionBridgeMode):
        return value
    return CodexExecutionBridgeMode(str(value).strip())


def _coerce_reasoning(value: ReasoningLevel | str) -> ReasoningLevel:
    if isinstance(value, ReasoningLevel):
        return value
    return ReasoningLevel(str(value).strip())


def _coerce_effort_mode(value: CodexEffortMode | str) -> CodexEffortMode:
    if isinstance(value, CodexEffortMode):
        return value
    return CodexEffortMode(str(value).strip())
