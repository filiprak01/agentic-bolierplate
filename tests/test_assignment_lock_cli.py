import json
from pathlib import Path

from agentic_boilerplate.cli import main
from agentic_boilerplate.domain import AgentRole, AssignmentLockStatus, acquire_assignment_lock
from agentic_boilerplate.storage import FileAssignmentLockStore


def test_worker_locks_list_prints_existing_locks(tmp_path: Path, capsys) -> None:
    store_root = tmp_path / "agent-state"
    FileAssignmentLockStore(store_root).create_lock(_lock("session-1"))

    result = main(
        [
            "--env-file",
            str(tmp_path / "missing.env"),
            "worker",
            "locks",
            "list",
            "--lock-store-root",
            str(store_root),
        ]
    )

    output = capsys.readouterr().out
    assert result == 0
    assert "jira_issue_key\trole\tworker_session_id\tstatus\tupdated_at\tworkspace_path\texpires_at" in output
    assert "AGENT-449\tscheduler\tsession-1\tactive" in output


def test_worker_locks_list_json_is_machine_readable(tmp_path: Path, capsys) -> None:
    store_root = tmp_path / "agent-state"
    FileAssignmentLockStore(store_root).create_lock(_lock("session-1"))

    result = main(
        [
            "--env-file",
            str(tmp_path / "missing.env"),
            "worker",
            "locks",
            "list",
            "--lock-store-root",
            str(store_root),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert result == 0
    assert payload["items"][0]["jira_issue_key"] == "AGENT-449"
    assert payload["items"][0]["status"] == "active"


def test_worker_locks_mark_stale_records_stale_metadata(tmp_path: Path, capsys) -> None:
    store_root = tmp_path / "agent-state"
    store = FileAssignmentLockStore(store_root)
    store.create_lock(_lock("session-1", acquired_at="2026-07-15T06:00:00Z"))

    result = main(
        [
            "--env-file",
            str(tmp_path / "missing.env"),
            "worker",
            "locks",
            "mark-stale",
            "--lock-store-root",
            str(store_root),
            "--checked-at",
            "2026-07-15T11:00:00Z",
            "--stale-after-seconds",
            "14400",
        ]
    )

    output = capsys.readouterr().out
    restored = store.read_lock("AGENT-449", "scheduler", "session-1")
    assert result == 0
    assert "marked_stale\t1" in output
    assert restored.status is AssignmentLockStatus.STALE
    assert restored.updated_at == "2026-07-15T11:00:00Z"


def test_worker_locks_release_requires_explicit_confirmation(tmp_path: Path, capsys) -> None:
    store_root = tmp_path / "agent-state"
    FileAssignmentLockStore(store_root).create_lock(_lock("session-1"))

    result = main(
        [
            "--env-file",
            str(tmp_path / "missing.env"),
            "worker",
            "locks",
            "release",
            "--lock-store-root",
            str(store_root),
            "--jira-issue-key",
            "AGENT-449",
            "--role",
            "scheduler",
            "--worker-session-id",
            "session-1",
            "--released-at",
            "2026-07-15T11:00:00Z",
            "--reason",
            "stale_replaced",
            "--audit-note",
            "Operator checked stale session and approved release.",
        ]
    )

    captured = capsys.readouterr()
    assert result == 1
    assert "without --confirm" in captured.err


def test_worker_locks_release_refuses_active_lock_without_allow_active(tmp_path: Path, capsys) -> None:
    store_root = tmp_path / "agent-state"
    FileAssignmentLockStore(store_root).create_lock(_lock("session-1"))

    result = _release_command(tmp_path, store_root, extra_args=["--confirm"])

    captured = capsys.readouterr()
    assert result == 1
    assert "without --allow-active" in captured.err


def test_worker_locks_release_selected_stale_lock_with_audit_note(tmp_path: Path, capsys) -> None:
    store_root = tmp_path / "agent-state"
    store = FileAssignmentLockStore(store_root)
    store.create_lock(_lock("session-1", acquired_at="2026-07-15T06:00:00Z"))
    store.mark_stale_locks(checked_at="2026-07-15T11:00:00Z", stale_after_seconds=14400)

    result = _release_command(tmp_path, store_root, extra_args=["--confirm", "--json"])

    payload = json.loads(capsys.readouterr().out)
    restored = store.read_lock("AGENT-449", "scheduler", "session-1")
    assert result == 0
    assert payload["status"] == "released"
    assert payload["audit_note"] == "Operator checked stale session and approved release."
    assert restored.status is AssignmentLockStatus.RELEASED
    assert restored.audit_note == "Operator checked stale session and approved release."


def _release_command(tmp_path: Path, store_root: Path, *, extra_args: list[str]) -> int:
    return main(
        [
            "--env-file",
            str(tmp_path / "missing.env"),
            "worker",
            "locks",
            "release",
            "--lock-store-root",
            str(store_root),
            "--jira-issue-key",
            "AGENT-449",
            "--role",
            "scheduler",
            "--worker-session-id",
            "session-1",
            "--released-at",
            "2026-07-15T11:30:00Z",
            "--reason",
            "stale_replaced",
            "--audit-note",
            "Operator checked stale session and approved release.",
            *extra_args,
        ]
    )


def _lock(session_id: str, *, acquired_at: str = "2026-07-15T10:00:00Z"):
    return acquire_assignment_lock(
        jira_issue_key="AGENT-449",
        role=AgentRole.SCHEDULER,
        worker_session_id=session_id,
        acquired_at=acquired_at,
        dependency_gate_passed=True,
    )
