from pathlib import Path

from agentic_boilerplate.domain import (
    AgentRole,
    CodexEffortMode,
    CodexJobArtifact,
    CodexJobStatus,
    CodexLimitObservationSource,
    CodexLimitRecommendedAction,
    CodexLimitWindowAvailability,
    CodexLimitWindowStatus,
    CodexResumeMetadata,
    ReasoningLevel,
    build_codex_limit_availability_record,
)
from agentic_boilerplate.runtime import codex_resume_scheduler_result_to_dict, resume_paused_limit_jobs
from agentic_boilerplate.storage import FileCodexJobStore, FileCodexLimitAvailabilityStore


def test_resume_scheduler_requeues_paused_job_when_limit_gate_allows_work(tmp_path: Path) -> None:
    job_store = FileCodexJobStore(tmp_path / "jobs")
    limit_store = FileCodexLimitAvailabilityStore(tmp_path / "limits")
    job_store.write(_paused_job(tmp_path, "job-001"))
    limit_store.write_record(_available_limit_record())

    result = resume_paused_limit_jobs(
        job_store=job_store,
        limit_store=limit_store,
        resumed_at="2026-06-26T13:00:00Z",
    )

    restored = job_store.read("job-001")

    assert result.gate.allowed is True
    assert result.resumed_job_ids == ("job-001",)
    assert restored.status == CodexJobStatus.QUEUED
    assert restored.resume.last_checkpoint_path == str(tmp_path / "results" / "job-001.json")
    assert restored.resume.resume_after == ""
    assert restored.updated_at == "2026-06-26T13:00:00Z"


def test_resume_scheduler_keeps_paused_job_when_limit_gate_is_closed(tmp_path: Path) -> None:
    job_store = FileCodexJobStore(tmp_path / "jobs")
    limit_store = FileCodexLimitAvailabilityStore(tmp_path / "limits")
    job_store.write(_paused_job(tmp_path, "job-001"))
    limit_store.write_record(_low_limit_record())

    result = resume_paused_limit_jobs(
        job_store=job_store,
        limit_store=limit_store,
        resumed_at="2026-06-26T13:00:00Z",
    )

    assert result.gate.allowed is False
    assert result.gate.action == CodexLimitRecommendedAction.WAIT
    assert result.skipped_job_ids == ("job-001",)
    assert result.next_check_at == "2026-06-26T17:00:00Z"
    assert job_store.read("job-001").status == CodexJobStatus.PAUSED_LIMIT


def test_resume_scheduler_uses_scoped_chronological_limit_selector(tmp_path: Path) -> None:
    job_store = FileCodexJobStore(tmp_path / "jobs")
    limit_store = FileCodexLimitAvailabilityStore(tmp_path / "limits")
    job_store.write(_paused_job(tmp_path, "job-001"))

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

    limit_store.write_record(record("z-older", "2026-06-26T12:40:00Z", 80))
    limit_store.write_record(record("a-newer", "2026-06-26T12:50:00Z", 5))

    result = resume_paused_limit_jobs(
        job_store=job_store,
        limit_store=limit_store,
        resumed_at="2026-06-26T13:00:00Z",
        account_scope_id="chatgpt-primary",
        bucket_id="codex",
    )

    assert result.gate.allowed is False
    assert result.gate.action is CodexLimitRecommendedAction.WAIT
    assert result.resumed_job_ids == ()
    assert job_store.read("job-001").status is CodexJobStatus.PAUSED_LIMIT


def test_resume_scheduler_skips_jobs_that_are_not_dependency_eligible(tmp_path: Path) -> None:
    job_store = FileCodexJobStore(tmp_path / "jobs")
    limit_store = FileCodexLimitAvailabilityStore(tmp_path / "limits")
    job_store.write(_paused_job(tmp_path, "job-001", jira_issue_key="AGENT-627"))
    limit_store.write_record(_available_limit_record())

    result = resume_paused_limit_jobs(
        job_store=job_store,
        limit_store=limit_store,
        resumed_at="2026-06-26T13:00:00Z",
        eligible_issue_keys=("AGENT-999",),
    )

    assert result.resumed_job_ids == ()
    assert result.skipped_job_ids == ("job-001",)
    assert job_store.read("job-001").status == CodexJobStatus.PAUSED_LIMIT


def test_resume_scheduler_result_is_cli_consumable(tmp_path: Path) -> None:
    job_store = FileCodexJobStore(tmp_path / "jobs")
    limit_store = FileCodexLimitAvailabilityStore(tmp_path / "limits")
    job_store.write(_paused_job(tmp_path, "job-001"))
    limit_store.write_record(_available_limit_record())

    result = resume_paused_limit_jobs(
        job_store=job_store,
        limit_store=limit_store,
        resumed_at="2026-06-26T13:00:00Z",
    )

    payload = codex_resume_scheduler_result_to_dict(result)

    assert payload["gate"]["allowed"] is True
    assert payload["resumed_job_ids"] == ["job-001"]


def _paused_job(tmp_path: Path, job_id: str, *, jira_issue_key: str = "AGENT-627") -> CodexJobArtifact:
    return CodexJobArtifact(
        id=job_id,
        jira_issue_key=jira_issue_key,
        role=AgentRole.DEVELOPER,
        target_repo_path="/workspace/repo",
        branch_name=f"feature/{jira_issue_key}-limit-resume",
        context_pack_path=f"data/context-packs/{jira_issue_key}/context-pack.md",
        output_path=str(tmp_path / "results" / f"{job_id}.json"),
        model="gpt-5.4",
        reasoning=ReasoningLevel.HIGH,
        speed="normal",
        effort_mode=CodexEffortMode.COMPLEX,
        status=CodexJobStatus.PAUSED_LIMIT,
        created_at="2026-06-26T12:30:00Z",
        updated_at="2026-06-26T12:41:00Z",
        attempt_count=1,
        failed_request_path=str(tmp_path / "pause" / "failed-request.json"),
        resume=CodexResumeMetadata(
            resumable=True,
            resume_after="2026-06-26T17:00:00Z",
            last_checkpoint_path=str(tmp_path / "results" / f"{job_id}.json"),
            last_error="Codex limit reached.",
            paused_at="2026-06-26T12:41:00Z",
        ),
    )


def _available_limit_record():
    return build_codex_limit_availability_record(
        record_id="availability-20260626T130000Z",
        short_window=_window(
            status=CodexLimitWindowStatus.AVAILABLE,
            remaining_percent=95,
            reset_at="2026-06-26T17:00:00Z",
        ),
        broad_quota=_window(
            status=CodexLimitWindowStatus.AVAILABLE,
            remaining_percent=80,
            reset_at="2026-07-03T12:00:00Z",
        ),
    )


def _low_limit_record():
    return build_codex_limit_availability_record(
        record_id="availability-20260626T124000Z",
        short_window=_window(
            status=CodexLimitWindowStatus.AVAILABLE,
            remaining_percent=5,
            reset_at="2026-06-26T17:00:00Z",
        ),
        broad_quota=_window(
            status=CodexLimitWindowStatus.AVAILABLE,
            remaining_percent=80,
            reset_at="2026-07-03T12:00:00Z",
        ),
    )


def _window(
    *,
    status: CodexLimitWindowStatus,
    remaining_percent: int,
    reset_at: str,
) -> CodexLimitWindowAvailability:
    return CodexLimitWindowAvailability(
        status=status,
        remaining_percent=remaining_percent,
        reset_at=reset_at,
        observation_source=CodexLimitObservationSource.OPERATOR,
        observed_at="2026-06-26T12:40:00Z",
    )
