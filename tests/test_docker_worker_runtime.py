import base64
import json
from pathlib import Path

from agentic_boilerplate.config import settings_from_mapping
from agentic_boilerplate.domain import (
    AgentRole,
    AssignmentLockStatus,
    CodexJobStatus,
    CodexLimitObservationSource,
    CodexLimitRecommendedAction,
    CodexLimitWindowAvailability,
    CodexLimitWindowStatus,
    acquire_assignment_lock,
    build_codex_limit_availability_record,
)
from agentic_boilerplate.domain.agent_assignment import AgentAssignment, AssignmentPaths, AssignmentStatus, WorkerStatus
from agentic_boilerplate.domain.detached_worker_checkpoint import (
    DetachedWorkerCheckpointStage,
    DetachedWorkerResumeAction,
)
from agentic_boilerplate.runtime import docker_worker_run_result_to_dict, run_docker_worker_once
from agentic_boilerplate.storage import (
    FileAgentAssignmentStore,
    FileAssignmentLockStore,
    FileCodexJobStore,
    FileCodexLimitAvailabilityStore,
    FileDetachedWorkerCheckpointStore,
)


def test_docker_worker_registers_and_reports_no_assignment(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    result = run_docker_worker_once(
        settings,
        role=AgentRole.DEVELOPER,
        worker_id="developer-1",
        container_name="agentic-worker-developer",
        now=lambda: "2026-07-07T10:00:00Z",
    )

    store = FileAgentAssignmentStore(tmp_path / "agent-state")
    worker = store.read_worker("developer-1")
    registry = store.read_registry("docker-workers")
    output = docker_worker_run_result_to_dict(result)

    assert result.startup_passed is True
    assert result.worker_status is WorkerStatus.AVAILABLE
    assert result.assignment_id == ""
    assert worker.role is AgentRole.DEVELOPER
    assert worker.container_name == "agentic-worker-developer"
    assert registry.workers == (worker,)
    assert result.log_path == tmp_path / "agent-logs" / "developer" / "developer-1.log"
    assert "secret" not in result.log_path.read_text(encoding="utf-8")
    assert "instructions.role" in result.log_path.read_text(encoding="utf-8")
    assert output["role"] == "developer"
    assert output["instruction_gate_allowed"] is True


def test_docker_worker_prepares_git_ssh_runtime_without_leaking_key(tmp_path: Path, monkeypatch) -> None:
    settings = settings_from_mapping(
        {
            **_base_env(tmp_path),
            "GITHUB_AUTH_MODE": "ssh",
            "GIT_REMOTE_MODE": "ssh",
            "GITHUB_REPOSITORY": "ExampleOrg/example-repo",
            "GITHUB_SSH_PRIVATE_KEY_B64": base64.b64encode(
                b"-----BEGIN" b" OPENSSH PRIVATE KEY-----\nsecret-value\n-----END OPENSSH PRIVATE KEY-----\n"
            ).decode(),
        }
    )
    ssh_dir = tmp_path / "ephemeral-ssh"
    monkeypatch.setenv("AGENTIC_GIT_SSH_DIR", str(ssh_dir))

    result = run_docker_worker_once(
        settings,
        role=AgentRole.DEVELOPER,
        worker_id="developer-ssh",
        container_name="agentic-worker-developer",
        now=lambda: "2026-07-07T10:00:00Z",
    )
    output = docker_worker_run_result_to_dict(result)
    log_payload = json.loads(result.log_path.read_text(encoding="utf-8"))

    assert result.git_ssh_enabled is True
    assert result.git_ssh_key_source == "private_key_b64"
    assert output["git_ssh_enabled"] is True
    assert output["git_ssh_key_source"] == "private_key_b64"
    assert (ssh_dir / "id_github").is_file()
    assert "secret-value" not in json.dumps(log_payload)
    assert log_payload["git_ssh"]["key_path"] == "<redacted>"


def test_docker_worker_dry_run_observes_assignment_without_mutating_it(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = FileAgentAssignmentStore(tmp_path / "agent-state")
    _write_limit_record(tmp_path, short_remaining=80, broad_remaining=80)
    _write_context_pack(tmp_path)
    assignment = _assignment()
    store.create_assignment(assignment)

    result = run_docker_worker_once(
        settings,
        role="developer",
        worker_id="developer-1",
        dry_run=True,
        now=lambda: "2026-07-07T10:00:00Z",
    )

    restored = store.read_assignment("assignment-AGENT-404")
    worker = store.read_worker("developer-1")
    log_text = result.log_path.read_text(encoding="utf-8")

    assert result.assignment_id == "assignment-AGENT-404"
    assert result.assignment_status is AssignmentStatus.QUEUED
    assert result.worker_status is WorkerStatus.PAUSED
    assert result.limit_gate_allowed is True
    assert result.instruction_gate_allowed is True
    assert result.workspace_gate_allowed is True
    assert result.workspace_path == str(tmp_path / "agent-workspaces" / "AGENT" / "AGENT-404" / "developer")
    assert worker.current_assignment_id == "assignment-AGENT-404"
    assert restored == assignment
    assert "left unchanged" in result.message
    assert "assignment-AGENT-404" in log_text
    assert result.checkpoint_path == (
        tmp_path
        / "agent-state"
        / "detached-worker-checkpoints"
        / "checkpoint-assignment-AGENT-404-limit_checked.json"
    )
    assert result.evidence_path == (
        tmp_path / "agent-logs" / "developer" / "assignment-AGENT-404" / "worker-run-evidence.json"
    )
    checkpoint = FileDetachedWorkerCheckpointStore(tmp_path / "agent-state").read(
        "checkpoint-assignment-AGENT-404-limit_checked"
    )
    evidence = json.loads(result.evidence_path.read_text(encoding="utf-8"))
    assert checkpoint.stage is DetachedWorkerCheckpointStage.LIMIT_CHECKED
    assert checkpoint.resume_action is DetachedWorkerResumeAction.RECHECK_GATES
    assert checkpoint.evidence_path == str(result.evidence_path)
    assert evidence["evidence_type"] == "bounded_worker_assignment"
    assert evidence["assignment_status"] == "queued"
    assert evidence["workspace_gate_allowed"] is True
    assert evidence["workspace_path"] == str(tmp_path / "agent-workspaces" / "AGENT" / "AGENT-404" / "developer")


def test_docker_worker_uses_scoped_chronological_limit_selector(tmp_path: Path) -> None:
    settings = settings_from_mapping(
        {
            **_base_env(tmp_path),
            "CODEX_LIMIT_ACCOUNT_SCOPE_ID": "chatgpt-primary",
            "CODEX_LIMIT_BUCKET_ID": "codex",
        }
    )
    store = FileAgentAssignmentStore(tmp_path / "agent-state")
    _write_context_pack(tmp_path)
    store.create_assignment(_assignment())
    _write_limit_record(
        tmp_path,
        short_remaining=80,
        broad_remaining=80,
        record_id="z-older",
        observed_at="2026-07-07T09:58:00Z",
        account_scope_id="chatgpt-primary",
        bucket_id="codex",
    )
    _write_limit_record(
        tmp_path,
        short_remaining=5,
        broad_remaining=80,
        record_id="a-newer",
        observed_at="2026-07-07T09:59:00Z",
        account_scope_id="chatgpt-primary",
        bucket_id="codex",
    )

    result = run_docker_worker_once(
        settings,
        role="developer",
        worker_id="developer-1",
        dry_run=True,
        now=lambda: "2026-07-07T10:00:00Z",
    )

    assert result.limit_gate_allowed is False
    assert result.limit_action is CodexLimitRecommendedAction.WAIT
    assert result.assignment_status is AssignmentStatus.QUEUED


def test_docker_worker_live_mode_creates_host_side_codex_job(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = FileAgentAssignmentStore(tmp_path / "agent-state")
    _write_limit_record(tmp_path, short_remaining=80, broad_remaining=80)
    _write_context_pack(tmp_path)
    assignment = _assignment()
    store.create_assignment(assignment)

    result = run_docker_worker_once(
        settings,
        role="developer",
        worker_id="developer-1",
        dry_run=False,
        now=lambda: "2026-07-07T10:00:00Z",
    )

    restored = store.read_assignment("assignment-AGENT-404")
    worker = store.read_worker("developer-1")
    job = FileCodexJobStore(tmp_path / "codex-jobs").read("AGENT-404")
    lock = FileAssignmentLockStore(tmp_path / "agent-state").active_lock_for("AGENT-404", AgentRole.DEVELOPER)
    log_text = result.log_path.read_text(encoding="utf-8")

    assert result.assignment_id == "assignment-AGENT-404"
    assert result.assignment_status is AssignmentStatus.ASSIGNED
    assert result.worker_status is WorkerStatus.ASSIGNED
    assert result.dry_run is False
    assert restored.status is AssignmentStatus.ASSIGNED
    assert restored.worker_id == "developer-1"
    assert restored.codex_job_id == "AGENT-404"
    assert worker.current_assignment_id == "assignment-AGENT-404"
    assert lock is not None
    assert lock.worker_session_id == "developer-1"
    assert lock.status is AssignmentLockStatus.ACTIVE
    assert lock.workspace_path == str(tmp_path / "agent-workspaces" / "AGENT" / "AGENT-404" / "developer")
    assert lock.expires_at == "2026-07-07T14:00:00Z"
    assert result.assignment_lock_allowed is True
    assert result.assignment_lock_path == (
        tmp_path / "agent-state" / "assignment-locks" / "AGENT-404__developer__developer-1.json"
    )
    assert job.status is CodexJobStatus.QUEUED
    assert job.target_repo_path == str(tmp_path / "agent-workspaces" / "AGENT" / "AGENT-404" / "developer")
    assert "Host-side Codex execution request created" in result.message
    assert "session secrets" in log_text
    assert result.codex_job_path == tmp_path / "codex-jobs" / "AGENT-404" / "job.json"
    assert result.evidence_path == (
        tmp_path / "agent-logs" / "developer" / "assignment-AGENT-404" / "worker-run-evidence.json"
    )
    checkpoint = FileDetachedWorkerCheckpointStore(tmp_path / "agent-state").read(
        "checkpoint-assignment-AGENT-404-codex_job_created"
    )
    evidence = json.loads(result.evidence_path.read_text(encoding="utf-8"))
    assert checkpoint.stage is DetachedWorkerCheckpointStage.CODEX_JOB_CREATED
    assert checkpoint.resume_action is DetachedWorkerResumeAction.NONE
    assert checkpoint.codex_job_id == "AGENT-404"
    assert evidence["codex_job_path"] == str(result.codex_job_path)
    assert evidence["assignment_lock_path"] == str(result.assignment_lock_path)
    assert evidence["workspace_gate_allowed"] is True
    assert evidence["workspace_path"] == str(tmp_path / "agent-workspaces" / "AGENT" / "AGENT-404" / "developer")


def test_docker_worker_blocks_assignment_when_workspace_gate_fails(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = FileAgentAssignmentStore(tmp_path / "agent-state")
    _write_limit_record(tmp_path, short_remaining=80, broad_remaining=80)
    _write_context_pack(tmp_path)
    assignment = AgentAssignment(
        **{
            **_assignment().__dict__,
            "branch_name": "feature/AGENT-999-wrong-branch",
        }
    )
    store.create_assignment(assignment)

    result = run_docker_worker_once(
        settings,
        role="developer",
        worker_id="developer-1",
        dry_run=False,
        now=lambda: "2026-07-07T10:00:00Z",
    )

    restored = store.read_assignment("assignment-AGENT-404")
    worker = store.read_worker("developer-1")
    evidence = json.loads(result.evidence_path.read_text(encoding="utf-8"))
    checkpoint = FileDetachedWorkerCheckpointStore(tmp_path / "agent-state").read(
        "checkpoint-assignment-AGENT-404-workspace_ready"
    )

    assert result.worker_status is WorkerStatus.PAUSED
    assert result.assignment_status is AssignmentStatus.QUEUED
    assert result.workspace_gate_allowed is False
    assert "branch-issue-mismatch" in result.workspace_gate_reason
    assert restored == assignment
    assert worker.current_assignment_id == ""
    assert "workspace provisioning gate" in result.message
    assert evidence["workspace_gate_allowed"] is False
    assert "branch-issue-mismatch" in evidence["workspace_gate_reason"]
    assert checkpoint.stage is DetachedWorkerCheckpointStage.WORKSPACE_READY
    assert checkpoint.resume_action is DetachedWorkerResumeAction.RECHECK_GATES


def test_docker_worker_blocks_live_claim_when_assignment_lock_is_active(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = FileAgentAssignmentStore(tmp_path / "agent-state")
    lock_store = FileAssignmentLockStore(tmp_path / "agent-state")
    _write_limit_record(tmp_path, short_remaining=80, broad_remaining=80)
    _write_context_pack(tmp_path)
    assignment = _assignment()
    store.create_assignment(assignment)
    lock_store.create_lock(
        acquire_assignment_lock(
            jira_issue_key="AGENT-404",
            role=AgentRole.DEVELOPER,
            worker_session_id="developer-2",
            acquired_at="2026-07-07T09:30:00Z",
            dependency_gate_passed=True,
            workspace_path=str(tmp_path / "other-workspace"),
            expires_at="2026-07-07T13:30:00Z",
        )
    )

    result = run_docker_worker_once(
        settings,
        role="developer",
        worker_id="developer-1",
        dry_run=False,
        now=lambda: "2026-07-07T10:00:00Z",
    )

    restored = store.read_assignment("assignment-AGENT-404")
    worker = store.read_worker("developer-1")
    evidence = json.loads(result.evidence_path.read_text(encoding="utf-8"))
    checkpoint = FileDetachedWorkerCheckpointStore(tmp_path / "agent-state").read(
        "checkpoint-assignment-AGENT-404-assignment_claimed"
    )

    assert result.worker_status is WorkerStatus.PAUSED
    assert result.assignment_status is AssignmentStatus.QUEUED
    assert result.assignment_lock_allowed is False
    assert "developer-2" in result.assignment_lock_reason
    assert result.assignment_lock_path is None
    assert restored == assignment
    assert worker.current_assignment_id == ""
    assert "blocked by assignment lock" in result.message
    assert evidence["assignment_lock_allowed"] is False
    assert "developer-2" in evidence["assignment_lock_reason"]
    assert checkpoint.stage is DetachedWorkerCheckpointStage.ASSIGNMENT_CLAIMED
    assert checkpoint.resume_action is DetachedWorkerResumeAction.RECHECK_GATES


def test_docker_worker_blocks_assignment_when_context_pack_is_missing(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = FileAgentAssignmentStore(tmp_path / "agent-state")
    _write_limit_record(tmp_path, short_remaining=80, broad_remaining=80)
    assignment = _assignment()
    store.create_assignment(assignment)

    result = run_docker_worker_once(
        settings,
        role="developer",
        worker_id="developer-1",
        dry_run=True,
        now=lambda: "2026-07-07T10:00:00Z",
    )

    restored = store.read_assignment("assignment-AGENT-404")
    worker = store.read_worker("developer-1")
    log_text = result.log_path.read_text(encoding="utf-8")
    output = docker_worker_run_result_to_dict(result)

    assert result.assignment_id == "assignment-AGENT-404"
    assert result.assignment_status is AssignmentStatus.QUEUED
    assert result.worker_status is WorkerStatus.PAUSED
    assert result.instruction_gate_allowed is False
    assert "assignment.context_pack" in result.instruction_gate_reason
    assert worker.current_assignment_id == ""
    assert restored == assignment
    assert output["instruction_gate_allowed"] is False
    assert "assignment.context_pack" in log_text
    checkpoint = FileDetachedWorkerCheckpointStore(tmp_path / "agent-state").read(
        "checkpoint-assignment-AGENT-404-context_loaded"
    )
    assert checkpoint.stage is DetachedWorkerCheckpointStage.CONTEXT_LOADED
    assert checkpoint.resume_action is DetachedWorkerResumeAction.REBUILD_CONTEXT
    assert result.evidence_path is not None


def test_docker_worker_blocks_assignment_when_limit_record_is_missing(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = FileAgentAssignmentStore(tmp_path / "agent-state")
    _write_context_pack(tmp_path)
    assignment = _assignment()
    store.create_assignment(assignment)

    result = run_docker_worker_once(
        settings,
        role="developer",
        worker_id="developer-1",
        dry_run=True,
        now=lambda: "2026-07-07T10:00:00Z",
    )

    restored = store.read_assignment("assignment-AGENT-404")
    worker = store.read_worker("developer-1")
    output = docker_worker_run_result_to_dict(result)

    assert result.assignment_id == "assignment-AGENT-404"
    assert result.assignment_status is AssignmentStatus.QUEUED
    assert result.worker_status is WorkerStatus.PAUSED
    assert result.limit_gate_allowed is False
    assert result.limit_action is CodexLimitRecommendedAction.ASK_PRODUCT_OWNER
    assert worker.current_assignment_id == ""
    assert restored == assignment
    assert output["limit_gate_allowed"] is False


def test_docker_worker_blocks_assignment_when_short_limit_is_low(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = FileAgentAssignmentStore(tmp_path / "agent-state")
    _write_limit_record(tmp_path, short_remaining=5, broad_remaining=80)
    _write_context_pack(tmp_path)
    assignment = _assignment()
    store.create_assignment(assignment)

    result = run_docker_worker_once(
        settings,
        role="developer",
        worker_id="developer-1",
        dry_run=True,
        now=lambda: "2026-07-07T10:00:00Z",
    )

    assert result.limit_gate_allowed is False
    assert result.limit_action is CodexLimitRecommendedAction.WAIT
    assert result.resume_after == "2026-07-07T15:00:00Z"
    assert "blocked by Codex limit gate" in result.message
    checkpoint = FileDetachedWorkerCheckpointStore(tmp_path / "agent-state").read(
        "checkpoint-assignment-AGENT-404-limit_checked"
    )
    assert checkpoint.resume_action is DetachedWorkerResumeAction.WAIT_FOR_LIMITS
    assert checkpoint.resume_after == "2026-07-07T15:00:00Z"


def test_docker_worker_direct_container_mode_fails_with_checkpoint_and_failed_request(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = FileAgentAssignmentStore(tmp_path / "agent-state")
    _write_limit_record(tmp_path, short_remaining=80, broad_remaining=80)
    _write_context_pack(tmp_path)
    assignment = _assignment()
    store.create_assignment(assignment)

    result = run_docker_worker_once(
        settings,
        role="developer",
        worker_id="developer-1",
        dry_run=False,
        codex_execution_mode="direct_container",
        now=lambda: "2026-07-07T10:00:00Z",
    )

    restored = store.read_assignment("assignment-AGENT-404")
    checkpoint = FileDetachedWorkerCheckpointStore(tmp_path / "agent-state").read(
        "checkpoint-assignment-AGENT-404-failed"
    )
    evidence = json.loads(result.evidence_path.read_text(encoding="utf-8"))

    assert restored.status is AssignmentStatus.FAILED
    assert result.assignment_status is AssignmentStatus.FAILED
    assert result.failed_request_path is not None
    assert checkpoint.stage is DetachedWorkerCheckpointStage.FAILED
    assert checkpoint.failed_request_path == str(result.failed_request_path)
    assert checkpoint.resume_action is DetachedWorkerResumeAction.MANUAL_RECOVERY
    assert evidence["failed_request_path"] == str(result.failed_request_path)


def test_docker_worker_pauses_when_role_is_not_enabled(tmp_path: Path) -> None:
    settings = settings_from_mapping(
        {
            **_base_env(tmp_path),
            "WORKER_ROLES": "tester",
        }
    )

    result = run_docker_worker_once(
        settings,
        role=AgentRole.DEVELOPER,
        worker_id="developer-1",
        now=lambda: "2026-07-07T10:00:00Z",
    )

    assert result.startup_passed is True
    assert result.worker_status is WorkerStatus.PAUSED
    assert result.message == "Worker role is supported but not enabled in WORKER_ROLES."


def _settings(tmp_path: Path):
    return settings_from_mapping(_base_env(tmp_path))


def _base_env(tmp_path: Path) -> dict[str, str]:
    target_project = tmp_path / "target-project"
    target_project.mkdir(exist_ok=True)
    (target_project / ".git").mkdir(exist_ok=True)
    return {
        "GITHUB_TOKEN": "github-token",
        "JIRA_EMAIL": "po@example.com",
        "JIRA_API_TOKEN": "jira-token",
        "CONFLUENCE_API_TOKEN": "confluence-token",
        "DURABLE_PO_INBOX_PATH": str(tmp_path / "po-inbox"),
        "DURABLE_CONTEXT_PACKS_PATH": str(tmp_path / "context-packs"),
        "DURABLE_CODEX_JOBS_PATH": str(tmp_path / "codex-jobs"),
        "DURABLE_CODEX_RESULTS_PATH": str(tmp_path / "codex-results"),
        "DURABLE_CODEX_LIMITS_PATH": str(tmp_path / "codex-limits"),
        "DURABLE_AGENT_STATE_PATH": str(tmp_path / "agent-state"),
        "DURABLE_AGENT_LOGS_PATH": str(tmp_path / "agent-logs"),
        "AGENTIC_WORKSPACES_ROOT": str(tmp_path / "agent-workspaces"),
        "DURABLE_PO_DECISIONS_PATH": str(tmp_path / "po-decisions"),
        "DURABLE_SPRINTS_PATH": str(tmp_path / "sprints"),
        "DURABLE_CONFLUENCE_MIRROR_PATH": str(tmp_path / "confluence-mirror"),
        "TARGET_PROJECT_PATH": str(target_project),
    }


def _assignment() -> AgentAssignment:
    return AgentAssignment(
        id="assignment-AGENT-404",
        jira_issue_key="AGENT-404",
        role=AgentRole.DEVELOPER,
        status=AssignmentStatus.QUEUED,
        paths=AssignmentPaths(
            context_pack_path="data/context-packs/AGENT-404/context.json",
            codex_job_path="data/codex-jobs/AGENT-404/job.json",
            output_path="data/codex-results/AGENT-404/result.json",
        ),
        branch_name="feature/AGENT-404-role-docker-workers",
        created_at="2026-07-07T09:55:00Z",
        updated_at="2026-07-07T09:55:00Z",
    )


def _write_context_pack(tmp_path: Path) -> Path:
    path = tmp_path / "context-packs" / "AGENT-404" / "context.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")
    return path


def _write_limit_record(
    tmp_path: Path,
    *,
    short_remaining: int,
    broad_remaining: int,
    record_id: str = "",
    observed_at: str = "2026-07-07T10:00:00Z",
    account_scope_id: str = "default",
    bucket_id: str = "",
) -> None:
    store = FileCodexLimitAvailabilityStore(tmp_path / "codex-limits")
    record = build_codex_limit_availability_record(
        record_id=record_id or f"availability-short-{short_remaining}-broad-{broad_remaining}",
        short_window=CodexLimitWindowAvailability(
            status=CodexLimitWindowStatus.AVAILABLE,
            remaining_percent=short_remaining,
            reset_at="2026-07-07T15:00:00Z",
            observation_source=CodexLimitObservationSource.OPERATOR,
            observed_at=observed_at,
            bucket_id=bucket_id,
        ),
        broad_quota=CodexLimitWindowAvailability(
            status=CodexLimitWindowStatus.AVAILABLE,
            remaining_percent=broad_remaining,
            reset_at="2026-07-14T10:00:00Z",
            observation_source=CodexLimitObservationSource.OPERATOR,
            observed_at=observed_at,
            bucket_id=bucket_id,
        ),
        account_scope_id=account_scope_id,
    )
    store.write_record(record)
