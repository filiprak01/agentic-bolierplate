import json
from dataclasses import replace
from pathlib import Path

from agentic_boilerplate.cli import main
from agentic_boilerplate.domain import AgentRole
from agentic_boilerplate.domain.agent_assignment import (
    AgentAssignment,
    AssignmentPaths,
    AssignmentStatus,
)
from agentic_boilerplate.storage import FileAgentAssignmentStore, FilePOInboxStore


def test_worker_po_inbox_pause_and_resume_requeues_assignment(tmp_path: Path, capsys) -> None:
    inbox_root = tmp_path / "po-inbox"
    agent_state = tmp_path / "agent-state"
    store = FileAgentAssignmentStore(agent_state)
    store.create_assignment(_assignment())

    pause_result = main(
        [
            "--env-file",
            str(tmp_path / "missing.env"),
            "--inbox-root",
            str(inbox_root),
            "worker",
            "pause-for-po",
            "--assignment-store-root",
            str(agent_state),
            "--assignment-id",
            "assignment-AGENT-628",
            "--worker-id",
            "developer-1",
            "--project-id",
            "AP",
            "--question",
            "Which retry behavior should the worker use?",
            "--response-needed",
            "Select retry or no retry before continuing implementation.",
            "--resume-context",
            "Continue from assignment context pack after the answer is recorded.",
            "--paused-at",
            "2026-08-09T20:00:00Z",
            "--json",
        ]
    )
    pause_payload = json.loads(capsys.readouterr().out)
    paused = store.read_assignment("assignment-AGENT-628")
    inbox_item = FilePOInboxStore(inbox_root).read("po-blocker-assignment-AGENT-628")

    assert pause_result == 0
    assert pause_payload["status"] == "paused_po"
    assert paused.status is AssignmentStatus.PAUSED_PO
    assert paused.po_inbox_item_id == "po-blocker-assignment-AGENT-628"
    assert Path(paused.paths.po_inbox_resume_context_path).is_file()
    assert inbox_item.status.value == "open"
    assert "Project: AP" in inbox_item.message
    assert "Assignment: assignment-AGENT-628" in inbox_item.message
    assert "Role: developer" in inbox_item.message

    assert (
        main(
            [
                "--env-file",
                str(tmp_path / "missing.env"),
                "--inbox-root",
                str(inbox_root),
                "po-inbox",
                "answer",
                "po-blocker-assignment-AGENT-628",
                "--answer",
                "Use one retry and keep the failure visible in evidence.",
            ]
        )
        == 0
    )
    capsys.readouterr()

    resume_result = main(
        [
            "--env-file",
            str(tmp_path / "missing.env"),
            "--inbox-root",
            str(inbox_root),
            "worker",
            "resume-po-inbox",
            "--assignment-store-root",
            str(agent_state),
            "--eligible-issue-key",
            "AGENT-628",
            "--resumed-at",
            "2026-08-09T20:15:00Z",
            "--json",
        ]
    )
    resume_payload = json.loads(capsys.readouterr().out)
    resumed = store.read_assignment("assignment-AGENT-628")

    assert resume_result == 0
    assert resume_payload["resumed_assignment_ids"] == ["assignment-AGENT-628"]
    assert resume_payload["resume_requests"][0]["action"] == "po_resume_instruction"
    assert resume_payload["resume_requests"][0]["original_stop_reason"].startswith("PO input required")
    assert resumed.status is AssignmentStatus.QUEUED
    assert resumed.worker_id == ""
    assert resumed.po_inbox_item_id == "po-blocker-assignment-AGENT-628"


def test_worker_po_inbox_resume_keeps_open_or_ineligible_assignment_paused(
    tmp_path: Path,
    capsys,
) -> None:
    inbox_root = tmp_path / "po-inbox"
    agent_state = tmp_path / "agent-state"
    store = FileAgentAssignmentStore(agent_state)
    store.create_assignment(_assignment())
    assert (
        main(
            [
                "--env-file",
                str(tmp_path / "missing.env"),
                "--inbox-root",
                str(inbox_root),
                "worker",
                "pause-for-po",
                "--assignment-store-root",
                str(agent_state),
                "--assignment-id",
                "assignment-AGENT-628",
                "--worker-id",
                "developer-1",
                "--project-id",
                "AP",
                "--question",
                "Confirm deployment target?",
                "--response-needed",
                "PO must confirm target before continuing.",
                "--resume-context",
                "Resume after deployment target is confirmed.",
                "--paused-at",
                "2026-08-09T20:00:00Z",
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert (
        main(
            [
                "--env-file",
                str(tmp_path / "missing.env"),
                "--inbox-root",
                str(inbox_root),
                "worker",
                "resume-po-inbox",
                "--assignment-store-root",
                str(agent_state),
                "--eligible-issue-key",
                "AGENT-628",
                "--json",
            ]
        )
        == 0
    )
    open_payload = json.loads(capsys.readouterr().out)
    assert open_payload["skips"][0]["reason"] == "po_inbox_item_open"
    assert store.read_assignment("assignment-AGENT-628").status is AssignmentStatus.PAUSED_PO

    assert (
        main(
            [
                "--env-file",
                str(tmp_path / "missing.env"),
                "--inbox-root",
                str(inbox_root),
                "po-inbox",
                "answer",
                "po-blocker-assignment-AGENT-628",
                "--answer",
                "Use staging first.",
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert (
        main(
            [
                "--env-file",
                str(tmp_path / "missing.env"),
                "--inbox-root",
                str(inbox_root),
                "worker",
                "resume-po-inbox",
                "--assignment-store-root",
                str(agent_state),
                "--eligible-issue-key",
                "AGENT-999",
                "--json",
            ]
        )
        == 0
    )
    ineligible_payload = json.loads(capsys.readouterr().out)
    assert ineligible_payload["skips"][0]["reason"] == "normal_gates_not_eligible"
    assert store.read_assignment("assignment-AGENT-628").status is AssignmentStatus.PAUSED_PO


def test_worker_po_inbox_resume_keeps_rejected_decision_paused(tmp_path: Path, capsys) -> None:
    inbox_root = tmp_path / "po-inbox"
    agent_state = tmp_path / "agent-state"
    store = FileAgentAssignmentStore(agent_state)
    resume_context_path = agent_state / "po-inbox-resume-contexts" / "assignment-AGENT-628.json"
    resume_context_path.parent.mkdir(parents=True)
    resume_context_path.write_text("{}", encoding="utf-8")
    store.create_assignment(
        replace(
            _assignment(),
            status=AssignmentStatus.PAUSED_PO,
            worker_id="developer-1",
            pause_reason="PO input required: approve the changed scope.",
            po_inbox_item_id="approval-assignment-AGENT-628",
            paths=AssignmentPaths(
                context_pack_path="data/context-packs/AGENT-628/context.json",
                codex_job_path="data/codex-jobs/AGENT-628/job.json",
                output_path="data/codex-results/AGENT-628/result.json",
                po_inbox_resume_context_path=str(resume_context_path),
            ),
        )
    )
    assert (
        main(
            [
                "--env-file",
                str(tmp_path / "missing.env"),
                "--inbox-root",
                str(inbox_root),
                "po-inbox",
                "create",
                "--id",
                "approval-assignment-AGENT-628",
                "--type",
                "approval_request",
                "--title",
                "Approve changed scope",
                "--message",
                "Should the worker continue with changed scope?",
                "--business-impact",
                "Controls whether implementation continues.",
                "--recommendation",
                "Reject and create follow-up if scope changed.",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert (
        main(
            [
                "--env-file",
                str(tmp_path / "missing.env"),
                "--inbox-root",
                str(inbox_root),
                "po-inbox",
                "reject",
                "approval-assignment-AGENT-628",
                "--answer",
                "Changed scope needs a new story.",
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert (
        main(
            [
                "--env-file",
                str(tmp_path / "missing.env"),
                "--inbox-root",
                str(inbox_root),
                "worker",
                "resume-po-inbox",
                "--assignment-store-root",
                str(agent_state),
                "--eligible-issue-key",
                "AGENT-628",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["skips"][0]["reason"] == "po_inbox_item_rejected"
    assert "Product Planning or Architecture follow-up" in payload["skips"][0]["next_action"]
    assert store.read_assignment("assignment-AGENT-628").status is AssignmentStatus.PAUSED_PO


def _assignment() -> AgentAssignment:
    return AgentAssignment(
        id="assignment-AGENT-628",
        jira_issue_key="AGENT-628",
        role=AgentRole.DEVELOPER,
        status=AssignmentStatus.QUEUED,
        paths=AssignmentPaths(
            context_pack_path="data/context-packs/AGENT-628/context.json",
            codex_job_path="data/codex-jobs/AGENT-628/job.json",
            output_path="data/codex-results/AGENT-628/result.json",
        ),
        branch_name="feature/AGENT-628-po-inbox-pause-resume",
        created_at="2026-08-09T19:50:00Z",
        updated_at="2026-08-09T19:50:00Z",
    )
