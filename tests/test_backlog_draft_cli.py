import json
from pathlib import Path

from agentic_boilerplate.cli import main


def test_backlog_draft_generate_cli_saves_draft_and_reuses_po_blockers(tmp_path: Path, capsys) -> None:
    source_path = tmp_path / "approved-backlog-source.json"
    source_path.write_text(json.dumps(_source_with_missing_decision()), encoding="utf-8")
    inbox_root = tmp_path / "po-inbox"
    draft_root = tmp_path / "backlog-drafts"

    command = [
        "--inbox-root",
        str(inbox_root),
        "backlog-draft",
        "generate",
        "--input",
        str(source_path),
        "--backlog-draft-root",
        str(draft_root),
        "--created-at",
        "2026-08-10T12:00:00Z",
        "--jira-issue-key",
        "AGENT-640",
        "--project-id",
        "ap",
        "--project-name",
        "Airline Project",
        "--project-root",
        "/workspace/airline",
        "--repository",
        "example-org/airline",
        "--jira-project-key",
        "AP",
        "--json",
    ]

    first_result = main(command)
    first_payload = json.loads(capsys.readouterr().out)
    second_result = main(command)
    second_payload = json.loads(capsys.readouterr().out)

    assert first_result == 1
    assert second_result == 1
    assert first_payload["draft_key"] == "REQ-R1"
    assert first_payload["story_count"] == 2
    assert first_payload["dependency_count"] == 1
    assert first_payload["sprint_ring_count"] == 1
    assert first_payload["po_inbox_items"] == second_payload["po_inbox_items"]
    assert Path(first_payload["draft_path"]).is_file()
    assert first_payload["draft"]["sprint_rings"][0]["story_ids"] == ["STORY-1", "STORY-2"]
    inbox_item = json.loads(Path(first_payload["po_inbox_items"][0]["path"]).read_text(encoding="utf-8"))
    assert inbox_item["project_id"] == "ap"
    assert inbox_item["jira_issue_key"] == "AGENT-640"
    assert inbox_item["status"] == "open"


def test_backlog_draft_generate_cli_returns_success_without_po_blockers(tmp_path: Path, capsys) -> None:
    source = _source_with_missing_decision()
    source["missing_business_decisions"] = []
    source_path = tmp_path / "approved-backlog-source.json"
    source_path.write_text(json.dumps(source), encoding="utf-8")

    result = main(
        [
            "backlog-draft",
            "generate",
            "--input",
            str(source_path),
            "--backlog-draft-root",
            str(tmp_path / "backlog-drafts"),
            "--created-at",
            "2026-08-10T12:00:00Z",
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert result == 0
    assert payload["missing_business_decision_count"] == 0
    assert payload["po_inbox_items"] == []


def _source_with_missing_decision() -> dict:
    return {
        "key": "REQ-R1",
        "title": "Release 1 draft",
        "overview": "Create the initial release backlog from approved docs.",
        "epics": [
            {
                "id": "EPIC-PLANNING",
                "title": "Planning",
                "description": "Planning workflow.",
                "stories": [
                    {
                        "id": "STORY-1",
                        "title": "Generate draft",
                        "description": "Generate a local draft.",
                        "acceptance_criteria": ["Draft exists."],
                        "prerequisite_story_ids": [],
                        "complexity": "C2",
                        "complexity_rationale": "Structured transformation.",
                    },
                    {
                        "id": "STORY-2",
                        "title": "Approve draft",
                        "description": "Prepare draft for PO approval.",
                        "acceptance_criteria": ["Dependencies are preserved."],
                        "prerequisite_story_ids": ["STORY-1"],
                        "complexity": "C3",
                        "complexity_rationale": "Approval workflow touches Jira later.",
                    },
                ],
            }
        ],
        "sprint_rings": [
            {
                "id": "SPRINT-1",
                "name": "Planning setup",
                "goal": "Prepare the planning backlog slice.",
                "story_ids": ["STORY-1", "STORY-2"],
                "capacity_note": "Scope-first slice.",
            }
        ],
        "missing_business_decisions": [
            {
                "id": "DECISION-1",
                "title": "Confirm sprint scope",
                "question": "Should both stories be in one sprint?",
                "business_impact": "Sprint slicing changes worker order.",
                "recommendation": "Keep both in one planning sprint.",
                "affected_story_ids": ["STORY-1", "STORY-2"],
            }
        ],
    }
