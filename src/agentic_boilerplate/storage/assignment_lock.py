"""File-backed assignment lock store."""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from agentic_boilerplate.domain.assignment_lock import (
    AssignmentLock,
    AssignmentLockReleaseReason,
    AssignmentLockStatus,
    is_assignment_lock_stale,
    release_assignment_lock,
)
from agentic_boilerplate.domain.po_inbox import AgentRole

ASSIGNMENT_LOCK_FILE_SUFFIX = ".json"
ASSIGNMENT_LOCK_FOLDER = "assignment-locks"
_SAFE_LOCK_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class AssignmentLockStoreError(RuntimeError):
    """Base error for assignment lock store failures."""


class AssignmentLockAlreadyExistsError(AssignmentLockStoreError):
    """Raised when a lock file already exists."""


class AssignmentLockNotFoundError(AssignmentLockStoreError):
    """Raised when a lock cannot be found."""


class DuplicateActiveAssignmentLockError(AssignmentLockStoreError):
    """Raised when a Jira issue and role already have an active lock."""


class InvalidAssignmentLockKeyError(AssignmentLockStoreError):
    """Raised when a lock key is unsafe for file storage."""


@dataclass(frozen=True)
class AssignmentLockLocation:
    jira_issue_key: str
    role: AgentRole
    worker_session_id: str
    path: Path


class FileAssignmentLockStore:
    """Store assignment locks as durable local JSON files."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    @property
    def lock_root(self) -> Path:
        return self.root / ASSIGNMENT_LOCK_FOLDER

    def ensure_directories(self) -> Path:
        self.lock_root.mkdir(parents=True, exist_ok=True)
        return self.lock_root

    def lock_path(self, jira_issue_key: str, role: AgentRole | str, worker_session_id: str) -> Path:
        key = _lock_file_stem(jira_issue_key, role, worker_session_id)
        return self.lock_root / f"{key}{ASSIGNMENT_LOCK_FILE_SUFFIX}"

    def create_lock(self, lock: AssignmentLock) -> AssignmentLockLocation:
        self.ensure_directories()
        path = self.lock_path(lock.jira_issue_key, lock.role, lock.worker_session_id)
        if path.exists():
            existing = self.read_lock(lock.jira_issue_key, lock.role, lock.worker_session_id)
            if existing.status is AssignmentLockStatus.ACTIVE:
                raise AssignmentLockAlreadyExistsError(
                    f"Assignment lock already exists for {lock.jira_issue_key}/{lock.role.value}/{lock.worker_session_id}."
                )
        duplicate = self.active_lock_for(lock.jira_issue_key, lock.role)
        if duplicate is not None and lock.status is AssignmentLockStatus.ACTIVE:
            raise DuplicateActiveAssignmentLockError(
                f"Active assignment lock already exists for {lock.jira_issue_key}/{lock.role.value}."
            )
        _atomic_write_json(path, assignment_lock_to_dict(lock))
        return AssignmentLockLocation(
            jira_issue_key=lock.jira_issue_key,
            role=lock.role,
            worker_session_id=lock.worker_session_id,
            path=path,
        )

    def save_lock(self, lock: AssignmentLock) -> AssignmentLockLocation:
        self.ensure_directories()
        path = self.lock_path(lock.jira_issue_key, lock.role, lock.worker_session_id)
        _atomic_write_json(path, assignment_lock_to_dict(lock))
        return AssignmentLockLocation(
            jira_issue_key=lock.jira_issue_key,
            role=lock.role,
            worker_session_id=lock.worker_session_id,
            path=path,
        )

    def read_lock(self, jira_issue_key: str, role: AgentRole | str, worker_session_id: str) -> AssignmentLock:
        path = self.lock_path(jira_issue_key, role, worker_session_id)
        if not path.is_file():
            raise AssignmentLockNotFoundError(
                f"Assignment lock was not found for {jira_issue_key}/{AgentRole(role).value}/{worker_session_id}."
            )
        with path.open("r", encoding="utf-8") as file:
            return assignment_lock_from_dict(json.load(file))

    def list_locks(self, *, status: AssignmentLockStatus | str | None = None) -> tuple[AssignmentLock, ...]:
        self.ensure_directories()
        locks = tuple(
            assignment_lock_from_dict(json.loads(path.read_text(encoding="utf-8")))
            for path in sorted(self.lock_root.glob(f"*{ASSIGNMENT_LOCK_FILE_SUFFIX}"))
        )
        if status is None:
            return locks
        wanted = AssignmentLockStatus(status)
        return tuple(lock for lock in locks if lock.status is wanted)

    def active_lock_for(self, jira_issue_key: str, role: AgentRole | str) -> AssignmentLock | None:
        wanted_role = AgentRole(role)
        for lock in self.list_locks(status=AssignmentLockStatus.ACTIVE):
            if lock.jira_issue_key == jira_issue_key and lock.role is wanted_role:
                return lock
        return None

    def release_lock(
        self,
        jira_issue_key: str,
        role: AgentRole | str,
        worker_session_id: str,
        *,
        released_at: str,
        reason: AssignmentLockReleaseReason | str,
        audit_note: str = "",
    ) -> AssignmentLock:
        released = release_assignment_lock(
            self.read_lock(jira_issue_key, role, worker_session_id),
            released_at=released_at,
            reason=AssignmentLockReleaseReason(reason),
            audit_note=audit_note,
        )
        self.save_lock(released)
        return released

    def mark_stale_locks(
        self,
        *,
        checked_at: str,
        stale_after_seconds: int,
    ) -> tuple[AssignmentLock, ...]:
        stale_locks: list[AssignmentLock] = []
        for lock in self.list_locks(status=AssignmentLockStatus.ACTIVE):
            if is_assignment_lock_stale(lock, checked_at=checked_at, stale_after_seconds=stale_after_seconds):
                stale_lock = replace(lock, status=AssignmentLockStatus.STALE, updated_at=checked_at)
                self.save_lock(stale_lock)
                stale_locks.append(stale_lock)
        return tuple(stale_locks)


def assignment_lock_to_dict(lock: AssignmentLock) -> dict[str, Any]:
    return {
        "jira_issue_key": lock.jira_issue_key,
        "role": lock.role.value,
        "worker_session_id": lock.worker_session_id,
        "status": lock.status.value,
        "acquired_at": lock.acquired_at,
        "updated_at": lock.updated_at,
        "dependency_gate_passed": lock.dependency_gate_passed,
        "workspace_path": lock.workspace_path,
        "expires_at": lock.expires_at,
        "release_reason": lock.release_reason,
        "released_at": lock.released_at,
        "audit_note": lock.audit_note,
    }


def assignment_lock_from_dict(data: dict[str, Any]) -> AssignmentLock:
    return AssignmentLock(
        jira_issue_key=_require_text("jira_issue_key", data.get("jira_issue_key")),
        role=AgentRole(_require_text("role", data.get("role"))),
        worker_session_id=_require_text("worker_session_id", data.get("worker_session_id")),
        status=AssignmentLockStatus(_require_text("status", data.get("status"))),
        acquired_at=_require_text("acquired_at", data.get("acquired_at")),
        updated_at=_require_text("updated_at", data.get("updated_at")),
        dependency_gate_passed=bool(data.get("dependency_gate_passed")),
        workspace_path=str(data.get("workspace_path") or ""),
        expires_at=str(data.get("expires_at") or ""),
        release_reason=str(data.get("release_reason") or ""),
        released_at=str(data.get("released_at") or ""),
        audit_note=str(data.get("audit_note") or ""),
    )


def _lock_file_stem(jira_issue_key: str, role: AgentRole | str, worker_session_id: str) -> str:
    role_value = AgentRole(role).value
    parts = [_require_text("jira_issue_key", jira_issue_key), role_value, _require_text("worker_session_id", worker_session_id)]
    for part in parts:
        if not _SAFE_LOCK_KEY.fullmatch(part):
            raise InvalidAssignmentLockKeyError(
                "Assignment lock keys may contain letters, numbers, dots, underscores, and hyphens."
            )
    return "__".join(parts)


def _require_text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    return value.strip()


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temp_path.open("w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, sort_keys=True)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        temp_path.replace(path)
    finally:
        temp_path.unlink(missing_ok=True)
