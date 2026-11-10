import json
from pathlib import Path

from agentic_boilerplate.cli import main


def test_agent_messages_cli_publish_list_and_dedupe(tmp_path: Path, capsys) -> None:
    store_root = tmp_path / "agent-state"

    result = main(
        [
            "--env-file",
            str(tmp_path / "missing.env"),
            "agent-messages",
            "publish",
            "--message-root",
            str(store_root),
            "--id",
            "message-1",
            "--type",
            "review_requested",
            "--source-role",
            "developer",
            "--target-role",
            "review",
            "--target-channel",
            "role",
            "--project-id",
            "AP",
            "--jira-project-key",
            "AP",
            "--jira-issue-key",
            "AP-29",
            "--assignment-id",
            "assignment-ap-29",
            "--correlation-id",
            "workflow-ap-29",
            "--payload-json",
            '{"pr_url":"https://github.com/org/repo/pull/1"}',
            "--artifact-ref",
            "data/agent-logs/AP-29/evidence.md",
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert result == 0
    assert payload["created"] is True
    assert payload["message"]["idempotency_key"] == (
        "review_requested:AP:AP-29:assignment-ap-29:review:role:workflow-ap-29:-"
    )
    assert payload["message"]["project_id"] == "AP"
    assert payload["message"]["target_role"] == "review"

    duplicate_result = main(
        [
            "--env-file",
            str(tmp_path / "missing.env"),
            "agent-messages",
            "publish",
            "--message-root",
            str(store_root),
            "--id",
            "message-duplicate",
            "--type",
            "review_requested",
            "--source-role",
            "developer",
            "--target-role",
            "review",
            "--target-channel",
            "role",
            "--project-id",
            "AP",
            "--jira-issue-key",
            "AP-29",
            "--assignment-id",
            "assignment-ap-29",
            "--correlation-id",
            "workflow-ap-29",
            "--json",
        ]
    )
    duplicate_payload = json.loads(capsys.readouterr().out)

    assert duplicate_result == 0
    assert duplicate_payload["created"] is False
    assert duplicate_payload["duplicate_of"] == "message-1"

    list_result = main(
        [
            "--env-file",
            str(tmp_path / "missing.env"),
            "agent-messages",
            "list",
            "--message-root",
            str(store_root),
            "--project-id",
            "AP",
            "--json",
        ]
    )
    list_payload = json.loads(capsys.readouterr().out)

    assert list_result == 0
    assert [item["id"] for item in list_payload["items"]] == ["message-1"]

    empty_result = main(
        [
            "--env-file",
            str(tmp_path / "missing.env"),
            "agent-messages",
            "list",
            "--message-root",
            str(store_root),
            "--project-id",
            "OTHER",
            "--json",
        ]
    )
    empty_payload = json.loads(capsys.readouterr().out)

    assert empty_result == 0
    assert empty_payload["items"] == []


def test_agent_messages_cli_ack_consume_and_reject_paths(tmp_path: Path, capsys) -> None:
    store_root = tmp_path / "agent-state"
    main(
        [
            "--env-file",
            str(tmp_path / "missing.env"),
            "agent-messages",
            "publish",
            "--message-root",
            str(store_root),
            "--id",
            "message-2",
            "--type",
            "test_requested",
            "--source-role",
            "review",
            "--target-role",
            "tester",
            "--target-channel",
            "role",
            "--project-id",
            "AP",
            "--json",
        ]
    )
    capsys.readouterr()

    ack_result = main(
        [
            "--env-file",
            str(tmp_path / "missing.env"),
            "agent-messages",
            "ack",
            "message-2",
            "--message-root",
            str(store_root),
            "--acknowledged-at",
            "2026-08-10T02:10:00Z",
            "--json",
        ]
    )
    ack_payload = json.loads(capsys.readouterr().out)

    assert ack_result == 0
    assert ack_payload["message"]["status"] == "acknowledged"

    consume_result = main(
        [
            "--env-file",
            str(tmp_path / "missing.env"),
            "agent-messages",
            "consume",
            "message-2",
            "--message-root",
            str(store_root),
            "--consumed-at",
            "2026-08-10T02:12:00Z",
            "--json",
        ]
    )
    consume_payload = json.loads(capsys.readouterr().out)

    assert consume_result == 0
    assert consume_payload["message"]["status"] == "consumed"

    reject_result = main(
        [
            "--env-file",
            str(tmp_path / "missing.env"),
            "agent-messages",
            "reject",
            "message-2",
            "--message-root",
            str(store_root),
            "--reason",
            "already consumed",
        ]
    )
    error = capsys.readouterr().err

    assert reject_result == 1
    assert "Cannot transition agent message from consumed to rejected" in error
