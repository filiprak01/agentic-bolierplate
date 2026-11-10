from pathlib import Path

import pytest

from agentic_boilerplate.domain import AgentRole
from agentic_boilerplate.domain.detached_worker_checkpoint import (
    DetachedWorkerCheckpoint,
    DetachedWorkerCheckpointError,
    DetachedWorkerCheckpointStage,
    DetachedWorkerResumeAction,
    detached_worker_checkpoint_from_dict,
    detached_worker_checkpoint_to_dict,
    require_valid_detached_worker_checkpoint,
)
from agentic_boilerplate.storage import (
    DETACHED_WORKER_CHECKPOINT_FOLDER,
    DetachedWorkerCheckpointAlreadyExistsError,
    DetachedWorkerCheckpointNotFoundError,
    FileDetachedWorkerCheckpointStore,
    InvalidDetachedWorkerCheckpointIdError,
)


def test_checkpoint_round_trips_through_json_compatible_data() -> None:
    checkpoint = _checkpoint()

    restored = detached_worker_checkpoint_from_dict(detached_worker_checkpoint_to_dict(checkpoint))

    assert restored == checkpoint
    assert restored.project_id == "agentic-boilerplate"
    assert restored.repository == "example-org/agentic-boilerplate"


def test_legacy_checkpoint_records_without_extended_project_identity_still_load() -> None:
    data = detached_worker_checkpoint_to_dict(_checkpoint())
    for key in ("project_name", "project_root", "repository", "jira_project_key"):
        data.pop(key)

    restored = detached_worker_checkpoint_from_dict(data)

    assert restored.project_id == "agentic-boilerplate"
    assert restored.project_name == ""
    assert restored.project_root == ""
    assert restored.repository == ""
    assert restored.jira_project_key == ""


def test_paused_limit_checkpoint_requires_failed_request_and_resume_after() -> None:
    checkpoint = DetachedWorkerCheckpoint(
        **{
            **_checkpoint().__dict__,
            "stage": DetachedWorkerCheckpointStage.PAUSED_LIMIT,
            "resume_action": DetachedWorkerResumeAction.WAIT_FOR_LIMITS,
            "failed_request_path": "",
            "resume_after": "",
        }
    )

    with pytest.raises(DetachedWorkerCheckpointError) as error:
        require_valid_detached_worker_checkpoint(checkpoint)

    assert "failed_request_path" in str(error.value)
    assert "resume_after" in str(error.value)
    assert "docker run" not in str(error.value)


def test_store_persists_checkpoint_across_store_reinstantiation(tmp_path: Path) -> None:
    store = FileDetachedWorkerCheckpointStore(tmp_path)
    checkpoint = _checkpoint()

    location = store.create(checkpoint)
    restarted_store = FileDetachedWorkerCheckpointStore(tmp_path)

    assert location.path == tmp_path / DETACHED_WORKER_CHECKPOINT_FOLDER / "checkpoint-AGENT-622-001.json"
    assert restarted_store.read(checkpoint.id) == checkpoint
    assert restarted_store.list_for_assignment("assignment-AGENT-622") == (checkpoint,)


def test_store_redacts_secret_like_checkpoint_text_before_persistence(tmp_path: Path) -> None:
    store = FileDetachedWorkerCheckpointStore(tmp_path)
    checkpoint = DetachedWorkerCheckpoint(
        **{
            **_checkpoint().__dict__,
            "last_command": "curl -H 'Authorization: Bearer live-token' https://example.test",
            "resume_recommendation": "retry with api_token=abc123 and secret=hidden",
        }
    )

    location = store.create(checkpoint)
    restored = store.read(checkpoint.id)
    raw_content = location.path.read_text(encoding="utf-8")

    assert "live-token" not in raw_content
    assert "abc123" not in raw_content
    assert "hidden" not in raw_content
    assert "Authorization: Bearer ***REDACTED***" in restored.last_command
    assert "api_token=***REDACTED***" in restored.resume_recommendation
    assert "secret=***REDACTED***" in restored.resume_recommendation
    assert set(restored.redacted_fields) == {
        "last_command.authorization",
        "resume_recommendation.api_token",
        "resume_recommendation.password",
    }


def test_store_redacts_standalone_github_tokens_before_persistence(tmp_path: Path) -> None:
    store = FileDetachedWorkerCheckpointStore(tmp_path)
    checkpoint = DetachedWorkerCheckpoint(
        **{
            **_checkpoint().__dict__,
            "last_command": "configure remote with " + "github_" + "pat_exampleTokenValue12345",
            "resume_recommendation": "retry push after replacing " + "gh" + "p_exampleTokenValue12345",
        }
    )

    location = store.create(checkpoint)
    restored = store.read(checkpoint.id)
    raw_content = location.path.read_text(encoding="utf-8")

    assert "exampleTokenValue12345" not in raw_content
    assert restored.last_command == "configure remote with ***REDACTED***"
    assert restored.resume_recommendation == "retry push after replacing ***REDACTED***"
    assert set(restored.redacted_fields) == {
        "last_command.github_pat",
        "resume_recommendation.github_classic_token",
    }


def test_store_rejects_duplicate_missing_and_invalid_checkpoint_ids(tmp_path: Path) -> None:
    store = FileDetachedWorkerCheckpointStore(tmp_path)
    checkpoint = _checkpoint()
    store.create(checkpoint)

    with pytest.raises(DetachedWorkerCheckpointAlreadyExistsError):
        store.create(checkpoint)
    with pytest.raises(DetachedWorkerCheckpointNotFoundError):
        store.read("missing")
    with pytest.raises(InvalidDetachedWorkerCheckpointIdError):
        store.checkpoint_path("../escape")


def test_invalid_checkpoint_schema_file_is_rejected_on_read(tmp_path: Path) -> None:
    store = FileDetachedWorkerCheckpointStore(tmp_path)
    store.ensure_directories()
    (tmp_path / DETACHED_WORKER_CHECKPOINT_FOLDER / "bad.json").write_text('{"id":"bad"}', encoding="utf-8")

    with pytest.raises(DetachedWorkerCheckpointError):
        store.read("bad")


def _checkpoint() -> DetachedWorkerCheckpoint:
    return DetachedWorkerCheckpoint(
        id="checkpoint-AGENT-622-001",
        assignment_id="assignment-AGENT-622",
        worker_id="data-persistence-worker-1",
        role=AgentRole.DATA_PERSISTENCE,
        project_id="agentic-boilerplate",
        project_name="Agentic Boilerplate",
        project_root="/home/user/business/agentic-bolierplate",
        repository="example-org/agentic-boilerplate",
        jira_project_key="AGENT",
        sprint="R1.2 S1 Foundation",
        jira_issue_key="AGENT-622",
        branch_name="feature/AGENT-622-detached-worker-checkpoint-schema",
        worktree_path="/workspace/project",
        stage=DetachedWorkerCheckpointStage.WORKSPACE_READY,
        last_command="docker run worker --assignment assignment-AGENT-622",
        resume_action=DetachedWorkerResumeAction.RECHECK_GATES,
        resume_recommendation="Re-check gates and continue in the same workspace.",
        created_at="2026-08-09T18:30:00Z",
        updated_at="2026-08-09T18:31:00Z",
        attempt_count=1,
        codex_job_id="codex-job-AGENT-622",
        context_pack_path="data/context-packs/AGENT-622/context.json",
        output_path="data/codex-results/AGENT-622/result.json",
        evidence_path="data/agent-logs/AGENT-622/test-evidence.md",
    )
