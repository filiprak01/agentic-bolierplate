from dataclasses import replace

import pytest

from agentic_boilerplate.domain import (
    AgentRole,
    CodexEffortMode,
    CodexJobArtifact,
    CodexJobStatus,
    ReasoningLevel,
)
from agentic_boilerplate.storage import (
    CodexJobAlreadyExistsError,
    CodexJobNotFoundError,
    FileCodexJobStore,
    InvalidCodexJobIdError,
)


def test_codex_job_store_creates_reads_and_updates_job(tmp_path) -> None:
    store = FileCodexJobStore(tmp_path)
    job = _codex_job("job-001", status=CodexJobStatus.QUEUED)

    location = store.create(job)
    restored = store.read("job-001")
    running = replace(restored, status=CodexJobStatus.RUNNING, attempt_count=1, updated_at="2026-06-26T12:31:00Z")
    updated_location = store.write(running)

    assert location.path == tmp_path / "job-001" / "job.json"
    assert updated_location.path == location.path
    assert restored == job
    assert store.read("job-001") == running


def test_codex_job_store_lists_only_pending_jobs(tmp_path) -> None:
    store = FileCodexJobStore(tmp_path)
    queued = _codex_job("queued-job", status=CodexJobStatus.QUEUED)
    running = _codex_job("running-job", status=CodexJobStatus.RUNNING)

    store.create(running)
    store.create(queued)

    assert store.list_pending() == (queued,)
    assert [job.id for job in store.list_jobs()] == ["queued-job", "running-job"]


def test_codex_job_store_rejects_duplicate_and_unsafe_ids(tmp_path) -> None:
    store = FileCodexJobStore(tmp_path)
    job = _codex_job("job-001", status=CodexJobStatus.QUEUED)

    store.create(job)

    with pytest.raises(CodexJobAlreadyExistsError):
        store.create(job)
    with pytest.raises(InvalidCodexJobIdError):
        store.read("../unsafe")
    with pytest.raises(CodexJobNotFoundError):
        store.read("missing-job")


def _codex_job(job_id: str, *, status: CodexJobStatus) -> CodexJobArtifact:
    return CodexJobArtifact(
        id=job_id,
        jira_issue_key="AGENT-43",
        role=AgentRole.DEVELOPER,
        target_repo_path="/workspace/repo",
        branch_name="feature/AGENT-43-host-side-codex-runner",
        context_pack_path="data/context-packs/AGENT-43/context-pack.md",
        output_path="data/codex-results/AGENT-43/result.json",
        model="gpt-5.5",
        reasoning=ReasoningLevel.HIGH,
        speed="normal",
        effort_mode=CodexEffortMode.COMPLEX,
        status=status,
        created_at="2026-06-26T12:30:00Z",
        updated_at="2026-06-26T12:30:00Z",
    )
