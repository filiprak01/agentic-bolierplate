from pathlib import Path

from agentic_boilerplate.domain import AgentRole, CodexEffortMode, CodexJobStatus, ReasoningLevel
from agentic_boilerplate.domain.agent_assignment import AgentAssignment, AssignmentPaths, AssignmentStatus
from agentic_boilerplate.runtime import (
    CodexExecutionBridgeMode,
    CodexRunnerExecution,
    HostSideCodexExecutionBridge,
    HostSideCodexRunner,
)
from agentic_boilerplate.storage import FileAgentAssignmentStore, FileCodexJobStore, FileCodexPauseStore


class RecordingExecutor:
    def __init__(self, execution: CodexRunnerExecution) -> None:
        self.execution = execution
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        return self.execution


class Clock:
    def __init__(self) -> None:
        self.index = 0
        self.values = (
            "2026-08-09T20:00:00Z",
            "2026-08-09T20:01:00Z",
            "2026-08-09T20:02:00Z",
        )

    def __call__(self) -> str:
        value = self.values[min(self.index, len(self.values) - 1)]
        self.index += 1
        return value


def test_bridge_creates_host_side_codex_job_and_assigns_worker(tmp_path: Path) -> None:
    assignment_store = FileAgentAssignmentStore(tmp_path / "agent-state")
    job_store = FileCodexJobStore(tmp_path / "codex-jobs")
    pause_store = FileCodexPauseStore(tmp_path / "codex-jobs")
    assignment = _assignment(tmp_path)
    assignment_store.create_assignment(assignment)
    bridge = HostSideCodexExecutionBridge(
        assignment_store=assignment_store,
        job_store=job_store,
        pause_store=pause_store,
    )

    outcome = bridge.create_request(
        assignment,
        worker_id="developer-1",
        target_repo_path="/workspace/project",
        model="gpt-5.4",
        reasoning=ReasoningLevel.HIGH,
        speed="normal",
        effort_mode=CodexEffortMode.STANDARD,
        created_at="2026-08-09T20:00:00Z",
    )

    stored_job = job_store.read("AGENT-624")
    stored_assignment = assignment_store.read_assignment("assignment-AGENT-624")

    assert outcome.status is AssignmentStatus.ASSIGNED
    assert outcome.codex_job_path == tmp_path / "codex-jobs" / "AGENT-624" / "job.json"
    assert stored_job.status is CodexJobStatus.QUEUED
    assert stored_job.jira_issue_key == "AGENT-624"
    assert stored_job.target_repo_path == "/workspace/project"
    assert stored_job.model == "gpt-5.4"
    assert stored_assignment.worker_id == "developer-1"
    assert stored_assignment.codex_job_id == "AGENT-624"
    assert "session secrets" in outcome.message


def test_bridge_created_job_can_complete_through_host_side_runner(tmp_path: Path) -> None:
    assignment_store, job_store, pause_store, assignment = _stores_with_bridge_job(tmp_path)
    runner = HostSideCodexRunner(
        job_store=job_store,
        pause_store=pause_store,
        executor=RecordingExecutor(CodexRunnerExecution(output_text="done", log_text="runner log")),
        logs_root=tmp_path / "logs",
        now=Clock(),
    )

    outcome = runner.run_next()

    assert outcome is not None
    assert outcome.status is CodexJobStatus.COMPLETED
    assert job_store.read("AGENT-624").status is CodexJobStatus.COMPLETED
    assert assignment_store.read_assignment(assignment.id).status is AssignmentStatus.ASSIGNED


def test_bridge_created_job_pause_records_resume_metadata(tmp_path: Path) -> None:
    _, job_store, pause_store, _ = _stores_with_bridge_job(tmp_path)
    runner = HostSideCodexRunner(
        job_store=job_store,
        pause_store=pause_store,
        executor=RecordingExecutor(
            CodexRunnerExecution(
                output_text="partial",
                log_text="limit log",
                limit_reached=True,
                error_summary="Limit gate closed.",
                resume_after="2026-08-10T00:00:00Z",
            )
        ),
        logs_root=tmp_path / "logs",
        now=Clock(),
    )

    outcome = runner.run_next()
    paused_job = job_store.read("AGENT-624")

    assert outcome is not None
    assert outcome.status is CodexJobStatus.PAUSED_LIMIT
    assert paused_job.resume.resume_after == "2026-08-10T00:00:00Z"
    assert paused_job.resume.last_checkpoint_path
    assert paused_job.failed_request_path
    assert pause_store.list_paused_assignments()[0].codex_job_id == "AGENT-624"


def test_unsupported_direct_container_mode_fails_safely_with_durable_reason(tmp_path: Path) -> None:
    assignment_store = FileAgentAssignmentStore(tmp_path / "agent-state")
    job_store = FileCodexJobStore(tmp_path / "codex-jobs")
    pause_store = FileCodexPauseStore(tmp_path / "codex-jobs")
    assignment = _assignment(tmp_path)
    assignment_store.create_assignment(assignment)
    bridge = HostSideCodexExecutionBridge(
        assignment_store=assignment_store,
        job_store=job_store,
        pause_store=pause_store,
        mode=CodexExecutionBridgeMode.DIRECT_CONTAINER,
    )

    outcome = bridge.create_request(
        assignment,
        worker_id="developer-1",
        target_repo_path="/workspace/project",
        model="gpt-5.4",
        reasoning="high",
        speed="normal",
        effort_mode="standard",
        created_at="2026-08-09T20:00:00Z",
    )
    stored_assignment = assignment_store.read_assignment("assignment-AGENT-624")
    failed_request = pause_store.list_failed_requests()[0]

    assert outcome.status is AssignmentStatus.FAILED
    assert outcome.failed_request_path is not None
    assert stored_assignment.status is AssignmentStatus.FAILED
    assert stored_assignment.failure_reason == outcome.message
    assert "Direct in-container Codex execution is not supported" in failed_request.error_summary
    assert "session secrets" in failed_request.error_summary
    assert failed_request.stage_id == "codex_execution_bridge.unsupported_mode"
    assert failed_request.retry_policy == "switch_to_host_side_mode_before_retry"
    assert failed_request.suggested_next_role_action == "operator_update_worker_codex_execution_mode"
    assert failed_request.side_effect_idempotency_key == (
        "AGENT-624:assignment-AGENT-624:unsupported:direct_container"
    )


def _stores_with_bridge_job(
    tmp_path: Path,
) -> tuple[FileAgentAssignmentStore, FileCodexJobStore, FileCodexPauseStore, AgentAssignment]:
    assignment_store = FileAgentAssignmentStore(tmp_path / "agent-state")
    job_store = FileCodexJobStore(tmp_path / "codex-jobs")
    pause_store = FileCodexPauseStore(tmp_path / "codex-jobs")
    assignment = _assignment(tmp_path)
    assignment_store.create_assignment(assignment)
    bridge = HostSideCodexExecutionBridge(
        assignment_store=assignment_store,
        job_store=job_store,
        pause_store=pause_store,
    )
    bridge.create_request(
        assignment,
        worker_id="developer-1",
        target_repo_path="/workspace/project",
        model="gpt-5.4",
        reasoning="high",
        speed="normal",
        effort_mode="standard",
        created_at="2026-08-09T20:00:00Z",
    )
    return assignment_store, job_store, pause_store, assignment


def _assignment(tmp_path: Path) -> AgentAssignment:
    return AgentAssignment(
        id="assignment-AGENT-624",
        jira_issue_key="AGENT-624",
        role=AgentRole.DEVELOPER,
        status=AssignmentStatus.QUEUED,
        paths=AssignmentPaths(
            context_pack_path="data/context-packs/AGENT-624/context.json",
            codex_job_path="data/codex-jobs/AGENT-624/job.json",
            output_path=str(tmp_path / "codex-results" / "AGENT-624" / "result.json"),
        ),
        branch_name="feature/AGENT-624-host-side-codex-execution-bridge",
        created_at="2026-08-09T19:55:00Z",
        updated_at="2026-08-09T19:55:00Z",
    )
