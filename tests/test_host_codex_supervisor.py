from pathlib import Path
from typing import Any

from agentic_boilerplate.domain import (
    AgentAssignment,
    AgentRole,
    AssignmentPaths,
    AssignmentStatus,
    CodexEffortMode,
    CodexJobArtifact,
    CodexJobStatus,
    CodexLimitObservationSource,
    CodexLimitWindowAvailability,
    CodexLimitWindowStatus,
    OrchestrationEventType,
    ReasoningLevel,
    build_single_pool_codex_limit_availability_record,
)
from agentic_boilerplate.runtime import (
    CodexRunnerExecution,
    HostCodexPreflightDecision,
    HostCodexPreflightIssue,
    HostCodexPreflightIssueKind,
    HostCodexSupervisor,
    HostCodexSupervisorReason,
    HostCodexSupervisorServiceState,
    HostSideCodexRunner,
)
from agentic_boilerplate.storage import (
    FileAgentAssignmentStore,
    FileAssignmentLockStore,
    FileCodexJobStore,
    FileCodexLimitAvailabilityStore,
    FileCodexPauseStore,
    FileDetachedWorkerCheckpointStore,
    FileOrchestrationEventQueue,
)

NOW = "2026-09-12T12:00:00Z"
LIMIT_OBSERVED_AT = "2026-09-12T11:59:00Z"


class FakeExecutor:
    def __init__(self, execution: CodexRunnerExecution | Exception) -> None:
        self.execution = execution
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        if isinstance(self.execution, Exception):
            raise self.execution
        return self.execution


class FakeLimitReader:
    def __init__(self, payload: dict[str, Any] | Exception) -> None:
        self.payload = payload
        self.calls = 0

    def read(self, *, cancel_event=None):
        self.calls += 1
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def test_supervisor_claims_executes_reconciles_and_emits_event(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    executor = FakeExecutor(CodexRunnerExecution(output_text="done", log_text="ok"))
    bundle.limit_store.write_record(_limit_record())
    job, assignment = bundle.write_queued_work()
    supervisor = bundle.supervisor(executor=executor, limit_reader=FakeLimitReader(_rate_limits_payload()))

    result = supervisor.run_once()

    assert result.status.service_state is HostCodexSupervisorServiceState.IDLE
    assert result.status.reason is HostCodexSupervisorReason.JOB_COMPLETED
    assert bundle.job_store.read(job.id).status is CodexJobStatus.COMPLETED
    assert bundle.assignment_store.read_assignment(assignment.id).status is AssignmentStatus.COMPLETED
    assert bundle.lock_store.active_lock_for(job.jira_issue_key, job.role) is None
    assert bundle.event_queue.list_events()[0].event_type is OrchestrationEventType.ASSIGNMENT_COMPLETED
    assert executor.requests[0].jira_issue_key == "AGENT-966"


def test_supervisor_rejects_duplicate_running_job(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    running, _ = bundle.write_queued_work(job_id="job-running")
    bundle.job_store.write(_job(tmp_path, job_id=running.id, status=CodexJobStatus.RUNNING))
    bundle.write_queued_work(job_id="job-next", assignment_id="assignment-next")
    supervisor = bundle.supervisor()

    result = supervisor.run_once()

    assert result.status.service_state is HostCodexSupervisorServiceState.BLOCKED
    assert result.status.reason is HostCodexSupervisorReason.DUPLICATE_ACTIVE_JOB
    assert result.status.active_job_id == "job-running"


def test_supervisor_keeps_preflight_block_with_owned_lock_for_recheck(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    bundle.limit_store.write_record(_limit_record())
    job, assignment = bundle.write_queued_work()
    supervisor = bundle.supervisor(preflight_allowed=False)

    result = supervisor.run_once()

    stored = bundle.assignment_store.read_assignment(assignment.id)
    assert result.status.reason is HostCodexSupervisorReason.PREFLIGHT_BLOCKED
    assert stored.status is AssignmentStatus.IN_PROGRESS
    assert bundle.lock_store.active_lock_for(job.jira_issue_key, job.role) is not None
    assert "Product Owner blocker" in result.status.latest_blocking_reason


def test_supervisor_detects_lost_lease_before_dispatch(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    bundle.limit_store.write_record(_limit_record())
    job, assignment = bundle.write_queued_work()
    bundle.assignment_store.save_assignment(
        _assignment(
            tmp_path,
            assignment_id=assignment.id,
            job_id=job.id,
            status=AssignmentStatus.IN_PROGRESS,
            worker_id="host-codex-supervisor",
            codex_job_id=job.id,
        )
    )
    supervisor = bundle.supervisor()

    result = supervisor.run_once()

    assert result.status.service_state is HostCodexSupervisorServiceState.BLOCKED
    assert result.status.reason is HostCodexSupervisorReason.LOST_LEASE


def test_supervisor_converts_executor_exception_to_failed_artifacts(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    bundle.limit_store.write_record(_limit_record())
    job, assignment = bundle.write_queued_work()
    supervisor = bundle.supervisor(executor=FakeExecutor(RuntimeError("token=abc123")))

    result = supervisor.run_once()

    failed_job = bundle.job_store.read(job.id)
    failed_assignment = bundle.assignment_store.read_assignment(assignment.id)
    assert result.status.reason is HostCodexSupervisorReason.EXECUTOR_EXCEPTION
    assert failed_job.status is CodexJobStatus.FAILED
    assert failed_job.failed_request_path.endswith("executor-exception.json")
    assert failed_assignment.status is AssignmentStatus.FAILED
    assert "abc123" not in result.status.latest_blocking_reason


def test_supervisor_stop_after_preflight_releases_lock_without_executor_launch(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    bundle.limit_store.write_record(_limit_record())
    job, _ = bundle.write_queued_work()
    supervisor_ref = {}

    def provider(job, assignment, lock, limit_record, now):
        supervisor_ref["supervisor"].request_stop()
        return _preflight_decision(True, limit_record)

    supervisor = bundle.supervisor(preflight_provider=provider)
    supervisor_ref["supervisor"] = supervisor

    result = supervisor.run_once()

    assert result.status.service_state is HostCodexSupervisorServiceState.STOPPED
    assert result.status.reason is HostCodexSupervisorReason.SHUTDOWN_REQUESTED
    assert bundle.lock_store.active_lock_for(job.jira_issue_key, job.role) is None


def test_supervisor_blocks_next_work_when_post_stage_limit_refresh_fails(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    bundle.limit_store.write_record(_limit_record())
    job, assignment = bundle.write_queued_work()
    supervisor = bundle.supervisor(
        executor=FakeExecutor(CodexRunnerExecution(output_text="done", log_text="ok")),
        limit_reader=FakeLimitReader(RuntimeError("app server unavailable")),
    )

    result = supervisor.run_once()

    assert result.status.reason is HostCodexSupervisorReason.POST_STAGE_LIMIT_REFRESH_FAILED
    assert bundle.job_store.read(job.id).status is CodexJobStatus.COMPLETED
    assert bundle.assignment_store.read_assignment(assignment.id).status is AssignmentStatus.COMPLETED
    assert bundle.lock_store.active_lock_for(job.jira_issue_key, job.role) is None
    assert result.status.latest_limit_observation_id.startswith("post-job-966-unknown")


def test_supervisor_run_loop_polls_again_after_idle_until_bound_is_reached(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    idle_waits: list[int] = []
    supervisor = bundle.supervisor(idle_wait=lambda seconds: idle_waits.append(seconds) or False)

    status = supervisor.run_until_stopped(max_iterations=2)

    assert status.service_state is HostCodexSupervisorServiceState.IDLE
    assert status.reason is HostCodexSupervisorReason.NO_JOB
    assert idle_waits == [300]


class _Bundle:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.job_store = FileCodexJobStore(tmp_path / "codex-jobs")
        self.pause_store = FileCodexPauseStore(tmp_path / "codex-results")
        self.assignment_store = FileAgentAssignmentStore(tmp_path / "agent-state")
        self.lock_store = FileAssignmentLockStore(tmp_path / "agent-state")
        self.checkpoint_store = FileDetachedWorkerCheckpointStore(tmp_path / "agent-state")
        self.event_queue = FileOrchestrationEventQueue(tmp_path / "agent-state")
        self.limit_store = FileCodexLimitAvailabilityStore(tmp_path / "codex-limits")
        self.workspace = tmp_path / "workspaces" / "AGENT-966" / "developer"
        self.workspace.mkdir(parents=True)
        (self.workspace / ".git").mkdir()

    def write_queued_work(
        self,
        *,
        job_id: str = "job-966",
        assignment_id: str = "assignment-966",
    ) -> tuple[CodexJobArtifact, AgentAssignment]:
        job = _job(self.tmp_path, job_id=job_id)
        assignment = _assignment(self.tmp_path, assignment_id=assignment_id, job_id=job_id)
        self.job_store.write(job)
        self.assignment_store.save_assignment(assignment)
        return job, assignment

    def supervisor(
        self,
        *,
        executor: FakeExecutor | None = None,
        limit_reader: FakeLimitReader | None = None,
        preflight_allowed: bool = True,
        preflight_provider=None,
        idle_wait=None,
    ) -> HostCodexSupervisor:
        runner = HostSideCodexRunner(
            job_store=self.job_store,
            pause_store=self.pause_store,
            executor=executor or FakeExecutor(CodexRunnerExecution(output_text="done", log_text="ok")),
            limit_store=self.limit_store,
            logs_root=self.tmp_path / "agent-logs" / "runner",
            now=lambda: NOW,
            worker_id="host-codex-supervisor",
            limit_account_scope_id="default",
            limit_bucket_id="codex",
        )
        provider = preflight_provider or (lambda job, assignment, lock, limit_record, now: _preflight_decision(preflight_allowed, limit_record))
        return HostCodexSupervisor(
            runner=runner,
            assignment_store=self.assignment_store,
            lock_store=self.lock_store,
            checkpoint_store=self.checkpoint_store,
            event_queue=self.event_queue,
            limit_store=self.limit_store,
            limit_reader=limit_reader,
            preflight_provider=provider,
            logs_root=self.tmp_path / "agent-logs" / "host-supervisor",
            worker_id="host-codex-supervisor",
            poll_interval_seconds=300,
            limit_account_scope_id="default",
            limit_bucket_id="codex",
            idle_wait=idle_wait,
            now=lambda: NOW,
        )


def _bundle(tmp_path: Path) -> _Bundle:
    return _Bundle(tmp_path)


def _assignment(
    tmp_path: Path,
    *,
    assignment_id: str = "assignment-966",
    job_id: str = "job-966",
    status: AssignmentStatus = AssignmentStatus.QUEUED,
    worker_id: str = "",
    codex_job_id: str = "",
) -> AgentAssignment:
    return AgentAssignment(
        id=assignment_id,
        jira_issue_key="AGENT-966",
        role=AgentRole.DEVELOPER,
        status=status,
        paths=AssignmentPaths(
            context_pack_path=str(tmp_path / "context-packs" / "AGENT-966" / "context.json"),
            codex_job_path=str(tmp_path / "codex-jobs" / job_id / "job.json"),
            output_path=str(tmp_path / "codex-results" / "AGENT-966" / "result.json"),
            workspace_path=str(tmp_path / "workspaces" / "AGENT-966" / "developer"),
            evidence_path=str(tmp_path / "agent-logs" / "AGENT-966" / "evidence.md"),
        ),
        worker_id=worker_id,
        codex_job_id=codex_job_id,
        branch_name="feature/AGENT-966-host-codex-supervisor",
        project_id="agentic-boilerplate",
        project_name="Agentic Boilerplate",
        project_root=str(tmp_path / "source"),
        repository="example-org/agentic-boilerplate",
        jira_project_key="AGENT",
        created_at=NOW,
        updated_at=NOW,
    )


def _job(tmp_path: Path, *, job_id: str = "job-966", status: CodexJobStatus = CodexJobStatus.QUEUED) -> CodexJobArtifact:
    return CodexJobArtifact(
        id=job_id,
        jira_issue_key="AGENT-966",
        role=AgentRole.DEVELOPER,
        target_repo_path=str(tmp_path / "workspaces" / "AGENT-966" / "developer"),
        branch_name="feature/AGENT-966-host-codex-supervisor",
        context_pack_path=str(tmp_path / "context-packs" / "AGENT-966" / "context.json"),
        output_path=str(tmp_path / "codex-results" / "AGENT-966" / "result.json"),
        model="gpt-5.5",
        reasoning=ReasoningLevel.HIGH,
        speed="normal",
        effort_mode=CodexEffortMode.COMPLEX,
        status=status,
        created_at=NOW,
        updated_at=NOW,
    )


def _preflight_decision(allowed: bool, limit_record) -> HostCodexPreflightDecision:
    issues = ()
    if not allowed:
        issues = (
            HostCodexPreflightIssue(
                HostCodexPreflightIssueKind.PO_BLOCKERS,
                "scope.po_blocker_ids",
                "Product Owner blocker must be answered before execution.",
            ),
        )
    return HostCodexPreflightDecision(
        allowed=allowed,
        issues=issues,
        host_workspace_path="/workspace/AGENT-966/developer",
        limit_observation_id=limit_record.id if limit_record else "",
        limit_observation_source="codex_app_server" if limit_record else "",
        limit_observed_at=LIMIT_OBSERVED_AT if limit_record else "",
    )


def _limit_record(record_id: str = "availability-good"):
    window = CodexLimitWindowAvailability(
        status=CodexLimitWindowStatus.AVAILABLE,
        remaining_percent=90,
        reset_at="2026-09-12T15:00:00Z",
        observation_source=CodexLimitObservationSource.CODEX_APP_SERVER,
        observed_at=LIMIT_OBSERVED_AT,
        window_id="primary",
        label="Codex primary",
        bucket_id="codex",
        window_name="primary",
        window_duration_minutes=300,
    )
    return build_single_pool_codex_limit_availability_record(
        record_id=record_id,
        pool=window,
        account_scope_id="default",
    )


def _rate_limits_payload() -> dict[str, Any]:
    return {
        "rateLimits": {
            "limitId": "codex",
            "primary": {
                "usedPercent": 10,
                "resetsAt": 1789235467,
                "windowDurationMins": 10080,
            },
            "planType": "prolite",
            "rateLimitReachedType": None,
        }
    }
