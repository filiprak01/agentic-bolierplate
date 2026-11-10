"""Host-side supervisor for queued Codex jobs.

The supervisor coordinates durable state around the lower-level host runner. It
never accepts Jira work, approves PRs, merges, or bypasses Tester gates; it only
claims one queued execution stage, verifies gates, dispatches it, and records the
next safe orchestration signal.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from agentic_boilerplate.domain.agent_assignment import (
    AgentAssignment,
    AssignmentStatus,
    assign_worker,
    complete_assignment,
    fail_assignment,
    mark_assignment_in_progress,
    pause_assignment_for_limit,
)
from agentic_boilerplate.domain.assignment_lock import (
    AssignmentLock,
    AssignmentLockReleaseReason,
    AssignmentLockStatus,
    acquire_assignment_lock,
)
from agentic_boilerplate.domain.codex_job import CodexJobArtifact, CodexJobStatus
from agentic_boilerplate.domain.codex_limit_availability import (
    CodexLimitAvailabilityRecord,
    CodexLimitObservationSource,
)
from agentic_boilerplate.domain.codex_pause import redact_failed_request_text
from agentic_boilerplate.domain.detached_worker_checkpoint import (
    DetachedWorkerCheckpoint,
    DetachedWorkerCheckpointStage,
    DetachedWorkerResumeAction,
)
from agentic_boilerplate.domain.orchestration_event_queue import (
    OrchestrationEventType,
    build_orchestration_event,
    orchestration_event_idempotency_key,
)
from agentic_boilerplate.domain.po_inbox import AgentRole
from agentic_boilerplate.runtime.codex_limit_sentinel import (
    CodexAppServerLimitReader,
    build_unknown_codex_limit_record,
    refresh_codex_limit_from_payload,
)
from agentic_boilerplate.runtime.codex_runner import CodexRunnerOutcome, HostSideCodexRunner
from agentic_boilerplate.runtime.host_execution_preflight import (
    HostCodexPreflightDecision,
    HostCodexPreflightIssue,
    HostCodexPreflightIssueKind,
    render_host_codex_preflight_decision,
)
from agentic_boilerplate.storage import (
    FileAgentAssignmentStore,
    FileAssignmentLockStore,
    FileCodexLimitAvailabilityStore,
    FileDetachedWorkerCheckpointStore,
    FileOrchestrationEventQueue,
)

HostCodexPreflightProvider = Callable[
    [CodexJobArtifact, AgentAssignment, AssignmentLock, CodexLimitAvailabilityRecord | None, str],
    HostCodexPreflightDecision,
]


class HostCodexSupervisorServiceState(str, Enum):
    """Operator-visible service state for the host supervisor."""

    STARTING = "starting"
    IDLE = "idle"
    RUNNING = "running"
    BLOCKED = "blocked"
    STOPPING = "stopping"
    STOPPED = "stopped"


class HostCodexSupervisorReason(str, Enum):
    """Machine-readable outcome reason for one supervisor turn."""

    NO_JOB = "no_job"
    JOB_COMPLETED = "job_completed"
    JOB_PAUSED_LIMIT = "job_paused_limit"
    JOB_FAILED = "job_failed"
    DUPLICATE_ACTIVE_JOB = "duplicate_active_job"
    ASSIGNMENT_MISSING = "assignment_missing"
    ASSIGNMENT_NOT_ELIGIBLE = "assignment_not_eligible"
    LOST_LEASE = "lost_lease"
    FOREIGN_LOCK = "foreign_lock"
    PREFLIGHT_BLOCKED = "preflight_blocked"
    PREFLIGHT_MISSING = "preflight_missing"
    EXECUTOR_EXCEPTION = "executor_exception"
    POST_STAGE_LIMIT_REFRESH_FAILED = "post_stage_limit_refresh_failed"
    SHUTDOWN_REQUESTED = "shutdown_requested"


@dataclass(frozen=True)
class HostCodexSupervisorStatus:
    """Serializable status snapshot for the host supervisor API and CLI."""

    service_state: HostCodexSupervisorServiceState
    reason: HostCodexSupervisorReason
    worker_id: str
    active_job_id: str = ""
    active_assignment_id: str = ""
    active_child_session_id: str = ""
    heartbeat_at: str = ""
    next_poll_at: str = ""
    job_status: str = ""
    assignment_status: str = ""
    latest_blocking_reason: str = ""
    preflight_allowed: bool = False
    preflight_blockers: tuple[str, ...] = ()
    latest_limit_observation_id: str = ""
    pre_stage_limit_observation_id: str = ""
    post_stage_limit_observation_id: str = ""
    checkpoint_path: str = ""
    event_path: str = ""
    result_path: str = ""
    log_path: str = ""
    failed_request_path: str = ""


@dataclass(frozen=True)
class HostCodexSupervisorResult:
    """Result of one run-once turn."""

    status: HostCodexSupervisorStatus
    runner_outcome: CodexRunnerOutcome | None = None


class HostCodexSupervisor:
    """Run one host-side Codex stage with durable claim and reconciliation."""

    def __init__(
        self,
        *,
        runner: HostSideCodexRunner,
        assignment_store: FileAgentAssignmentStore,
        lock_store: FileAssignmentLockStore,
        checkpoint_store: FileDetachedWorkerCheckpointStore,
        event_queue: FileOrchestrationEventQueue | None = None,
        limit_store: FileCodexLimitAvailabilityStore | None = None,
        limit_reader: CodexAppServerLimitReader | None = None,
        preflight_provider: HostCodexPreflightProvider | None = None,
        logs_root: Path | str = "data/agent-logs/host-codex-supervisor",
        worker_id: str = "host-codex-supervisor",
        poll_interval_seconds: int = 300,
        limit_account_scope_id: str = "",
        limit_bucket_id: str = "",
        limit_cutoff_percent: int = 90,
        now: Callable[[], str] | None = None,
        idle_wait: Callable[[int], bool] | None = None,
    ) -> None:
        self.runner = runner
        self.assignment_store = assignment_store
        self.lock_store = lock_store
        self.checkpoint_store = checkpoint_store
        self.event_queue = event_queue
        self.limit_store = limit_store or runner.limit_store
        self.limit_reader = limit_reader
        self.preflight_provider = preflight_provider
        self.logs_root = Path(logs_root)
        self.worker_id = worker_id.strip() or "host-codex-supervisor"
        self.poll_interval_seconds = max(1, int(poll_interval_seconds))
        self.limit_account_scope_id = limit_account_scope_id
        self.limit_bucket_id = limit_bucket_id
        self.limit_cutoff_percent = limit_cutoff_percent
        self._now = now or _utc_now
        self._stop_requested = threading.Event()
        self._idle_wait = idle_wait or self._stop_requested.wait
        self._last_status = HostCodexSupervisorStatus(
            service_state=HostCodexSupervisorServiceState.STARTING,
            reason=HostCodexSupervisorReason.NO_JOB,
            worker_id=self.worker_id,
            heartbeat_at=self._now(),
        )

    def request_stop(self) -> None:
        """Ask the service loop to stop before claiming another job."""

        self._stop_requested.set()

    def status(self) -> HostCodexSupervisorStatus:
        """Return the latest redacted supervisor status."""

        return self._last_status

    def run_once(self) -> HostCodexSupervisorResult:
        """Process at most one queued job, then return a durable status."""

        heartbeat = self._now()
        if self._stop_requested.is_set():
            return self._remember(
                HostCodexSupervisorStatus(
                    service_state=HostCodexSupervisorServiceState.STOPPED,
                    reason=HostCodexSupervisorReason.SHUTDOWN_REQUESTED,
                    worker_id=self.worker_id,
                    heartbeat_at=heartbeat,
                    next_poll_at="",
                    latest_blocking_reason="Stop requested before claim.",
                )
            )

        duplicate = self._duplicate_active_job()
        if duplicate is not None:
            return self._blocked(
                reason=HostCodexSupervisorReason.DUPLICATE_ACTIVE_JOB,
                job=duplicate,
                message="Another host-side Codex job is already running; duplicate consumer rejected.",
                heartbeat=heartbeat,
            )

        pending = self.runner.job_store.list_pending()
        if not pending:
            return self._remember(
                HostCodexSupervisorStatus(
                    service_state=HostCodexSupervisorServiceState.IDLE,
                    reason=HostCodexSupervisorReason.NO_JOB,
                    worker_id=self.worker_id,
                    heartbeat_at=heartbeat,
                    next_poll_at=_plus_seconds(heartbeat, self.poll_interval_seconds),
                    latest_limit_observation_id=_record_id(self._latest_limit_record()),
                )
            )

        job = pending[0]
        assignment = self._assignment_for_job(job)
        if assignment is None:
            return self._blocked(
                reason=HostCodexSupervisorReason.ASSIGNMENT_MISSING,
                job=job,
                message="Queued Codex job has no matching durable assignment; manual reconciliation required.",
                heartbeat=heartbeat,
            )

        claim = self._claim_assignment(job, assignment, heartbeat=heartbeat)
        if isinstance(claim, HostCodexSupervisorResult):
            return claim
        assignment, lock = claim

        limit_record = self._latest_limit_record()
        if self.preflight_provider is None:
            return self._preflight_missing(job, assignment, lock, limit_record, heartbeat=heartbeat)

        decision = self.preflight_provider(job, assignment, lock, limit_record, heartbeat)
        if not decision.allowed:
            return self._preflight_blocked(job, assignment, lock, decision, heartbeat=heartbeat)

        checkpoint_path = self._write_checkpoint(
            job=job,
            assignment=assignment,
            stage=DetachedWorkerCheckpointStage.LIMIT_CHECKED,
            resume_action=DetachedWorkerResumeAction.NONE,
            recommendation="RUN02 preflight passed; dispatch exactly one host-side Codex job.",
            heartbeat=heartbeat,
            last_command="host_codex_supervisor.run_once.dispatch",
        )
        if self._stop_requested.is_set():
            self._release_lock(lock, AssignmentLockReleaseReason.CANCELLED, heartbeat, "Stop requested before dispatch.")
            return self._remember(
                HostCodexSupervisorStatus(
                    service_state=HostCodexSupervisorServiceState.STOPPED,
                    reason=HostCodexSupervisorReason.SHUTDOWN_REQUESTED,
                    worker_id=self.worker_id,
                    active_job_id=job.id,
                    active_assignment_id=assignment.id,
                    heartbeat_at=heartbeat,
                    latest_blocking_reason="Stop requested after preflight and before executor launch.",
                    checkpoint_path=checkpoint_path,
                    preflight_allowed=True,
                    latest_limit_observation_id=_record_id(limit_record),
                    pre_stage_limit_observation_id=decision.limit_observation_id or _record_id(limit_record),
                )
            )

        try:
            outcome = self.runner.run_job(job)
        except Exception as exc:  # noqa: BLE001 - any executor exception must become durable state.
            return self._executor_exception(job, assignment, lock, exc, heartbeat=heartbeat)

        return self._reconcile(job, assignment, lock, outcome, decision, heartbeat=heartbeat)

    def run_until_stopped(self, *, max_iterations: int | None = None) -> HostCodexSupervisorStatus:
        """Run continuous polling until stopped, blocked, or max_iterations is reached."""

        iterations = 0
        while not self._stop_requested.is_set():
            result = self.run_once()
            if result.status.service_state in {
                HostCodexSupervisorServiceState.BLOCKED,
                HostCodexSupervisorServiceState.STOPPED,
            }:
                return result.status
            iterations += 1
            if max_iterations is not None and iterations >= max_iterations:
                return result.status
            if result.status.service_state is HostCodexSupervisorServiceState.IDLE:
                self._idle_wait(self.poll_interval_seconds)
        heartbeat = self._now()
        return self._remember(
            HostCodexSupervisorStatus(
                service_state=HostCodexSupervisorServiceState.STOPPED,
                reason=HostCodexSupervisorReason.SHUTDOWN_REQUESTED,
                worker_id=self.worker_id,
                heartbeat_at=heartbeat,
                next_poll_at="",
                latest_blocking_reason="Stop requested before next poll.",
            )
        ).status

    def _claim_assignment(
        self,
        job: CodexJobArtifact,
        assignment: AgentAssignment,
        *,
        heartbeat: str,
    ) -> tuple[AgentAssignment, AssignmentLock] | HostCodexSupervisorResult:
        expected_worker = assignment.worker_id.strip() or self.worker_id
        active_lock = self.lock_store.active_lock_for(job.jira_issue_key, job.role)
        if active_lock is not None and active_lock.worker_session_id != expected_worker:
            return self._blocked(
                reason=HostCodexSupervisorReason.FOREIGN_LOCK,
                job=job,
                assignment=assignment,
                message=f"Active lock is owned by {active_lock.worker_session_id}; expected {expected_worker}.",
                heartbeat=heartbeat,
            )
        if active_lock is None and assignment.status is AssignmentStatus.IN_PROGRESS:
            return self._blocked(
                reason=HostCodexSupervisorReason.LOST_LEASE,
                job=job,
                assignment=assignment,
                message="Assignment is in progress but no active lease exists; conservative recovery required.",
                heartbeat=heartbeat,
            )
        lock = active_lock or acquire_assignment_lock(
            jira_issue_key=job.jira_issue_key,
            role=job.role,
            worker_session_id=expected_worker,
            acquired_at=heartbeat,
            dependency_gate_passed=True,
            workspace_path=assignment.paths.workspace_path or job.target_repo_path,
        )
        if active_lock is None:
            self.lock_store.create_lock(lock)

        if assignment.status is AssignmentStatus.QUEUED:
            assignment = assign_worker(
                assignment,
                worker_id=expected_worker,
                codex_job_id=job.id,
                started_at=heartbeat,
                updated_at=heartbeat,
            )
            self.assignment_store.save_assignment(assignment)
        if assignment.status is AssignmentStatus.ASSIGNED:
            assignment = mark_assignment_in_progress(assignment, updated_at=heartbeat)
            self.assignment_store.save_assignment(assignment)
        if assignment.status is not AssignmentStatus.IN_PROGRESS:
            return self._blocked(
                reason=HostCodexSupervisorReason.ASSIGNMENT_NOT_ELIGIBLE,
                job=job,
                assignment=assignment,
                message=f"Assignment status {assignment.status.value} is not executable by the host supervisor.",
                heartbeat=heartbeat,
            )
        return assignment, lock

    def _reconcile(
        self,
        job: CodexJobArtifact,
        assignment: AgentAssignment,
        lock: AssignmentLock,
        outcome: CodexRunnerOutcome,
        preflight: HostCodexPreflightDecision,
        *,
        heartbeat: str,
    ) -> HostCodexSupervisorResult:
        if outcome.status is CodexJobStatus.PAUSED_LIMIT:
            checkpoint_path = self._write_checkpoint(
                job=job,
                assignment=assignment,
                stage=DetachedWorkerCheckpointStage.PAUSED_LIMIT,
                resume_action=DetachedWorkerResumeAction.WAIT_FOR_LIMITS,
                recommendation="Codex quota paused the job; wait until reset before replaying the same request.",
                heartbeat=heartbeat,
                last_command="host_codex_supervisor.reconcile.paused_limit",
                failed_request_path=str(outcome.failed_request_path or ""),
                output_path=str(outcome.result_path),
                resume_after=self._resume_after(outcome.job_id),
            )
            self._pause_assignment(assignment, outcome, heartbeat)
            self._release_lock(lock, AssignmentLockReleaseReason.PAUSED_LIMIT, heartbeat, "Job paused on Codex limit.")
            event_path = self._emit_event(job, assignment, OrchestrationEventType.LIMIT_PAUSED, heartbeat, outcome)
            return self._remember(
                HostCodexSupervisorStatus(
                    service_state=HostCodexSupervisorServiceState.BLOCKED,
                    reason=HostCodexSupervisorReason.JOB_PAUSED_LIMIT,
                    worker_id=self.worker_id,
                    active_job_id=outcome.job_id,
                    active_assignment_id=assignment.id,
                    heartbeat_at=heartbeat,
                    next_poll_at=self._resume_after(outcome.job_id),
                    job_status=outcome.status.value,
                    assignment_status=AssignmentStatus.PAUSED_LIMIT.value,
                    latest_blocking_reason="Codex limit reached during execution.",
                    preflight_allowed=preflight.allowed,
                    latest_limit_observation_id=_record_id(self._latest_limit_record()),
                    pre_stage_limit_observation_id=preflight.limit_observation_id,
                    checkpoint_path=checkpoint_path,
                    event_path=event_path,
                    result_path=str(outcome.result_path),
                    log_path=str(outcome.log_path),
                    failed_request_path=str(outcome.failed_request_path or ""),
                ),
                runner_outcome=outcome,
            )
        if outcome.status is CodexJobStatus.FAILED:
            checkpoint_path = self._write_checkpoint(
                job=job,
                assignment=assignment,
                stage=DetachedWorkerCheckpointStage.FAILED,
                resume_action=DetachedWorkerResumeAction.MANUAL_RECOVERY,
                recommendation="Executor returned a failed result; inspect failed request artifact before retry.",
                heartbeat=heartbeat,
                last_command="host_codex_supervisor.reconcile.failed",
                failed_request_path=str(outcome.failed_request_path or outcome.log_path),
                output_path=str(outcome.result_path),
            )
            self._fail_assignment(assignment, "Codex execution failed.", heartbeat)
            self._release_lock(lock, AssignmentLockReleaseReason.FAILED, heartbeat, "Job failed.")
            return self._remember(
                HostCodexSupervisorStatus(
                    service_state=HostCodexSupervisorServiceState.BLOCKED,
                    reason=HostCodexSupervisorReason.JOB_FAILED,
                    worker_id=self.worker_id,
                    active_job_id=outcome.job_id,
                    active_assignment_id=assignment.id,
                    heartbeat_at=heartbeat,
                    job_status=outcome.status.value,
                    assignment_status=AssignmentStatus.FAILED.value,
                    latest_blocking_reason="Codex execution failed; manual recovery required.",
                    preflight_allowed=preflight.allowed,
                    pre_stage_limit_observation_id=preflight.limit_observation_id,
                    checkpoint_path=checkpoint_path,
                    result_path=str(outcome.result_path),
                    log_path=str(outcome.log_path),
                    failed_request_path=str(outcome.failed_request_path or ""),
                ),
                runner_outcome=outcome,
            )

        completed_assignment = self._complete_assignment(assignment, outcome, heartbeat)
        self._release_lock(lock, AssignmentLockReleaseReason.COMPLETED, heartbeat, "Job completed.")
        checkpoint_path = self._write_checkpoint(
            job=job,
            assignment=completed_assignment,
            stage=DetachedWorkerCheckpointStage.COMPLETED,
            resume_action=DetachedWorkerResumeAction.NONE,
            recommendation="Codex stage completed and durable result was reconciled.",
            heartbeat=heartbeat,
            last_command="host_codex_supervisor.reconcile.completed",
            output_path=str(outcome.result_path),
            evidence_path=str(outcome.log_path),
        )
        post_limit_observation_id = ""
        try:
            post_limit = self._refresh_limit_after_stage(job, heartbeat)
            post_limit_observation_id = _record_id(post_limit)
        except Exception as exc:  # noqa: BLE001 - fail closed on any quota read or persistence failure.
            unknown_record = self._record_unknown_post_stage_limit(job, heartbeat, exc)
            return self._remember(
                HostCodexSupervisorStatus(
                    service_state=HostCodexSupervisorServiceState.BLOCKED,
                    reason=HostCodexSupervisorReason.POST_STAGE_LIMIT_REFRESH_FAILED,
                    worker_id=self.worker_id,
                    active_job_id=outcome.job_id,
                    active_assignment_id=completed_assignment.id,
                    heartbeat_at=heartbeat,
                    job_status=outcome.status.value,
                    assignment_status=completed_assignment.status.value,
                    latest_blocking_reason=(
                        "Post-stage account/rateLimits/read failed; completed result preserved and next work blocked."
                    ),
                    preflight_allowed=preflight.allowed,
                    latest_limit_observation_id=_record_id(unknown_record),
                    pre_stage_limit_observation_id=preflight.limit_observation_id,
                    post_stage_limit_observation_id=_record_id(unknown_record),
                    checkpoint_path=checkpoint_path,
                    result_path=str(outcome.result_path),
                    log_path=str(outcome.log_path),
                ),
                runner_outcome=outcome,
            )
        event_path = self._emit_event(
            job,
            completed_assignment,
            OrchestrationEventType.ASSIGNMENT_COMPLETED,
            heartbeat,
            outcome,
        )
        return self._remember(
            HostCodexSupervisorStatus(
                service_state=HostCodexSupervisorServiceState.IDLE,
                reason=HostCodexSupervisorReason.JOB_COMPLETED,
                worker_id=self.worker_id,
                active_job_id=outcome.job_id,
                active_assignment_id=completed_assignment.id,
                heartbeat_at=heartbeat,
                next_poll_at=_plus_seconds(heartbeat, self.poll_interval_seconds),
                job_status=outcome.status.value,
                assignment_status=completed_assignment.status.value,
                preflight_allowed=preflight.allowed,
                latest_limit_observation_id=post_limit_observation_id,
                pre_stage_limit_observation_id=preflight.limit_observation_id,
                post_stage_limit_observation_id=post_limit_observation_id,
                checkpoint_path=checkpoint_path,
                event_path=event_path,
                result_path=str(outcome.result_path),
                log_path=str(outcome.log_path),
            ),
            runner_outcome=outcome,
        )

    def _preflight_missing(
        self,
        job: CodexJobArtifact,
        assignment: AgentAssignment,
        lock: AssignmentLock,
        limit_record: CodexLimitAvailabilityRecord | None,
        *,
        heartbeat: str,
    ) -> HostCodexSupervisorResult:
        decision = HostCodexPreflightDecision(
            allowed=False,
            issues=(
                HostCodexPreflightIssue(
                    HostCodexPreflightIssueKind.LIMIT_REFRESH_MISSING,
                    "preflight_provider",
                    "Host supervisor requires a RUN02 preflight provider before executor launch.",
                ),
            ),
            host_workspace_path=assignment.paths.workspace_path or job.target_repo_path,
            limit_observation_id=_record_id(limit_record),
        )
        return self._preflight_blocked(
            job,
            assignment,
            lock,
            decision,
            heartbeat=heartbeat,
            reason=HostCodexSupervisorReason.PREFLIGHT_MISSING,
        )

    def _preflight_blocked(
        self,
        job: CodexJobArtifact,
        assignment: AgentAssignment,
        lock: AssignmentLock,
        decision: HostCodexPreflightDecision,
        *,
        heartbeat: str,
        reason: HostCodexSupervisorReason = HostCodexSupervisorReason.PREFLIGHT_BLOCKED,
    ) -> HostCodexSupervisorResult:
        message = render_host_codex_preflight_decision(decision)
        checkpoint_path = self._write_checkpoint(
            job=job,
            assignment=assignment,
            stage=DetachedWorkerCheckpointStage.WORKSPACE_READY,
            resume_action=DetachedWorkerResumeAction.RECHECK_GATES,
            recommendation=message,
            heartbeat=heartbeat,
            last_command="host_codex_supervisor.preflight",
        )
        return self._remember(
            HostCodexSupervisorStatus(
                service_state=HostCodexSupervisorServiceState.BLOCKED,
                reason=reason,
                worker_id=self.worker_id,
                active_job_id=job.id,
                active_assignment_id=assignment.id,
                heartbeat_at=heartbeat,
                next_poll_at=_plus_seconds(heartbeat, self.poll_interval_seconds),
                job_status=job.status.value,
                assignment_status=assignment.status.value,
                latest_blocking_reason=message,
                preflight_allowed=False,
                preflight_blockers=decision.blocking_reasons,
                latest_limit_observation_id=decision.limit_observation_id,
                pre_stage_limit_observation_id=decision.limit_observation_id,
                checkpoint_path=checkpoint_path,
            )
        )

    def _executor_exception(
        self,
        job: CodexJobArtifact,
        assignment: AgentAssignment,
        lock: AssignmentLock,
        exc: Exception,
        *,
        heartbeat: str,
    ) -> HostCodexSupervisorResult:
        error_summary = redact_failed_request_text(str(exc) or exc.__class__.__name__).value
        failed_path = self._write_supervisor_artifact(
            job,
            "executor-exception.json",
            {
                "job_id": job.id,
                "assignment_id": assignment.id,
                "error_summary": error_summary,
                "recorded_at": heartbeat,
            },
        )
        failed_job = replace(
            job,
            status=CodexJobStatus.FAILED,
            failed_request_path=str(failed_path),
            updated_at=heartbeat,
        )
        self.runner.job_store.write(failed_job)
        self._fail_assignment(assignment, error_summary, heartbeat)
        self._release_lock(lock, AssignmentLockReleaseReason.FAILED, heartbeat, "Executor exception.")
        checkpoint_path = self._write_checkpoint(
            job=failed_job,
            assignment=assignment,
            stage=DetachedWorkerCheckpointStage.FAILED,
            resume_action=DetachedWorkerResumeAction.MANUAL_RECOVERY,
            recommendation="Executor raised before returning a structured outcome; inspect durable exception artifact.",
            heartbeat=heartbeat,
            last_command="host_codex_supervisor.executor_exception",
            failed_request_path=str(failed_path),
        )
        return self._remember(
            HostCodexSupervisorStatus(
                service_state=HostCodexSupervisorServiceState.BLOCKED,
                reason=HostCodexSupervisorReason.EXECUTOR_EXCEPTION,
                worker_id=self.worker_id,
                active_job_id=job.id,
                active_assignment_id=assignment.id,
                heartbeat_at=heartbeat,
                job_status=CodexJobStatus.FAILED.value,
                assignment_status=AssignmentStatus.FAILED.value,
                latest_blocking_reason=error_summary,
                checkpoint_path=checkpoint_path,
                failed_request_path=str(failed_path),
            )
        )

    def _assignment_for_job(self, job: CodexJobArtifact) -> AgentAssignment | None:
        job_path = str(self.runner.job_store.job_path(job.id))
        candidates = self.assignment_store.list_assignments()
        for assignment in candidates:
            if assignment.codex_job_id == job.id:
                return assignment
        for assignment in candidates:
            if assignment.paths.codex_job_path == job_path:
                return assignment
        for assignment in candidates:
            if assignment.jira_issue_key == job.jira_issue_key and assignment.role == job.role:
                return assignment
        return None

    def _duplicate_active_job(self) -> CodexJobArtifact | None:
        active = self.runner.job_store.list_jobs(status=CodexJobStatus.RUNNING)
        return active[0] if active else None

    def _latest_limit_record(self) -> CodexLimitAvailabilityRecord | None:
        if self.limit_store is None:
            return None
        return self.limit_store.latest_record(
            account_scope_id=self.limit_account_scope_id,
            bucket_id=self.limit_bucket_id,
        )

    def _refresh_limit_after_stage(
        self,
        job: CodexJobArtifact,
        heartbeat: str,
    ) -> CodexLimitAvailabilityRecord | None:
        if self.limit_reader is None or self.limit_store is None:
            return self._latest_limit_record()
        payload = self.limit_reader.read(cancel_event=self._stop_requested)
        observed_at = self._now()
        result = refresh_codex_limit_from_payload(
            payload,
            record_id=_safe_record_id(f"post-{job.id}-{observed_at}"),
            observed_at=observed_at,
            cutoff_percent=self.limit_cutoff_percent,
            account_scope_id=self.limit_account_scope_id or "default",
            selected_bucket_id=self.limit_bucket_id,
            note=f"Post-stage refresh after {job.id} at {heartbeat}.",
        )
        selected = self.limit_store.write_record_and_select_latest(
            result.record,
            account_scope_id=self.limit_account_scope_id,
            bucket_id=self.limit_bucket_id,
        )
        return selected or result.record

    def _record_unknown_post_stage_limit(
        self,
        job: CodexJobArtifact,
        heartbeat: str,
        exc: Exception,
    ) -> CodexLimitAvailabilityRecord | None:
        if self.limit_store is None:
            return None
        record = build_unknown_codex_limit_record(
            record_id=_safe_record_id(f"post-{job.id}-unknown-{heartbeat}"),
            observed_at=self._now(),
            source=CodexLimitObservationSource.EXPLICIT_FAILURE,
            note=redact_failed_request_text(str(exc)).value,
            account_scope_id=self.limit_account_scope_id or "default",
            bucket_id=self.limit_bucket_id,
        )
        self.limit_store.write_record(record)
        return record

    def _complete_assignment(
        self,
        assignment: AgentAssignment,
        outcome: CodexRunnerOutcome,
        heartbeat: str,
    ) -> AgentAssignment:
        current = self.assignment_store.read_assignment(assignment.id)
        if current.status is AssignmentStatus.COMPLETED:
            return current
        if current.status is AssignmentStatus.ASSIGNED:
            current = mark_assignment_in_progress(current, updated_at=heartbeat)
            self.assignment_store.save_assignment(current)
        completed = complete_assignment(
            current,
            output_path=str(outcome.result_path),
            evidence_path=str(outcome.log_path),
            completed_at=heartbeat,
        )
        self.assignment_store.save_assignment(completed)
        return completed

    def _pause_assignment(self, assignment: AgentAssignment, outcome: CodexRunnerOutcome, heartbeat: str) -> None:
        current = self.assignment_store.read_assignment(assignment.id)
        if current.status is AssignmentStatus.PAUSED_LIMIT:
            return
        if current.status is AssignmentStatus.ASSIGNED:
            current = mark_assignment_in_progress(current, updated_at=heartbeat)
            self.assignment_store.save_assignment(current)
        if current.status is AssignmentStatus.IN_PROGRESS:
            paused = pause_assignment_for_limit(
                current,
                failed_request_path=str(outcome.failed_request_path or ""),
                pause_reason="codex_limit_reached",
                updated_at=heartbeat,
            )
            self.assignment_store.save_assignment(paused)

    def _fail_assignment(self, assignment: AgentAssignment, reason: str, heartbeat: str) -> None:
        current = self.assignment_store.read_assignment(assignment.id)
        if current.status is AssignmentStatus.FAILED:
            return
        failed = fail_assignment(current, failure_reason=reason, updated_at=heartbeat)
        self.assignment_store.save_assignment(failed)

    def _release_lock(
        self,
        lock: AssignmentLock,
        reason: AssignmentLockReleaseReason,
        heartbeat: str,
        audit_note: str,
    ) -> None:
        active = self.lock_store.active_lock_for(lock.jira_issue_key, lock.role)
        if active is None or active.status is not AssignmentLockStatus.ACTIVE:
            return
        if active.worker_session_id != lock.worker_session_id:
            return
        self.lock_store.release_lock(
            active.jira_issue_key,
            active.role,
            active.worker_session_id,
            released_at=heartbeat,
            reason=reason,
            audit_note=audit_note,
        )

    def _emit_event(
        self,
        job: CodexJobArtifact,
        assignment: AgentAssignment,
        event_type: OrchestrationEventType,
        heartbeat: str,
        outcome: CodexRunnerOutcome,
    ) -> str:
        if self.event_queue is None:
            return ""
        event = build_orchestration_event(
            event_id=_safe_record_id(f"event-{event_type.value}-{assignment.id}-{outcome.job_id}"),
            event_type=event_type,
            idempotency_key=orchestration_event_idempotency_key(
                event_type=event_type,
                jira_issue_key=job.jira_issue_key,
                source_assignment_id=assignment.id,
                scope_key=outcome.job_id,
            ),
            source_role=job.role,
            created_at=heartbeat,
            jira_issue_key=job.jira_issue_key,
            source_assignment_id=assignment.id,
            project_id=assignment.project_id,
            project_name=assignment.project_name,
            project_root=assignment.project_root,
            repository=assignment.repository,
            jira_project_key=assignment.jira_project_key,
            correlation_id=outcome.job_id,
            scope_key=outcome.status.value,
            payload={
                "job_status": outcome.status.value,
                "result_path": str(outcome.result_path),
                "log_path": str(outcome.log_path),
                "blocked_note": "Supervisor emits events only after durable outcome reconciliation.",
            },
            evidence_paths=tuple(
                path
                for path in (str(outcome.result_path), str(outcome.log_path), str(outcome.failed_request_path or ""))
                if path
            ),
        )
        location = self.event_queue.enqueue_event(event)
        return str(location.path)

    def _write_checkpoint(
        self,
        *,
        job: CodexJobArtifact,
        assignment: AgentAssignment,
        stage: DetachedWorkerCheckpointStage,
        resume_action: DetachedWorkerResumeAction,
        recommendation: str,
        heartbeat: str,
        last_command: str,
        failed_request_path: str = "",
        output_path: str = "",
        evidence_path: str = "",
        resume_after: str = "",
    ) -> str:
        checkpoint = DetachedWorkerCheckpoint(
            id=_safe_record_id(f"{assignment.id}-{stage.value}-{heartbeat}-{uuid.uuid4().hex[:8]}"),
            assignment_id=assignment.id,
            worker_id=assignment.worker_id or self.worker_id,
            role=assignment.role,
            project_id=assignment.project_id or "default",
            project_name=assignment.project_name,
            project_root=assignment.project_root,
            repository=assignment.repository,
            jira_project_key=assignment.jira_project_key,
            sprint="runtime-completion",
            jira_issue_key=assignment.jira_issue_key,
            branch_name=assignment.branch_name or job.branch_name,
            worktree_path=assignment.paths.workspace_path or job.target_repo_path,
            stage=stage,
            last_command=last_command,
            resume_action=resume_action,
            resume_recommendation=recommendation,
            created_at=heartbeat,
            updated_at=heartbeat,
            attempt_count=job.attempt_count,
            codex_job_id=job.id,
            context_pack_path=job.context_pack_path,
            failed_request_path=failed_request_path,
            output_path=output_path or job.output_path,
            evidence_path=evidence_path,
            resume_after=resume_after,
        )
        location = self.checkpoint_store.write(checkpoint)
        return str(location.path)

    def _write_supervisor_artifact(self, job: CodexJobArtifact, name: str, payload: Mapping[str, Any]) -> Path:
        path = self.logs_root / job.jira_issue_key / job.id / name
        _atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
        return path

    def _resume_after(self, job_id: str) -> str:
        try:
            return self.runner.job_store.read(job_id).resume.resume_after
        except Exception:  # noqa: BLE001 - resume_after is best-effort status metadata.
            return ""

    def _blocked(
        self,
        *,
        reason: HostCodexSupervisorReason,
        job: CodexJobArtifact,
        message: str,
        heartbeat: str,
        assignment: AgentAssignment | None = None,
    ) -> HostCodexSupervisorResult:
        checkpoint_path = ""
        if assignment is not None:
            checkpoint_path = self._write_checkpoint(
                job=job,
                assignment=assignment,
                stage=DetachedWorkerCheckpointStage.WORKSPACE_READY,
                resume_action=DetachedWorkerResumeAction.RECHECK_GATES,
                recommendation=message,
                heartbeat=heartbeat,
                last_command=f"host_codex_supervisor.blocked.{reason.value}",
            )
        return self._remember(
            HostCodexSupervisorStatus(
                service_state=HostCodexSupervisorServiceState.BLOCKED,
                reason=reason,
                worker_id=self.worker_id,
                active_job_id=job.id,
                active_assignment_id=assignment.id if assignment else "",
                heartbeat_at=heartbeat,
                next_poll_at=_plus_seconds(heartbeat, self.poll_interval_seconds),
                job_status=job.status.value,
                assignment_status=assignment.status.value if assignment else "",
                latest_blocking_reason=message,
                latest_limit_observation_id=_record_id(self._latest_limit_record()),
                checkpoint_path=checkpoint_path,
            )
        )

    def _remember(
        self,
        status: HostCodexSupervisorStatus,
        *,
        runner_outcome: CodexRunnerOutcome | None = None,
    ) -> HostCodexSupervisorResult:
        self._last_status = _redact_status(status)
        return HostCodexSupervisorResult(status=self._last_status, runner_outcome=runner_outcome)


def host_codex_supervisor_status_to_dict(status: HostCodexSupervisorStatus) -> dict[str, Any]:
    """Convert supervisor status into JSON-safe operator output."""

    safe = _redact_status(status)
    return {
        "service_state": safe.service_state.value,
        "reason": safe.reason.value,
        "worker_id": safe.worker_id,
        "active_job_id": safe.active_job_id,
        "active_assignment_id": safe.active_assignment_id,
        "active_child_session_id": safe.active_child_session_id,
        "heartbeat_at": safe.heartbeat_at,
        "next_poll_at": safe.next_poll_at,
        "job_status": safe.job_status,
        "assignment_status": safe.assignment_status,
        "latest_blocking_reason": safe.latest_blocking_reason,
        "preflight_allowed": safe.preflight_allowed,
        "preflight_blockers": list(safe.preflight_blockers),
        "latest_limit_observation_id": safe.latest_limit_observation_id,
        "pre_stage_limit_observation_id": safe.pre_stage_limit_observation_id,
        "post_stage_limit_observation_id": safe.post_stage_limit_observation_id,
        "checkpoint_path": safe.checkpoint_path,
        "event_path": safe.event_path,
        "result_path": safe.result_path,
        "log_path": safe.log_path,
        "failed_request_path": safe.failed_request_path,
    }


def host_codex_supervisor_result_to_dict(result: HostCodexSupervisorResult) -> dict[str, Any]:
    """Convert one supervisor run result into CLI/API output."""

    payload: dict[str, Any] = {"status": host_codex_supervisor_status_to_dict(result.status)}
    if result.runner_outcome is not None:
        payload["runner_outcome"] = {
            "job_id": result.runner_outcome.job_id,
            "status": result.runner_outcome.status.value,
            "job_path": str(result.runner_outcome.job_path),
            "result_path": str(result.runner_outcome.result_path),
            "log_path": str(result.runner_outcome.log_path),
            "failed_request_path": str(result.runner_outcome.failed_request_path or ""),
            "paused_assignment_path": str(result.runner_outcome.paused_assignment_path or ""),
        }
    return payload


def _record_id(record: CodexLimitAvailabilityRecord | None) -> str:
    return record.id if record is not None else ""


def _redact_status(status: HostCodexSupervisorStatus) -> HostCodexSupervisorStatus:
    return replace(
        status,
        latest_blocking_reason=redact_failed_request_text(status.latest_blocking_reason).value,
        preflight_blockers=tuple(redact_failed_request_text(value).value for value in status.preflight_blockers),
    )


def _safe_record_id(value: str) -> str:
    return "".join(character if character.isalnum() or character in "_.-" else "-" for character in value).strip("-")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _plus_seconds(timestamp: str, seconds: int) -> str:
    normalized = timestamp.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    return datetime.fromtimestamp(parsed.timestamp() + seconds, timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


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
