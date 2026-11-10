import json
from pathlib import Path

from agentic_boilerplate.cli import main


def test_publish_handoff_cli_creates_review_requested_message(tmp_path: Path, capsys) -> None:
    result = main(
        [
            "--env-file",
            str(tmp_path / "missing.env"),
            "agent-messages",
            "publish-handoff",
            "--message-root",
            str(tmp_path / "agent-state"),
            "--id",
            "handoff-ap-29-dev-review",
            "--current-status",
            "IN PROGRESS",
            "--event",
            "development_completed",
            "--actor",
            "developer",
            "--target-status",
            "DEV COMPLETED",
            "--project-id",
            "AP",
            "--project-name",
            "Airline POC",
            "--jira-project-key",
            "AP",
            "--jira-issue-key",
            "AP-29",
            "--assignment-id",
            "assignment-ap-29",
            "--workspace-path",
            "/workspaces/AP-29",
            "--context-pack-path",
            "data/context-packs/AP-29/context.md",
            "--evidence-path",
            "data/agent-logs/AP-29/developer-evidence.md",
            "--communication-channel-id",
            "channel-ap-29",
            "--branch-name",
            "feature/AP-29-booking-flow",
            "--pull-request-url",
            "https://github.com/org/repo/pull/42",
            "--artifact",
            "completed_subtasks=AP-101,AP-102",
            "--artifact",
            "jira_pr_link=https://github.com/org/repo/pull/42",
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert result == 0
    assert payload["allowed"] is True
    assert payload["created"] is True
    assert payload["route_id"] == "in-progress.development-completed"
    assert payload["message"]["message_type"] == "review_requested"
    assert payload["message"]["target_role"] == "review"
    assert payload["message"]["payload"]["artifacts"]["completed_subtasks"] == "AP-101,AP-102"


def test_publish_handoff_cli_persists_blocked_message_when_artifacts_are_missing(
    tmp_path: Path,
    capsys,
) -> None:
    result = main(
        [
            "--env-file",
            str(tmp_path / "missing.env"),
            "agent-messages",
            "publish-handoff",
            "--message-root",
            str(tmp_path / "agent-state"),
            "--id",
            "handoff-ap-29-blocked",
            "--current-status",
            "IN PROGRESS",
            "--event",
            "development_completed",
            "--actor",
            "developer",
            "--project-id",
            "AP",
            "--jira-issue-key",
            "AP-29",
            "--assignment-id",
            "assignment-ap-29",
            "--workspace-path",
            "/workspaces/AP-29",
            "--context-pack-path",
            "data/context-packs/AP-29/context.md",
            "--evidence-path",
            "data/agent-logs/AP-29/developer-evidence.md",
            "--communication-channel-id",
            "channel-ap-29",
            "--artifact",
            "completed_subtasks=AP-101",
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    stored_path = Path(payload["blocked_message"])
    stored = json.loads(stored_path.read_text(encoding="utf-8"))

    assert result == 2
    assert payload["allowed"] is False
    assert "Required artifact 'pull_request_url' is missing" in "\n".join(payload["blockers"])
    assert stored["message_type"] == "blocked"
    assert stored["target_channel"] == "orchestrator"
    assert stored["payload"]["blocked"] is True


def test_publish_handoff_cli_creates_bug_fix_requested_message_for_failed_testing(
    tmp_path: Path,
    capsys,
) -> None:
    result = main(
        [
            "--env-file",
            str(tmp_path / "missing.env"),
            "agent-messages",
            "publish-handoff",
            "--message-root",
            str(tmp_path / "agent-state"),
            "--id",
            "handoff-ap-29-test-failed",
            "--current-status",
            "IN TESTING",
            "--event",
            "testing_failed",
            "--actor",
            "tester",
            "--target-status",
            "DEV COMPLETED",
            "--project-id",
            "AP",
            "--jira-issue-key",
            "AP-29",
            "--assignment-id",
            "assignment-ap-29-test",
            "--workspace-path",
            "/workspaces/AP-29",
            "--context-pack-path",
            "data/context-packs/AP-29/context.md",
            "--evidence-path",
            "data/agent-logs/AP-29/test-evidence.md",
            "--communication-channel-id",
            "channel-ap-29",
            "--artifact",
            "linked_bug=AP-99",
            "--artifact",
            "bug_related_labels=bug-related,has-linked-bug",
            "--artifact",
            "retest_scope=Retest AP-29 and AP-99",
            "--payload-json",
            '{"failed_acceptance_criteria":["AC1"]}',
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert result == 0
    assert payload["allowed"] is True
    assert payload["route_id"] == "in-testing.testing-failed"
    assert payload["message"]["message_type"] == "bug_fix_requested"
    assert payload["message"]["source_role"] == "tester"
    assert payload["message"]["target_role"] == "developer"
    assert payload["message"]["payload"]["artifacts"]["linked_bug"] == "AP-99"
