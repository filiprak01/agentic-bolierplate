import json
from pathlib import Path

from agentic_boilerplate.cli import main


def test_cli_create_list_read_and_answer_question(tmp_path: Path, capsys) -> None:
    root = str(tmp_path)

    assert (
        main(
            [
                "--inbox-root",
                root,
                "po-inbox",
                "create",
                "--id",
                "question-001",
                "--type",
                "blocking_question",
                "--title",
                "Choose Jira status",
                "--message",
                "Which status should drafts use?",
                "--business-impact",
                "Controls PO workflow.",
                "--recommendation",
                "Use FUNNEL.",
            ]
        )
        == 0
    )
    assert "created\tquestion-001\topen" in capsys.readouterr().out

    assert main(["--inbox-root", root, "po-inbox", "list", "--status", "open"]) == 0
    assert "question-001\topen\tblocking_question\tChoose Jira status" in capsys.readouterr().out

    assert main(["--inbox-root", root, "po-inbox", "read", "question-001"]) == 0
    item = json.loads(capsys.readouterr().out)
    assert item["id"] == "question-001"
    assert item["status"] == "open"

    assert main(["--inbox-root", root, "po-inbox", "answer", "question-001", "--answer", "Use FUNNEL."]) == 0
    assert "answered\tquestion-001\tanswered" in capsys.readouterr().out

    assert main(["--inbox-root", root, "po-inbox", "read", "question-001"]) == 0
    answered = json.loads(capsys.readouterr().out)
    assert answered["status"] == "answered"
    assert answered["answer"] == "Use FUNNEL."
    assert [event["action"] for event in answered["audit"]] == ["created", "answered"]


def test_cli_create_and_list_support_project_identity_filter(tmp_path: Path, capsys) -> None:
    root = str(tmp_path)

    assert (
        main(
            [
                "--inbox-root",
                root,
                "po-inbox",
                "create",
                "--id",
                "question-ap",
                "--type",
                "blocking_question",
                "--title",
                "Choose AP behavior",
                "--message",
                "Should AP use this process?",
                "--business-impact",
                "Controls AP setup.",
                "--recommendation",
                "Use the boilerplate process.",
                "--project-id",
                "AP",
                "--project-name",
                "Airline POC",
                "--repository",
                "example-org/airline-poc",
                "--jira-project-key",
                "AP",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert main(["--inbox-root", root, "po-inbox", "list", "--project-id", "AP"]) == 0
    assert "question-ap\topen\tblocking_question\tChoose AP behavior\tAP" in capsys.readouterr().out
    assert main(["--inbox-root", root, "po-inbox", "list", "--project-id", "OTHER"]) == 0
    assert "question-ap" not in capsys.readouterr().out


def test_cli_approval_request_approve_and_reject(tmp_path: Path, capsys) -> None:
    root = str(tmp_path)

    _create_approval(root, "approval-001", "Approve draft")
    capsys.readouterr()
    assert main(["--inbox-root", root, "po-inbox", "approve", "approval-001", "--answer", "Approved."]) == 0
    assert "approved\tapproval-001\tapproved" in capsys.readouterr().out

    _create_approval(root, "approval-002", "Reject draft")
    capsys.readouterr()
    assert main(["--inbox-root", root, "po-inbox", "reject", "approval-002", "--answer", "Rejected."]) == 0
    assert "rejected\tapproval-002\trejected" in capsys.readouterr().out

    assert main(["--inbox-root", root, "po-inbox", "list"]) == 0
    output = capsys.readouterr().out
    assert "approval-001\tapproved\tapproval_request\tApprove draft" in output
    assert "approval-002\trejected\tapproval_request\tReject draft" in output


def test_cli_resolve_archives_fyi(tmp_path: Path, capsys) -> None:
    root = str(tmp_path)

    assert (
        main(
            [
                "--inbox-root",
                root,
                "po-inbox",
                "create",
                "--id",
                "fyi-001",
                "--type",
                "fyi",
                "--title",
                "Build finished",
                "--message",
                "Worker finished.",
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert main(["--inbox-root", root, "po-inbox", "resolve", "fyi-001", "--note", "Seen."]) == 0
    assert "resolved\tfyi-001\tarchived" in capsys.readouterr().out


def test_cli_import_accepts_schema_valid_external_item(tmp_path: Path, capsys) -> None:
    inbox_root = tmp_path / "platform" / "po-inbox"
    external_item = tmp_path / "external-question.json"
    external_item.write_text(
        json.dumps(
            {
                "id": "external-question-001",
                "message_type": "blocking_question",
                "status": "open",
                "title": "Choose release status",
                "message": "Which Jira status should release follow-ups use?",
                "agent_role": "release_manager",
                "created_at": "2026-07-10T18:00:00Z",
                "business_impact": "Controls release follow-up routing.",
                "recommendation": "Use FUNNEL until PO approval.",
                "options": [],
                "audit": [
                    {
                        "timestamp": "2026-07-10T18:00:00Z",
                        "actor": "release-manager",
                        "action": "created",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = main(["--inbox-root", str(inbox_root), "po-inbox", "import", "--input", str(external_item)])

    assert result == 0
    assert "imported\texternal-question-001\topen" in capsys.readouterr().out
    assert (inbox_root / "open" / "external-question-001.json").is_file()


def test_cli_import_rejects_invalid_external_item(tmp_path: Path, capsys) -> None:
    external_item = tmp_path / "bad-question.json"
    external_item.write_text(json.dumps({"id": "bad-question"}), encoding="utf-8")

    result = main(["--inbox-root", str(tmp_path / "po-inbox"), "po-inbox", "import", "--input", str(external_item)])

    captured = capsys.readouterr()
    assert result == 1
    assert "PO inbox item validation failed" in captured.err
    assert not (tmp_path / "po-inbox").exists()


def test_cli_validate_paths_rejects_target_project_inbox(tmp_path: Path, capsys) -> None:
    platform_inbox = tmp_path / "platform" / "data" / "po-inbox"
    target_project = tmp_path / "target-project"
    misplaced = target_project / "data" / "po-inbox"
    misplaced.mkdir(parents=True)

    result = main(
        [
            "po-inbox",
            "validate-paths",
            "--platform-inbox-root",
            str(platform_inbox),
            "--target-project-root",
            str(target_project),
        ]
    )

    output = capsys.readouterr().out
    assert result == 1
    assert "misplaced PO inbox path" in output
    assert str(misplaced.resolve()) in output


def test_cli_errors_are_concise_and_do_not_print_settings(tmp_path: Path, capsys) -> None:
    result = main(
        [
            "--inbox-root",
            str(tmp_path),
            "po-inbox",
            "create",
            "--id",
            "question-001",
            "--type",
            "blocking_question",
            "--title",
            "Choose Jira status",
            "--message",
            "Which status should drafts use?",
        ]
    )

    captured = capsys.readouterr()

    assert result == 1
    assert "business_impact" in captured.err
    assert "JIRA_API_TOKEN" not in captured.err
    assert "GITHUB_TOKEN" not in captured.err


def _create_approval(root: str, item_id: str, title: str) -> None:
    assert (
        main(
            [
                "--inbox-root",
                root,
                "po-inbox",
                "create",
                "--id",
                item_id,
                "--type",
                "approval_request",
                "--title",
                title,
                "--message",
                "Approve this draft?",
                "--business-impact",
                "Controls implementation.",
                "--recommendation",
                "Approve.",
            ]
        )
        == 0
    )
