from pathlib import Path
from dataclasses import replace

import pytest

from agentic_boilerplate.domain import AgentRole
from agentic_boilerplate.domain.agent_assignment import (
    AgentAssignment,
    AgentRegistry,
    AssignmentPaths,
    AssignmentStatus,
    WorkerInstance,
    WorkerStatus,
    assign_worker,
)
from agentic_boilerplate.storage.agent_assignment import (
    AGENT_ASSIGNMENT_FOLDER,
    AGENT_REGISTRY_FOLDER,
    AGENT_WORKER_FOLDER,
    AgentAssignmentAlreadyExistsError,
    AgentAssignmentNotFoundError,
    FileAgentAssignmentStore,
    InvalidAgentAssignmentKeyError,
)


def test_store_creates_registry_assignment_and_worker_directories(tmp_path: Path) -> None:
    store = FileAgentAssignmentStore(tmp_path)

    directories = store.ensure_directories()

    assert [directory.name for directory in directories] == [
        AGENT_REGISTRY_FOLDER,
        AGENT_ASSIGNMENT_FOLDER,
        AGENT_WORKER_FOLDER,
    ]
    assert all(directory.is_dir() for directory in directories)


def test_create_read_save_and_list_assignments(tmp_path: Path) -> None:
    store = FileAgentAssignmentStore(tmp_path)
    assignment = _assignment()

    location = store.create_assignment(assignment)
    assigned = assign_worker(
        assignment,
        worker_id="developer-1",
        codex_job_id="codex-job-AGENT-40",
        started_at="2026-06-22T08:00:00Z",
        updated_at="2026-06-22T08:00:00Z",
    )
    saved = store.save_assignment(assigned)
    restored = store.read_assignment(assignment.id)
    listed = store.list_assignments()

    assert location.path == tmp_path / AGENT_ASSIGNMENT_FOLDER / "assignment-AGENT-40.json"
    assert saved.path == location.path
    assert restored == assigned
    assert listed == (assigned,)


def test_list_assignments_can_filter_by_project_id(tmp_path: Path) -> None:
    store = FileAgentAssignmentStore(tmp_path)
    ap_assignment = replace(_assignment(), id="assignment-AP-1", jira_issue_key="AP-1", project_id="AP")
    agent_assignment = replace(_assignment(), id="assignment-AGENT-1", jira_issue_key="AGENT-1", project_id="AGENT")

    store.create_assignment(ap_assignment)
    store.create_assignment(agent_assignment)

    assert store.list_assignments(project_id="AP") == (ap_assignment,)
    assert store.list_assignments(project_id="AGENT") == (agent_assignment,)


def test_create_read_save_and_list_workers(tmp_path: Path) -> None:
    store = FileAgentAssignmentStore(tmp_path)
    worker = _worker()

    location = store.create_worker(worker)
    updated = WorkerInstance(**{**worker.__dict__, "status": WorkerStatus.ASSIGNED, "current_assignment_id": "a1"})
    saved = store.save_worker(updated)

    assert location.path == tmp_path / AGENT_WORKER_FOLDER / "developer-1.json"
    assert saved.path == location.path
    assert store.read_worker(worker.id) == updated
    assert store.list_workers() == (updated,)


def test_create_read_save_and_list_registries(tmp_path: Path) -> None:
    store = FileAgentAssignmentStore(tmp_path)
    registry = AgentRegistry(
        id="main",
        workers=(_worker(),),
        assignments=(_assignment(),),
        created_at="2026-06-22T07:55:00Z",
        updated_at="2026-06-22T07:55:00Z",
    )

    location = store.create_registry(registry)
    saved = store.save_registry(registry)

    assert location.path == tmp_path / AGENT_REGISTRY_FOLDER / "main.json"
    assert saved.path == location.path
    assert store.read_registry("main") == registry
    assert store.list_registries() == (registry,)


def test_duplicate_missing_and_invalid_assignment_ids_are_rejected(tmp_path: Path) -> None:
    store = FileAgentAssignmentStore(tmp_path)
    assignment = _assignment()
    store.create_assignment(assignment)

    with pytest.raises(AgentAssignmentAlreadyExistsError):
        store.create_assignment(assignment)
    with pytest.raises(AgentAssignmentNotFoundError):
        store.read_assignment("missing")
    with pytest.raises(InvalidAgentAssignmentKeyError):
        store.assignment_path("../escape")


def _worker() -> WorkerInstance:
    return WorkerInstance(
        id="developer-1",
        role=AgentRole.DEVELOPER,
        status=WorkerStatus.AVAILABLE,
        display_name="Developer 1",
        registered_at="2026-06-22T07:55:00Z",
        updated_at="2026-06-22T07:55:00Z",
    )


def _assignment() -> AgentAssignment:
    return AgentAssignment(
        id="assignment-AGENT-40",
        jira_issue_key="AGENT-40",
        role=AgentRole.DEVELOPER,
        status=AssignmentStatus.QUEUED,
        paths=AssignmentPaths(
            context_pack_path="data/context-packs/AGENT-40/context.json",
            codex_job_path="data/codex-jobs/AGENT-40/job.json",
            output_path="data/codex-results/AGENT-40/result.json",
        ),
        created_at="2026-06-22T07:55:00Z",
        updated_at="2026-06-22T07:55:00Z",
    )
