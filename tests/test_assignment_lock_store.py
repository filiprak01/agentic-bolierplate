from pathlib import Path

import pytest

from agentic_boilerplate.domain import (
    AgentRole,
    AssignmentLockReleaseReason,
    AssignmentLockStatus,
    acquire_assignment_lock,
)
from agentic_boilerplate.storage import (
    ASSIGNMENT_LOCK_FOLDER,
    DuplicateActiveAssignmentLockError,
    FileAssignmentLockStore,
    InvalidAssignmentLockKeyError,
    assignment_lock_from_dict,
    assignment_lock_to_dict,
)


def test_assignment_lock_store_creates_reads_and_lists_locks(tmp_path: Path) -> None:
    store = FileAssignmentLockStore(tmp_path / "agent-state")
    lock = _lock("session-1")

    location = store.create_lock(lock)
    restored = store.read_lock("AGENT-448", AgentRole.SCHEDULER, "session-1")

    assert location.path == tmp_path / "agent-state" / ASSIGNMENT_LOCK_FOLDER / "AGENT-448__scheduler__session-1.json"
    assert restored == lock
    assert store.list_locks() == (lock,)
    assert store.list_locks(status=AssignmentLockStatus.ACTIVE) == (lock,)


def test_assignment_lock_store_prevents_duplicate_active_lock_for_same_issue_and_role(tmp_path: Path) -> None:
    store = FileAssignmentLockStore(tmp_path / "agent-state")
    store.create_lock(_lock("session-1"))

    with pytest.raises(DuplicateActiveAssignmentLockError, match="AGENT-448/scheduler"):
        store.create_lock(_lock("session-2"))


def test_assignment_lock_store_allows_new_active_lock_after_release(tmp_path: Path) -> None:
    store = FileAssignmentLockStore(tmp_path / "agent-state")
    store.create_lock(_lock("session-1"))

    released = store.release_lock(
        "AGENT-448",
        AgentRole.SCHEDULER,
        "session-1",
        released_at="2026-07-15T11:00:00Z",
        reason=AssignmentLockReleaseReason.COMPLETED,
    )
    replacement = _lock("session-2", acquired_at="2026-07-15T11:05:00Z")
    store.create_lock(replacement)

    assert released.status is AssignmentLockStatus.RELEASED
    assert released.release_reason == "completed"
    assert store.active_lock_for("AGENT-448", AgentRole.SCHEDULER) == replacement
    assert len(store.list_locks()) == 2


def test_assignment_lock_store_allows_same_worker_to_claim_after_released_lock(tmp_path: Path) -> None:
    store = FileAssignmentLockStore(tmp_path / "agent-state")
    store.create_lock(_lock("session-1"))
    store.release_lock(
        "AGENT-448",
        AgentRole.SCHEDULER,
        "session-1",
        released_at="2026-07-15T11:00:00Z",
        reason=AssignmentLockReleaseReason.COMPLETED,
        audit_note="Previous assignment completed.",
    )

    replacement = _lock("session-1", acquired_at="2026-07-15T11:05:00Z")
    location = store.create_lock(replacement)

    assert location.path == store.lock_path("AGENT-448", AgentRole.SCHEDULER, "session-1")
    assert store.active_lock_for("AGENT-448", AgentRole.SCHEDULER) == replacement
    assert store.read_lock("AGENT-448", AgentRole.SCHEDULER, "session-1") == replacement


def test_assignment_lock_store_marks_stale_locks_for_later_release(tmp_path: Path) -> None:
    store = FileAssignmentLockStore(tmp_path / "agent-state")
    store.create_lock(_lock("session-1", acquired_at="2026-07-15T06:00:00Z"))

    stale = store.mark_stale_locks(checked_at="2026-07-15T11:00:00Z", stale_after_seconds=4 * 60 * 60)
    restored = store.read_lock("AGENT-448", "scheduler", "session-1")

    assert len(stale) == 1
    assert stale[0].status is AssignmentLockStatus.STALE
    assert stale[0].updated_at == "2026-07-15T11:00:00Z"
    assert restored == stale[0]


def test_assignment_lock_store_round_trips_json_payload() -> None:
    lock = _lock(
        "session-1",
        workspace_path="/workspace/project-a",
        expires_at="2026-07-15T14:00:00Z",
    )

    restored = assignment_lock_from_dict(assignment_lock_to_dict(lock))

    assert restored == lock
    assert restored.workspace_path == "/workspace/project-a"
    assert restored.expires_at == "2026-07-15T14:00:00Z"


def test_assignment_lock_store_rejects_unsafe_file_keys(tmp_path: Path) -> None:
    store = FileAssignmentLockStore(tmp_path / "agent-state")

    with pytest.raises(InvalidAssignmentLockKeyError):
        store.create_lock(_lock("../bad"))


def _lock(
    session_id: str,
    *,
    acquired_at: str = "2026-07-15T10:00:00Z",
    workspace_path: str = "",
    expires_at: str = "",
):
    return acquire_assignment_lock(
        jira_issue_key="AGENT-448",
        role=AgentRole.SCHEDULER,
        worker_session_id=session_id,
        acquired_at=acquired_at,
        dependency_gate_passed=True,
        workspace_path=workspace_path,
        expires_at=expires_at,
    )
