import json
from pathlib import Path

from agentic_boilerplate.cli import main


def test_orchestration_events_cli_enqueue_list_and_dedupe(tmp_path: Path, capsys) -> None:
    store_root = tmp_path / "agent-state"

    result = main(
        [
            "--env-file",
            str(tmp_path / "missing.env"),
            "orchestration-events",
            "enqueue",
            "--event-store-root",
            str(store_root),
            "--id",
            "event-1",
            "--type",
            "pr_merged",
            "--source-role",
            "review",
            "--target-role",
            "tester",
            "--jira-issue-key",
            "AGENT-629",
            "--source-assignment-id",
            "assignment-629",
            "--scope-key",
            "r12-s3",
            "--project-id",
            "AGENT",
            "--payload-json",
            '{"pr": 159}',
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert result == 0
    assert payload["created"] is True
    assert payload["event"]["idempotency_key"] == "pr_merged:AGENT-629:assignment-629:r12-s3"
    assert payload["event"]["project_id"] == "AGENT"

    duplicate_result = main(
        [
            "--env-file",
            str(tmp_path / "missing.env"),
            "orchestration-events",
            "enqueue",
            "--event-store-root",
            str(store_root),
            "--id",
            "event-duplicate",
            "--type",
            "pr_merged",
            "--source-role",
            "review",
            "--target-role",
            "tester",
            "--jira-issue-key",
            "AGENT-629",
            "--source-assignment-id",
            "assignment-629",
            "--scope-key",
            "r12-s3",
            "--project-id",
            "AGENT",
            "--json",
        ]
    )
    duplicate_payload = json.loads(capsys.readouterr().out)

    assert duplicate_result == 0
    assert duplicate_payload["created"] is False
    assert duplicate_payload["duplicate_of"] == "event-1"

    list_result = main(
        [
            "--env-file",
            str(tmp_path / "missing.env"),
            "orchestration-events",
            "list",
            "--event-store-root",
            str(store_root),
            "--project-id",
            "AGENT",
            "--json",
        ]
    )
    list_payload = json.loads(capsys.readouterr().out)

    assert list_result == 0
    assert [item["id"] for item in list_payload["items"]] == ["event-1"]

    empty_result = main(
        [
            "--env-file",
            str(tmp_path / "missing.env"),
            "orchestration-events",
            "list",
            "--event-store-root",
            str(store_root),
            "--project-id",
            "OTHER",
            "--json",
        ]
    )
    empty_payload = json.loads(capsys.readouterr().out)
    assert empty_result == 0
    assert empty_payload["items"] == []


def test_orchestration_events_cli_claim_complete_and_reject_paths(tmp_path: Path, capsys) -> None:
    store_root = tmp_path / "agent-state"
    main(
        [
            "--env-file",
            str(tmp_path / "missing.env"),
            "orchestration-events",
            "enqueue",
            "--event-store-root",
            str(store_root),
            "--id",
            "event-2",
            "--type",
            "regression_requested",
            "--source-role",
            "release_manager",
            "--target-role",
            "tester",
            "--scope-key",
            "r12-s3",
            "--json",
        ]
    )
    capsys.readouterr()

    claim_result = main(
        [
            "--env-file",
            str(tmp_path / "missing.env"),
            "orchestration-events",
            "claim-next",
            "--event-store-root",
            str(store_root),
            "--updated-at",
            "2026-08-10T02:00:00Z",
            "--json",
        ]
    )
    claim_payload = json.loads(capsys.readouterr().out)

    assert claim_result == 0
    assert claim_payload["claimed"] is True
    assert claim_payload["event"]["status"] == "processing"

    complete_result = main(
        [
            "--env-file",
            str(tmp_path / "missing.env"),
            "orchestration-events",
            "complete",
            "event-2",
            "--event-store-root",
            str(store_root),
            "--processed-at",
            "2026-08-10T02:05:00Z",
            "--json",
        ]
    )
    complete_payload = json.loads(capsys.readouterr().out)

    assert complete_result == 0
    assert complete_payload["event"]["status"] == "processed"

    reject_result = main(
        [
            "--env-file",
            str(tmp_path / "missing.env"),
            "orchestration-events",
            "reject",
            "event-2",
            "--event-store-root",
            str(store_root),
            "--reason",
            "already processed",
        ]
    )
    error = capsys.readouterr().err

    assert reject_result == 1
    assert "Cannot transition orchestration event from processed to rejected" in error
