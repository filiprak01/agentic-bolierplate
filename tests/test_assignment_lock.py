import pytest

from agentic_boilerplate.domain import (
    AgentRole,
    AssignmentLockReleaseReason,
    AssignmentLockStatus,
    acquire_assignment_lock,
    evaluate_assignment_lock_request,
    is_assignment_lock_stale,
    release_assignment_lock,
)


def test_assignment_lock_allows_first_claim_after_dependency_gate() -> None:
    decision = evaluate_assignment_lock_request(
        jira_issue_key="AGENT-450",
        role=AgentRole.SCHEDULER,
        worker_session_id="scheduler-session-1",
        requested_at="2026-07-10T20:00:00Z",
        dependency_gate_passed=True,
    )

    lock = acquire_assignment_lock(
        jira_issue_key=decision.jira_issue_key,
        role=AgentRole.SCHEDULER,
        worker_session_id=decision.worker_session_id,
        acquired_at="2026-07-10T20:00:00Z",
        dependency_gate_passed=True,
    )

    assert decision.allowed is True
    assert lock.jira_issue_key == "AGENT-450"
    assert lock.role is AgentRole.SCHEDULER
    assert lock.worker_session_id == "scheduler-session-1"
    assert lock.status is AssignmentLockStatus.ACTIVE
    assert lock.acquired_at == "2026-07-10T20:00:00Z"


def test_assignment_lock_blocks_parallel_session_when_active() -> None:
    existing = acquire_assignment_lock(
        jira_issue_key="AGENT-450",
        role=AgentRole.SCHEDULER,
        worker_session_id="scheduler-session-1",
        acquired_at="2026-07-10T20:00:00Z",
        dependency_gate_passed=True,
    )

    decision = evaluate_assignment_lock_request(
        jira_issue_key="AGENT-450",
        role=AgentRole.SCHEDULER,
        worker_session_id="scheduler-session-2",
        requested_at="2026-07-10T21:00:00Z",
        dependency_gate_passed=True,
        existing_lock=existing,
    )

    assert decision.allowed is False
    assert decision.status is AssignmentLockStatus.BLOCKED
    assert "scheduler-session-1" in decision.reasons[0]


def test_assignment_lock_can_replace_stale_lock() -> None:
    existing = acquire_assignment_lock(
        jira_issue_key="AGENT-450",
        role=AgentRole.SCHEDULER,
        worker_session_id="scheduler-session-1",
        acquired_at="2026-07-10T20:00:00Z",
        dependency_gate_passed=True,
    )

    decision = evaluate_assignment_lock_request(
        jira_issue_key="AGENT-450",
        role=AgentRole.SCHEDULER,
        worker_session_id="scheduler-session-2",
        requested_at="2026-07-11T01:00:00Z",
        dependency_gate_passed=True,
        existing_lock=existing,
    )

    assert is_assignment_lock_stale(existing, checked_at="2026-07-11T01:00:00Z")
    assert decision.allowed is True
    assert "stale" in decision.reasons[0]


def test_assignment_lock_requires_dependency_gate_before_claim() -> None:
    decision = evaluate_assignment_lock_request(
        jira_issue_key="AGENT-450",
        role=AgentRole.SCHEDULER,
        worker_session_id="scheduler-session-1",
        requested_at="2026-07-10T20:00:00Z",
        dependency_gate_passed=False,
    )

    assert decision.allowed is False
    assert decision.status is AssignmentLockStatus.BLOCKED
    assert "Dependency gate must pass" in decision.reasons[0]


def test_assignment_lock_releases_at_durable_stop_points() -> None:
    lock = acquire_assignment_lock(
        jira_issue_key="AGENT-450",
        role=AgentRole.SCHEDULER,
        worker_session_id="scheduler-session-1",
        acquired_at="2026-07-10T20:00:00Z",
        dependency_gate_passed=True,
    )

    released = release_assignment_lock(
        lock,
        released_at="2026-07-10T21:00:00Z",
        reason=AssignmentLockReleaseReason.PAUSED_LIMIT,
    )

    assert released.status is AssignmentLockStatus.RELEASED
    assert released.release_reason == "paused_limit"
    assert released.released_at == "2026-07-10T21:00:00Z"
    assert not is_assignment_lock_stale(released, checked_at="2026-07-11T01:00:00Z")


def test_assignment_lock_rejects_invalid_stale_window() -> None:
    lock = acquire_assignment_lock(
        jira_issue_key="AGENT-450",
        role=AgentRole.SCHEDULER,
        worker_session_id="scheduler-session-1",
        acquired_at="2026-07-10T20:00:00Z",
        dependency_gate_passed=True,
    )

    with pytest.raises(ValueError, match="stale_after_seconds"):
        is_assignment_lock_stale(lock, checked_at="2026-07-10T20:00:00Z", stale_after_seconds=0)
