import json
from pathlib import Path

from agentic_boilerplate.domain import (
    AgentRole,
    CodexEffortMode,
    CodexJobArtifact,
    CodexJobStatus,
    CodexLimitObservationSource,
    CodexLimitWindowAvailability,
    CodexLimitWindowStatus,
    ReasoningLevel,
    build_codex_limit_availability_record,
)
from agentic_boilerplate.runtime import CodexRunnerExecution, HostSideCodexRunner
from agentic_boilerplate.storage import FileCodexJobStore, FileCodexLimitAvailabilityStore, FileCodexPauseStore


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
            "2026-06-26T12:40:00Z",
            "2026-06-26T12:41:00Z",
            "2026-06-26T12:42:00Z",
        )

    def __call__(self) -> str:
        value = self.values[min(self.index, len(self.values) - 1)]
        self.index += 1
        return value


def test_host_side_runner_completes_next_pending_job_and_writes_outputs(tmp_path: Path) -> None:
    job_store = FileCodexJobStore(tmp_path / "jobs")
    pause_store = FileCodexPauseStore(tmp_path / "pause")
    job = _job(tmp_path, "job-001")
    job_store.create(job)
    executor = RecordingExecutor(CodexRunnerExecution(output_text="done", log_text="runner log"))
    runner = HostSideCodexRunner(
        job_store=job_store,
        pause_store=pause_store,
        executor=executor,
        logs_root=tmp_path / "logs",
        now=Clock(),
    )

    outcome = runner.run_next()

    assert outcome is not None
    assert outcome.status == CodexJobStatus.COMPLETED
    assert job_store.read("job-001").status == CodexJobStatus.COMPLETED
    assert job_store.read("job-001").attempt_count == 1
    assert json.loads((tmp_path / "results" / "job-001.json").read_text(encoding="utf-8"))["output_text"] == "done"
    assert (tmp_path / "logs" / "AGENT-43" / "job-001.log").read_text(encoding="utf-8") == "runner log"


def test_host_side_runner_passes_model_reasoning_speed_and_context_to_executor(tmp_path: Path) -> None:
    job_store = FileCodexJobStore(tmp_path / "jobs")
    pause_store = FileCodexPauseStore(tmp_path / "pause")
    job_store.create(_job(tmp_path, "job-001"))
    executor = RecordingExecutor(CodexRunnerExecution(output_text="done"))
    runner = HostSideCodexRunner(
        job_store=job_store,
        pause_store=pause_store,
        executor=executor,
        logs_root=tmp_path / "logs",
        now=Clock(),
    )

    runner.run_next()

    request = executor.requests[0]
    assert request.model == "gpt-5.5"
    assert request.reasoning == "high"
    assert request.speed == "normal"
    assert request.effort_mode == "complex"
    assert request.context_pack_path == "data/context-packs/AGENT-43/context-pack.md"
    assert request.branch_name == "feature/AGENT-43-host-side-codex-runner"


def test_host_side_runner_pauses_job_and_writes_failure_artifacts_on_limit(tmp_path: Path) -> None:
    job_store = FileCodexJobStore(tmp_path / "jobs")
    pause_store = FileCodexPauseStore(tmp_path / "pause")
    job_store.create(_job(tmp_path, "job-001"))
    executor = RecordingExecutor(
        CodexRunnerExecution(
            output_text="partial",
            log_text="limit log",
            limit_reached=True,
            error_summary="OpenAI Plus limit reached.",
            resume_after="2026-06-26T17:40:00Z",
        )
    )
    runner = HostSideCodexRunner(
        job_store=job_store,
        pause_store=pause_store,
        executor=executor,
        logs_root=tmp_path / "logs",
        now=Clock(),
    )

    outcome = runner.run_next()
    paused_job = job_store.read("job-001")
    paused_assignment = pause_store.read_paused_assignment("paused-job-001-attempt-1")

    assert outcome is not None
    assert outcome.status == CodexJobStatus.PAUSED_LIMIT
    assert paused_job.status == CodexJobStatus.PAUSED_LIMIT
    assert paused_job.resume.resume_after == "2026-06-26T17:40:00Z"
    assert paused_job.resume.last_checkpoint_path == str(tmp_path / "results" / "job-001.json")
    assert paused_assignment.codex_job_id == "job-001"
    assert paused_assignment.linked_artifacts[0].path == str(tmp_path / "logs" / "AGENT-43" / "job-001.log")
    failed_request = pause_store.read_failed_request(outcome.failed_request_path.stem)
    assert failed_request.stage_id == "host_side_runner.limit_pause"
    assert failed_request.retry_policy == "retry_same_request_after_limit_reset"
    assert failed_request.suggested_next_role_action == "scheduler_retry_after_limit_reset"
    assert failed_request.side_effect_idempotency_key == "AGENT-43:job-001:1:limit_reached"
    assert outcome.failed_request_path is not None
    assert outcome.paused_assignment_path is not None


def test_host_side_runner_blocks_request_when_limit_gate_is_closed(tmp_path: Path) -> None:
    job_store = FileCodexJobStore(tmp_path / "jobs")
    pause_store = FileCodexPauseStore(tmp_path / "pause")
    limit_store = FileCodexLimitAvailabilityStore(tmp_path / "limits")
    job_store.create(_job(tmp_path, "job-001"))
    limit_store.write_record(
        build_codex_limit_availability_record(
            record_id="availability-20260626T123930Z",
            short_window=CodexLimitWindowAvailability(
                status=CodexLimitWindowStatus.AVAILABLE,
                remaining_percent=5,
                reset_at="2026-07-07T15:00:00Z",
                observation_source=CodexLimitObservationSource.OPERATOR,
                observed_at="2026-06-26T12:39:30Z",
            ),
            broad_quota=CodexLimitWindowAvailability(
                status=CodexLimitWindowStatus.AVAILABLE,
                remaining_percent=80,
                reset_at="2026-07-14T10:00:00Z",
                observation_source=CodexLimitObservationSource.OPERATOR,
                observed_at="2026-06-26T12:39:30Z",
            ),
        )
    )
    executor = RecordingExecutor(CodexRunnerExecution(output_text="should not run"))
    runner = HostSideCodexRunner(
        job_store=job_store,
        pause_store=pause_store,
        limit_store=limit_store,
        executor=executor,
        logs_root=tmp_path / "logs",
        now=Clock(),
    )

    outcome = runner.run_next()
    paused_job = job_store.read("job-001")

    assert outcome is not None
    assert outcome.status == CodexJobStatus.PAUSED_LIMIT
    assert executor.requests == []
    assert paused_job.resume.resume_after == "2026-07-07T15:00:00Z"
    assert "primary window" in paused_job.resume.last_error
    assert "model=gpt-5.5" in outcome.log_path.read_text(encoding="utf-8")
    assert "reasoning=high" in outcome.log_path.read_text(encoding="utf-8")
    assert "remaining=5%" in outcome.log_path.read_text(encoding="utf-8")
    assert "reset_at=2026-07-07T15:00:00Z" in outcome.log_path.read_text(encoding="utf-8")
    assert outcome.failed_request_path is not None
    assert outcome.paused_assignment_path is not None


def test_host_side_runner_blocks_request_when_limit_record_is_stale(tmp_path: Path) -> None:
    job_store = FileCodexJobStore(tmp_path / "jobs")
    pause_store = FileCodexPauseStore(tmp_path / "pause")
    limit_store = FileCodexLimitAvailabilityStore(tmp_path / "limits")
    job_store.create(_job(tmp_path, "job-001"))
    limit_store.write_record(
        build_codex_limit_availability_record(
            record_id="availability-20260626T123000Z",
            short_window=CodexLimitWindowAvailability(
                status=CodexLimitWindowStatus.AVAILABLE,
                remaining_percent=95,
                reset_at="2026-06-26T17:00:00Z",
                observation_source=CodexLimitObservationSource.OPERATOR,
                observed_at="2026-06-26T12:30:00Z",
            ),
            broad_quota=CodexLimitWindowAvailability(
                status=CodexLimitWindowStatus.AVAILABLE,
                remaining_percent=95,
                reset_at="2026-07-03T12:00:00Z",
                observation_source=CodexLimitObservationSource.OPERATOR,
                observed_at="2026-06-26T12:30:00Z",
            ),
        )
    )
    executor = RecordingExecutor(CodexRunnerExecution(output_text="should not run"))
    runner = HostSideCodexRunner(
        job_store=job_store,
        pause_store=pause_store,
        limit_store=limit_store,
        executor=executor,
        logs_root=tmp_path / "logs",
        now=Clock(),
        limit_stale_after_seconds=300,
    )

    outcome = runner.run_next()

    assert outcome is not None
    assert outcome.status == CodexJobStatus.PAUSED_LIMIT
    assert executor.requests == []
    assert "stale" in outcome.log_path.read_text(encoding="utf-8")


def test_host_side_runner_uses_attempt_in_paused_assignment_id(tmp_path: Path) -> None:
    job_store = FileCodexJobStore(tmp_path / "jobs")
    pause_store = FileCodexPauseStore(tmp_path / "pause")
    original = _job(tmp_path, "job-001")
    job_store.create(original)
    executor = RecordingExecutor(
        CodexRunnerExecution(
            output_text="partial",
            limit_reached=True,
            error_summary="Limit reached.",
        )
    )
    runner = HostSideCodexRunner(
        job_store=job_store,
        pause_store=pause_store,
        executor=executor,
        logs_root=tmp_path / "logs",
        now=Clock(),
    )

    runner.run_next()
    resumed = job_store.read("job-001")
    job_store.write(
        CodexJobArtifact(
            **{
                **resumed.__dict__,
                "status": CodexJobStatus.QUEUED,
                "failed_request_path": "",
            }
        )
    )
    runner.run_next()

    assert {artifact.id for artifact in pause_store.list_paused_assignments()} == {
        "paused-job-001-attempt-1",
        "paused-job-001-attempt-2",
    }


def test_host_side_runner_marks_job_failed_and_records_failed_request(tmp_path: Path) -> None:
    job_store = FileCodexJobStore(tmp_path / "jobs")
    pause_store = FileCodexPauseStore(tmp_path / "pause")
    job_store.create(_job(tmp_path, "job-001"))
    executor = RecordingExecutor(
        CodexRunnerExecution(
            output_text="partial",
            log_text="failure log",
            failed=True,
            error_summary="Executor crashed.",
        )
    )
    runner = HostSideCodexRunner(
        job_store=job_store,
        pause_store=pause_store,
        executor=executor,
        logs_root=tmp_path / "logs",
        now=Clock(),
    )

    outcome = runner.run_next()
    failed_job = job_store.read("job-001")
    failed_requests = pause_store.list_failed_requests()

    assert outcome is not None
    assert outcome.status == CodexJobStatus.FAILED
    assert failed_job.status == CodexJobStatus.FAILED
    assert failed_job.failed_request_path
    assert failed_requests[0].error_summary == "Executor crashed."
    assert failed_requests[0].stage_id == "host_side_runner.execution_failure"
    assert failed_requests[0].retry_policy == "manual_review_before_retry"
    assert failed_requests[0].suggested_next_role_action == "developer_manual_recovery"


def test_host_side_runner_returns_none_when_no_pending_jobs(tmp_path: Path) -> None:
    runner = HostSideCodexRunner(
        job_store=FileCodexJobStore(tmp_path / "jobs"),
        pause_store=FileCodexPauseStore(tmp_path / "pause"),
        executor=RecordingExecutor(CodexRunnerExecution()),
        logs_root=tmp_path / "logs",
        now=Clock(),
    )

    assert runner.run_next() is None


def test_host_side_runner_uses_scoped_chronological_limit_selector(tmp_path: Path) -> None:
    job_store = FileCodexJobStore(tmp_path / "jobs")
    pause_store = FileCodexPauseStore(tmp_path / "pause")
    limit_store = FileCodexLimitAvailabilityStore(tmp_path / "limits")
    job_store.create(_job(tmp_path, "job-001"))

    def record(record_id: str, observed_at: str, remaining_percent: int):
        window = CodexLimitWindowAvailability(
            status=CodexLimitWindowStatus.AVAILABLE,
            remaining_percent=remaining_percent,
            reset_at="2026-06-26T17:00:00Z",
            observation_source=CodexLimitObservationSource.OPERATOR,
            observed_at=observed_at,
            bucket_id="codex",
        )
        return build_codex_limit_availability_record(
            record_id=record_id,
            short_window=window,
            broad_quota=window,
            account_scope_id="chatgpt-primary",
        )

    limit_store.write_record(record("z-older", "2026-06-26T12:38:00Z", 80))
    limit_store.write_record(record("a-newer", "2026-06-26T12:39:00Z", 5))
    executor = RecordingExecutor(CodexRunnerExecution(output_text="should not run"))
    runner = HostSideCodexRunner(
        job_store=job_store,
        pause_store=pause_store,
        limit_store=limit_store,
        executor=executor,
        logs_root=tmp_path / "logs",
        now=Clock(),
        limit_account_scope_id="chatgpt-primary",
        limit_bucket_id="codex",
    )

    outcome = runner.run_next()

    assert outcome is not None
    assert outcome.status is CodexJobStatus.PAUSED_LIMIT
    assert executor.requests == []
    assert job_store.read("job-001").resume.resume_after == "2026-06-26T17:00:00Z"


def _job(tmp_path: Path, job_id: str) -> CodexJobArtifact:
    return CodexJobArtifact(
        id=job_id,
        jira_issue_key="AGENT-43",
        role=AgentRole.DEVELOPER,
        target_repo_path="/workspace/repo",
        branch_name="feature/AGENT-43-host-side-codex-runner",
        context_pack_path="data/context-packs/AGENT-43/context-pack.md",
        output_path=str(tmp_path / "results" / f"{job_id}.json"),
        model="gpt-5.5",
        reasoning=ReasoningLevel.HIGH,
        speed="normal",
        effort_mode=CodexEffortMode.COMPLEX,
        status=CodexJobStatus.QUEUED,
        created_at="2026-06-26T12:30:00Z",
        updated_at="2026-06-26T12:30:00Z",
    )
