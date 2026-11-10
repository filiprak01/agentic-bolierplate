"""Host-side Codex runner boundary."""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from agentic_boilerplate.domain import (
    AgentRole,
    CodexFailedRequestArtifact,
    CodexJobArtifact,
    CodexJobStatus,
    CodexLinkedArtifact,
    CodexLinkedArtifactKind,
    CodexPausedAssignmentArtifact,
    CodexPauseReason,
    CodexResumeAction,
    CodexResumeMetadata,
    CodexResumePlan,
    codex_limit_windows_for_display,
    decide_codex_limit_gate,
    redact_failed_request_text,
)
from agentic_boilerplate.storage import FileCodexJobStore, FileCodexLimitAvailabilityStore, FileCodexPauseStore


class CodexRunnerExecutor(Protocol):
    """Fakeable execution boundary for the local host Codex process."""

    def execute(self, request: "CodexRunnerRequest") -> "CodexRunnerExecution":
        """Execute one Codex request and return structured local output."""


@dataclass(frozen=True)
class CodexRunnerRequest:
    """Request passed to the host-side Codex executor."""

    job_id: str
    jira_issue_key: str
    role: AgentRole
    target_repo_path: str
    branch_name: str
    context_pack_path: str
    model: str
    reasoning: str
    speed: str
    effort_mode: str
    output_path: str
    attempt_count: int


@dataclass(frozen=True)
class CodexRunnerExecution:
    """Executor response used by the runner boundary."""

    output_text: str = ""
    log_text: str = ""
    limit_reached: bool = False
    failed: bool = False
    error_summary: str = ""
    resume_after: str = ""
    failure_category: str = ""


@dataclass(frozen=True)
class CodexRunnerOutcome:
    """Durable outcome of one runner attempt."""

    job_id: str
    status: CodexJobStatus
    job_path: Path
    result_path: Path
    log_path: Path
    failed_request_path: Path | None = None
    paused_assignment_path: Path | None = None


class HostSideCodexRunner:
    """Read queued Codex jobs and execute them through a host-side boundary."""

    def __init__(
        self,
        *,
        job_store: FileCodexJobStore,
        pause_store: FileCodexPauseStore,
        executor: CodexRunnerExecutor,
        limit_store: FileCodexLimitAvailabilityStore | None = None,
        logs_root: Path | str = "data/agent-logs/codex-runner",
        now: Callable[[], str] | None = None,
        worker_id: str = "host-codex-runner",
        limit_stale_after_seconds: int | None = None,
        limit_future_tolerance_seconds: int = 30,
        limit_account_scope_id: str = "",
        limit_bucket_id: str = "",
    ) -> None:
        self.job_store = job_store
        self.pause_store = pause_store
        self.executor = executor
        self.limit_store = limit_store
        self.logs_root = Path(logs_root)
        self._now = now or _utc_now
        self.worker_id = worker_id
        self.limit_stale_after_seconds = limit_stale_after_seconds
        self.limit_future_tolerance_seconds = limit_future_tolerance_seconds
        self.limit_account_scope_id = limit_account_scope_id
        self.limit_bucket_id = limit_bucket_id

    def run_next(self) -> CodexRunnerOutcome | None:
        """Run the next queued job, if one exists."""

        pending = self.job_store.list_pending()
        if not pending:
            return None
        return self.run_job(pending[0])

    def run_job(self, job: CodexJobArtifact) -> CodexRunnerOutcome:
        """Run one queued job and persist status, result, log, and recovery files."""

        started_at = self._now()
        running_job = replace(
            job,
            status=CodexJobStatus.RUNNING,
            attempt_count=job.attempt_count + 1,
            updated_at=started_at,
        )
        job_location = self.job_store.write(running_job)
        limit_record = self._latest_limit_record()
        limit_gate = self._limit_gate(limit_record, now=started_at)
        if limit_gate is not None and not limit_gate.allowed:
            execution = CodexRunnerExecution(
                log_text=_format_limit_decision_log(running_job, limit_gate, limit_record),
                limit_reached=True,
                error_summary=limit_gate.reason,
                resume_after=limit_gate.resume_after,
                failure_category="quota_exhausted",
            )
            result_path = _write_result(Path(running_job.output_path), running_job, execution)
            log_path = _write_log(self.logs_root / running_job.jira_issue_key / f"{running_job.id}.log", execution)
            return self._pause_job(
                running_job,
                execution,
                job_location.path,
                result_path,
                log_path,
                paused_at=self._now(),
                reason=CodexPauseReason.LIMIT_REACHED,
            )

        request = _request_from_job(running_job)
        execution = self.executor.execute(request)
        if limit_gate is not None:
            execution = replace(
                execution,
                log_text=_format_limit_decision_log(running_job, limit_gate, limit_record) + execution.log_text,
            )
        result_path = _write_result(Path(running_job.output_path), running_job, execution)
        log_path = _write_log(self.logs_root / running_job.jira_issue_key / f"{running_job.id}.log", execution)

        if execution.limit_reached:
            return self._pause_job(
                running_job,
                execution,
                job_location.path,
                result_path,
                log_path,
                paused_at=self._now(),
                reason=CodexPauseReason.LIMIT_REACHED,
            )
        if execution.failed:
            return self._fail_job(
                running_job,
                execution,
                job_location.path,
                result_path,
                log_path,
                failed_at=self._now(),
            )

        completed = replace(running_job, status=CodexJobStatus.COMPLETED, updated_at=self._now())
        completed_location = self.job_store.write(completed)
        return CodexRunnerOutcome(
            job_id=completed.id,
            status=completed.status,
            job_path=completed_location.path,
            result_path=result_path,
            log_path=log_path,
        )

    def _latest_limit_record(self):
        if self.limit_store is None:
            return None
        return self.limit_store.latest_record(
            account_scope_id=self.limit_account_scope_id,
            bucket_id=self.limit_bucket_id,
        )

    def _limit_gate(self, record, *, now: str):
        if self.limit_store is None:
            return None
        return decide_codex_limit_gate(
            record,
            now=now,
            stale_after_seconds=self.limit_stale_after_seconds,
            future_tolerance_seconds=self.limit_future_tolerance_seconds,
        )

    def _pause_job(
        self,
        job: CodexJobArtifact,
        execution: CodexRunnerExecution,
        job_path: Path,
        result_path: Path,
        log_path: Path,
        *,
        paused_at: str,
        reason: CodexPauseReason,
    ) -> CodexRunnerOutcome:
        failed_request = _failed_request_from_execution(job, execution, reason=reason, failed_at=paused_at)
        failed_location = self.pause_store.create_failed_request(failed_request)
        paused = replace(
            job,
            status=CodexJobStatus.PAUSED_LIMIT,
            failed_request_path=str(failed_location.path),
            updated_at=paused_at,
            resume=CodexResumeMetadata(
                resumable=True,
                resume_after=execution.resume_after,
                last_checkpoint_path=str(result_path),
                last_error=execution.error_summary,
                paused_at=paused_at,
            ),
        )
        paused_job_location = self.job_store.write(paused)
        paused_assignment = CodexPausedAssignmentArtifact(
            id=f"paused-{job.id}-attempt-{job.attempt_count}",
            jira_issue_key=job.jira_issue_key,
            worker_role=job.role,
            codex_job_id=job.id,
            worker_id=self.worker_id,
            branch_name=job.branch_name,
            context_pack_path=job.context_pack_path,
            failed_request_path=str(failed_location.path),
            status=CodexJobStatus.PAUSED_LIMIT,
            reason=reason,
            resume=CodexResumePlan(
                original_story_key=job.jira_issue_key,
                worker_role=job.role,
                codex_job_id=job.id,
                context_pack_path=job.context_pack_path,
                next_action=CodexResumeAction.RETRY_SAME_REQUEST,
                note=execution.error_summary,
            ),
            paused_at=paused_at,
            updated_at=paused_at,
            attempt_count=paused.attempt_count,
            linked_artifacts=(
                CodexLinkedArtifact(
                    kind=CodexLinkedArtifactKind.LOG,
                    path=str(log_path),
                    label="Codex runner log",
                ),
                CodexLinkedArtifact(
                    kind=CodexLinkedArtifactKind.PARTIAL_OUTPUT,
                    path=str(result_path),
                    label="Codex runner result",
                ),
            ),
        )
        paused_location = self.pause_store.create_paused_assignment(paused_assignment)
        return CodexRunnerOutcome(
            job_id=job.id,
            status=CodexJobStatus.PAUSED_LIMIT,
            job_path=paused_job_location.path,
            result_path=result_path,
            log_path=log_path,
            failed_request_path=failed_location.path,
            paused_assignment_path=paused_location.path,
        )

    def _fail_job(
        self,
        job: CodexJobArtifact,
        execution: CodexRunnerExecution,
        job_path: Path,
        result_path: Path,
        log_path: Path,
        *,
        failed_at: str,
    ) -> CodexRunnerOutcome:
        failed_request = _failed_request_from_execution(
            job,
            execution,
            reason=CodexPauseReason.EXECUTION_FAILED,
            failed_at=failed_at,
        )
        failed_location = self.pause_store.create_failed_request(failed_request)
        failed = replace(
            job,
            status=CodexJobStatus.FAILED,
            failed_request_path=str(failed_location.path),
            updated_at=failed_at,
        )
        failed_job_location = self.job_store.write(failed)
        return CodexRunnerOutcome(
            job_id=job.id,
            status=CodexJobStatus.FAILED,
            job_path=failed_job_location.path,
            result_path=result_path,
            log_path=log_path,
            failed_request_path=failed_location.path,
        )


def _request_from_job(job: CodexJobArtifact) -> CodexRunnerRequest:
    return CodexRunnerRequest(
        job_id=job.id,
        jira_issue_key=job.jira_issue_key,
        role=job.role,
        target_repo_path=job.target_repo_path,
        branch_name=job.branch_name,
        context_pack_path=job.context_pack_path,
        model=job.model,
        reasoning=job.reasoning.value,
        speed=job.speed,
        effort_mode=job.effort_mode.value,
        output_path=job.output_path,
        attempt_count=job.attempt_count,
    )


def _failed_request_from_execution(
    job: CodexJobArtifact,
    execution: CodexRunnerExecution,
    *,
    reason: CodexPauseReason,
    failed_at: str,
) -> CodexFailedRequestArtifact:
    is_limit = reason == CodexPauseReason.LIMIT_REACHED
    failure_category = _failure_category_for_execution(execution, reason)
    return CodexFailedRequestArtifact(
        id=f"failed-{job.id}-{uuid.uuid5(uuid.NAMESPACE_URL, job.id + failed_at).hex[:8]}",
        codex_job_id=job.id,
        jira_issue_key=job.jira_issue_key,
        worker_role=job.role,
        reason=reason,
        failed_at=failed_at,
        request_summary=(
            f"job={job.id} issue={job.jira_issue_key} role={job.role.value} "
            f"model={job.model} reasoning={job.reasoning.value} speed={job.speed} "
            f"context_pack={job.context_pack_path} failure_category={failure_category}"
        ),
        error_summary=execution.error_summary or ("Codex limit reached." if is_limit else "Codex execution failed."),
        next_action=CodexResumeAction.RETRY_SAME_REQUEST if is_limit else CodexResumeAction.MANUAL_REVIEW,
        stage_id=_stage_id_for_execution(failure_category, reason),
        stdout_snippet=execution.output_text[:1000],
        stderr_snippet=execution.error_summary[:1000],
        retry_policy=_retry_policy_for_execution(failure_category, reason),
        suggested_next_role_action=_suggested_action_for_execution(failure_category, reason),
        side_effect_idempotency_key=_side_effect_key_for_execution(job, reason, failure_category),
    )


def _format_limit_decision_log(job: CodexJobArtifact, gate, record) -> str:
    lines = [
        "Codex limit decision before execution:",
        f"job={job.id}",
        f"jira_issue_key={job.jira_issue_key}",
        f"model={job.model}",
        f"reasoning={job.reasoning.value}",
        f"speed={job.speed}",
        f"allowed={str(gate.allowed).lower()}",
        f"action={gate.action.value}",
        f"reason={gate.reason}",
        f"resume_after={gate.resume_after or 'not required'}",
    ]
    if record is not None:
        for label, window in codex_limit_windows_for_display(record):
            remaining = "unknown" if window.remaining_percent is None else f"{window.remaining_percent}%"
            lines.append(
                "window="
                f"{label};status={window.status.value};remaining={remaining};"
                f"reset_at={window.reset_at or 'unknown'};source={window.observation_source.value}"
            )
    return "\n".join(lines) + "\n"


def _failure_category_for_execution(execution: CodexRunnerExecution, reason: CodexPauseReason) -> str:
    if execution.failure_category.strip():
        return execution.failure_category.strip()
    if reason == CodexPauseReason.LIMIT_REACHED:
        return "limit_pause"
    return "execution_failure"


def _stage_id_for_execution(failure_category: str, reason: CodexPauseReason) -> str:
    if reason == CodexPauseReason.LIMIT_REACHED:
        return f"host_side_runner.{failure_category or 'limit_pause'}"
    return f"host_side_runner.{failure_category or 'execution_failure'}"


def _retry_policy_for_execution(failure_category: str, reason: CodexPauseReason) -> str:
    if reason == CodexPauseReason.LIMIT_REACHED:
        return "retry_same_request_after_limit_reset"
    policies = {
        "authentication_blocked": "refresh_host_codex_login_before_retry",
        "permission_blocked": "operator_review_permission_request_before_retry",
        "timeout": "split_or_resume_stage_before_retry",
        "cancelled": "resume_same_stage_when_operator_allows",
        "malformed_output": "manual_review_before_retry",
    }
    return policies.get(failure_category, "manual_review_before_retry")


def _suggested_action_for_execution(failure_category: str, reason: CodexPauseReason) -> str:
    if reason == CodexPauseReason.LIMIT_REACHED:
        return "scheduler_retry_after_limit_reset"
    actions = {
        "authentication_blocked": "operator_refresh_codex_subscription_auth",
        "permission_blocked": "operator_review_and_approve_or_deny_permission",
        "timeout": "developer_split_stage_or_resume_from_checkpoint",
        "cancelled": "scheduler_resume_when_worker_restarts",
        "malformed_output": "developer_review_partial_output",
    }
    return actions.get(failure_category, "developer_manual_recovery")


def _side_effect_key_for_execution(
    job: CodexJobArtifact,
    reason: CodexPauseReason,
    failure_category: str,
) -> str:
    base_key = f"{job.jira_issue_key}:{job.id}:{job.attempt_count}:{reason.value}"
    if failure_category in {"limit_pause", "execution_failure"}:
        return base_key
    return f"{base_key}:{failure_category}"


def _write_result(path: Path, job: CodexJobArtifact, execution: CodexRunnerExecution) -> Path:
    payload = {
        "job_id": job.id,
        "jira_issue_key": job.jira_issue_key,
        "status": "limit_reached" if execution.limit_reached else "failed" if execution.failed else "completed",
        "failure_category": execution.failure_category,
        "model": job.model,
        "reasoning": job.reasoning.value,
        "speed": job.speed,
        "context_pack_path": job.context_pack_path,
        "output_text": redact_failed_request_text(execution.output_text).value,
        "error_summary": redact_failed_request_text(execution.error_summary).value,
    }
    _atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return path


def _write_log(path: Path, execution: CodexRunnerExecution) -> Path:
    log_text = execution.log_text or "No runner log output.\n"
    _atomic_write_text(path, redact_failed_request_text(log_text).value)
    return path


def _atomic_write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temp_path.open("w", encoding="utf-8") as file:
            file.write(value)
            file.flush()
            os.fsync(file.fileno())
        temp_path.replace(path)
    finally:
        temp_path.unlink(missing_ok=True)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
