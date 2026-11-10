import json
from pathlib import Path

from agentic_boilerplate.cli import main
from agentic_boilerplate.domain import (
    RequirementEpicInput,
    RequirementInput,
    RequirementStoryInput,
    backlog_draft_to_dict,
    create_backlog_draft,
)
from agentic_boilerplate.domain.story_complexity import ComplexityLevel


def test_backlog_draft_approval_cli_blocks_until_po_approval(tmp_path: Path, capsys) -> None:
    inbox_root = tmp_path / "po-inbox"
    draft_path = tmp_path / "draft.json"
    draft = create_backlog_draft(
        RequirementInput(
            key="REQ-APPROVAL-CLI",
            title="Approval CLI",
            overview="Require PO approval before Jira creation.",
            epics=(
                RequirementEpicInput(
                    id="EPIC-APPROVAL-CLI",
                    title="Approval CLI epic",
                    description="Approval CLI epic.",
                    stories=(
                        RequirementStoryInput(
                            id="STORY-APPROVAL-CLI",
                            title="Approve generated Jira story creation",
                            description="Create Jira issues only after approval.",
                            acceptance_criteria=("PO approval blocks Jira creation.",),
                            prerequisite_story_ids=(),
                            complexity=ComplexityLevel.C2,
                            complexity_rationale="One approval request and gate.",
                        ),
                    ),
                ),
            ),
        ),
        created_at="2026-08-10T12:00:00Z",
    )
    draft_path.write_text(json.dumps(backlog_draft_to_dict(draft)), encoding="utf-8")

    assert (
        main(
            [
                "--inbox-root",
                str(inbox_root),
                "backlog-draft",
                "request-approval",
                "--draft-path",
                str(draft_path),
                "--created-at",
                "2026-08-10T12:05:00Z",
                "--jira-issue-key",
                "AGENT-642",
                "--project-id",
                "ap",
                "--json",
            ]
        )
        == 0
    )
    approval_request = json.loads(capsys.readouterr().out)
    assert approval_request["approval_item_id"] == "REQ-APPROVAL-CLI-jira-creation-approval"
    assert approval_request["status"] == "open"

    assert (
        main(
            [
                "--inbox-root",
                str(inbox_root),
                "backlog-draft",
                "approval-gate",
                "--draft-path",
                str(draft_path),
                "--approval-item-id",
                "REQ-APPROVAL-CLI-jira-creation-approval",
                "--json",
            ]
        )
        == 1
    )
    waiting = json.loads(capsys.readouterr().out)
    assert waiting["status"] == "waiting"
    assert waiting["can_create_jira"] is False

    assert (
        main(
            [
                "--inbox-root",
                str(inbox_root),
                "po-inbox",
                "approve",
                "REQ-APPROVAL-CLI-jira-creation-approval",
                "--answer",
                "Product Owner approved.",
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert (
        main(
            [
                "--inbox-root",
                str(inbox_root),
                "backlog-draft",
                "approval-gate",
                "--draft-path",
                str(draft_path),
                "--approval-item-id",
                "REQ-APPROVAL-CLI-jira-creation-approval",
                "--json",
            ]
        )
        == 0
    )
    approved = json.loads(capsys.readouterr().out)
    assert approved["status"] == "approved"
    assert approved["can_create_jira"] is True
    assert approved["approved_by"] == "Product Owner approved."
