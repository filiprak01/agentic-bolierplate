import json
from pathlib import Path

from agentic_boilerplate.cli import main
from agentic_boilerplate.domain import (
    AgentRole,
    CodexEffortMode,
    CodexJobArtifact,
    CodexJobStatus,
    CodexLimitObservationSource,
    CodexLimitWindowAvailability,
    CodexLimitWindowStatus,
    CodexResumeMetadata,
    ReasoningLevel,
    build_codex_limit_availability_record,
)
from agentic_boilerplate.storage import FileCodexJobStore, FileCodexLimitAvailabilityStore


def test_worker_resume_paused_cli_requeues_jobs_when_limit_allows(tmp_path: Path, capsys) -> None:
    jobs_root = tmp_path / "jobs"
    limits_root = tmp_path / "limits"
    FileCodexJobStore(jobs_root).write(_paused_job(tmp_path, "job-001"))
    FileCodexLimitAvailabilityStore(limits_root).write_record(_limit_record(remaining_percent=95))

    result = main(
        [
            "--env-file",
            str(tmp_path / "missing.env"),
            "worker",
            "resume-paused",
            "--codex-jobs-root",
            str(jobs_root),
            "--limit-store-root",
            str(limits_root),
            "--resumed-at",
            "2026-06-26T13:00:00Z",
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert result == 0
    assert payload["gate"]["allowed"] is True
    assert payload["resumed_job_ids"] == ["job-001"]
    assert FileCodexJobStore(jobs_root).read("job-001").status == CodexJobStatus.QUEUED


def test_worker_resume_paused_cli_returns_wait_when_limit_is_closed(tmp_path: Path, capsys) -> None:
    jobs_root = tmp_path / "jobs"
    limits_root = tmp_path / "limits"
    FileCodexJobStore(jobs_root).write(_paused_job(tmp_path, "job-001"))
    FileCodexLimitAvailabilityStore(limits_root).write_record(_limit_record(remaining_percent=5))

    result = main(
        [
            "--env-file",
            str(tmp_path / "missing.env"),
            "worker",
            "resume-paused",
            "--codex-jobs-root",
            str(jobs_root),
            "--limit-store-root",
            str(limits_root),
            "--resumed-at",
            "2026-06-26T13:00:00Z",
        ]
    )

    output = capsys.readouterr().out

    assert result == 2
    assert "allowed=False" in output
    assert "resumed=0" in output
    assert "next_check_at=2026-06-26T17:00:00Z" in output


def _paused_job(tmp_path: Path, job_id: str) -> CodexJobArtifact:
    return CodexJobArtifact(
        id=job_id,
        jira_issue_key="AGENT-627",
        role=AgentRole.DEVELOPER,
        target_repo_path="/workspace/repo",
        branch_name="feature/AGENT-627-limit-auto-wait-resume",
        context_pack_path="data/context-packs/AGENT-627/context-pack.md",
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


def _limit_record(*, remaining_percent: int):
    return build_codex_limit_availability_record(
        record_id=f"availability-{remaining_percent}",
        short_window=CodexLimitWindowAvailability(
            status=CodexLimitWindowStatus.AVAILABLE,
            remaining_percent=remaining_percent,
            reset_at="2026-06-26T17:00:00Z",
            observation_source=CodexLimitObservationSource.OPERATOR,
            observed_at="2026-06-26T12:40:00Z",
        ),
        broad_quota=CodexLimitWindowAvailability(
            status=CodexLimitWindowStatus.AVAILABLE,
            remaining_percent=80,
            reset_at="2026-07-03T12:00:00Z",
            observation_source=CodexLimitObservationSource.OPERATOR,
            observed_at="2026-06-26T12:40:00Z",
        ),
    )
