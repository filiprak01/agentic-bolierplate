"""Assignment lock policy for session and worker concurrency control."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum

from agentic_boilerplate.domain.po_inbox import AgentRole


DEFAULT_ASSIGNMENT_LOCK_STALE_AFTER_SECONDS = 4 * 60 * 60


class AssignmentLockStatus(str, Enum):
    """Durable assignment lock state."""

    ACTIVE = "active"
    RELEASED = "released"
    STALE = "stale"
    BLOCKED = "blocked"


class AssignmentLockReleaseReason(str, Enum):
    """Supported lock release reasons."""

    COMPLETED = "completed"
    PAUSED_LIMIT = "paused_limit"
    FAILED = "failed"
    CANCELLED = "cancelled"
    STALE_REPLACED = "stale_replaced"


@dataclass(frozen=True)
class AssignmentLock:
    """One lock protecting a Jira issue from parallel worker execution."""

    jira_issue_key: str
    role: AgentRole
    worker_session_id: str
    status: AssignmentLockStatus
    acquired_at: str
    updated_at: str
    dependency_gate_passed: bool
    workspace_path: str = ""
    expires_at: str = ""
    release_reason: str = ""
    released_at: str = ""
    audit_note: str = ""


@dataclass(frozen=True)
class AssignmentLockDecision:
    """Decision for acquiring or keeping an assignment lock."""

    jira_issue_key: str
    worker_session_id: str
    allowed: bool
    status: AssignmentLockStatus
    reasons: tuple[str, ...]
    existing_lock: AssignmentLock | None = None


def evaluate_assignment_lock_request(
    *,
    jira_issue_key: str,
    role: AgentRole,
    worker_session_id: str,
    requested_at: str,
    dependency_gate_passed: bool,
    existing_lock: AssignmentLock | None = None,
    stale_after_seconds: int = DEFAULT_ASSIGNMENT_LOCK_STALE_AFTER_SECONDS,
) -> AssignmentLockDecision:
    """Decide whether a worker/session may claim work for a Jira issue."""

    issue_key = _require_text("jira_issue_key", jira_issue_key)
    session_id = _require_text("worker_session_id", worker_session_id)
    _require_text("requested_at", requested_at)
    reasons: list[str] = []
    if not dependency_gate_passed:
        reasons.append("Dependency gate must pass before an assignment lock can be acquired.")
    if existing_lock is not None and existing_lock.status is AssignmentLockStatus.ACTIVE:
        if existing_lock.worker_session_id == session_id:
            return AssignmentLockDecision(
                jira_issue_key=issue_key,
                worker_session_id=session_id,
                allowed=dependency_gate_passed,
                status=AssignmentLockStatus.ACTIVE if dependency_gate_passed else AssignmentLockStatus.BLOCKED,
                reasons=tuple(reasons) or ("Existing lock is already owned by this worker/session.",),
                existing_lock=existing_lock,
            )
        if not is_assignment_lock_stale(
            existing_lock,
            checked_at=requested_at,
            stale_after_seconds=stale_after_seconds,
        ):
            reasons.append(
                f"Active lock is held by {existing_lock.worker_session_id} for {existing_lock.jira_issue_key}."
            )
            return AssignmentLockDecision(
                jira_issue_key=issue_key,
                worker_session_id=session_id,
                allowed=False,
                status=AssignmentLockStatus.BLOCKED,
                reasons=tuple(reasons),
                existing_lock=existing_lock,
            )
        reasons.append("Existing active lock is stale and may be replaced.")

    return AssignmentLockDecision(
        jira_issue_key=issue_key,
        worker_session_id=session_id,
        allowed=not reasons or reasons == ["Existing active lock is stale and may be replaced."],
        status=AssignmentLockStatus.ACTIVE if dependency_gate_passed else AssignmentLockStatus.BLOCKED,
        reasons=tuple(reasons) or ("Assignment lock can be acquired.",),
        existing_lock=existing_lock,
    )


def acquire_assignment_lock(
    *,
    jira_issue_key: str,
    role: AgentRole,
    worker_session_id: str,
    acquired_at: str,
    dependency_gate_passed: bool,
    workspace_path: str = "",
    expires_at: str = "",
) -> AssignmentLock:
    """Create a valid active lock after the acquisition decision allows it."""

    return AssignmentLock(
        jira_issue_key=_require_text("jira_issue_key", jira_issue_key),
        role=role,
        worker_session_id=_require_text("worker_session_id", worker_session_id),
        status=AssignmentLockStatus.ACTIVE if dependency_gate_passed else AssignmentLockStatus.BLOCKED,
        acquired_at=_require_text("acquired_at", acquired_at),
        updated_at=_require_text("acquired_at", acquired_at),
        dependency_gate_passed=dependency_gate_passed,
        workspace_path=workspace_path.strip(),
        expires_at=expires_at.strip(),
    )


def release_assignment_lock(
    lock: AssignmentLock,
    *,
    released_at: str,
    reason: AssignmentLockReleaseReason,
    audit_note: str = "",
) -> AssignmentLock:
    """Release an active lock when work reaches a durable stop point."""

    if lock.status not in (AssignmentLockStatus.ACTIVE, AssignmentLockStatus.STALE):
        raise ValueError("Only active or stale assignment locks can be released.")
    return replace(
        lock,
        status=AssignmentLockStatus.RELEASED,
        release_reason=reason.value,
        released_at=_require_text("released_at", released_at),
        updated_at=_require_text("released_at", released_at),
        audit_note=audit_note.strip(),
    )


def is_assignment_lock_stale(
    lock: AssignmentLock,
    *,
    checked_at: str,
    stale_after_seconds: int = DEFAULT_ASSIGNMENT_LOCK_STALE_AFTER_SECONDS,
) -> bool:
    """Return true when a lock has not been updated within the stale window."""

    if lock.status is not AssignmentLockStatus.ACTIVE:
        return False
    if stale_after_seconds <= 0:
        raise ValueError("stale_after_seconds must be positive")
    updated = _parse_utc(lock.updated_at)
    checked = _parse_utc(_require_text("checked_at", checked_at))
    return (checked - updated).total_seconds() >= stale_after_seconds


def _parse_utc(value: str) -> datetime:
    text = _require_text("timestamp", value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _require_text(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    return value.strip()
