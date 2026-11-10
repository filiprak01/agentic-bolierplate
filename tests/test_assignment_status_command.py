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
from agentic_boilerplate.domain.assignment_status import (
    assignment_status_item_to_dict,
    build_assignment_status_items,
)
from agentic_boilerplate.storage import FileAgentAssignmentStore


def test_assignment_status_items_include_paused_and_blocked_actions() -> None:
    items = build_assignment_status_items(
        (_paused_assignment(), _po_paused_assignment(), _blocked_assignment(), _queued_assignment())
    )

    assert [item.category for item in items] == ["blocked", "blocked", "paused"]
    assert items[0].jira_issue_key == "AGENT-502"
    assert items[0].status == "failed"
    assert items[0].recommended_next_action == (
        "Finish or unblock the prerequisite Jira issue, then rerun assignment eligibility."
    )
    assert items[1].jira_issue_key == "AGENT-504"
    assert items[1].status == "paused_po"
    assert items[1].reason.startswith("blocked-by-PO-inbox")
    assert items[1].po_inbox_item_id == "po-blocker-po-paused-assignment"
    assert items[1].recommended_next_action == "Answer the durable PO inbox question, then rerun the worker assignment."
    assert items[2].jira_issue_key == "AGENT-501"
    assert items[2].status == "paused_limit"
    assert items[2].recommended_next_action == (
        "Record updated Codex limit availability, then rerun or resume the worker assignment."
    )
    assert "queued-assignment" not in json.dumps([assignment_status_item_to_dict(item) for item in items])


def test_assignment_status_items_include_project_identity() -> None:
    assignment = replace(
        _paused_assignment(),
        project_id="AP",
        project_name="Airline POC",
        repository="example-org/airline-poc",
        jira_project_key="AP",
    )

    (item,) = build_assignment_status_items((assignment,))
    payload = assignment_status_item_to_dict(item)

    assert payload["project_id"] == "AP"
    assert payload["project_name"] == "Airline POC"
    assert payload["repository"] == "example-org/airline-poc"
    assert payload["jira_project_key"] == "AP"


def test_assignment_status_items_redact_secret_like_free_text() -> None:
    assignment = replace(
        _blocked_assignment(),
        failure_reason="dependency blocked; token=super-secret-value was attached by mistake",
    )

    (item,) = build_assignment_status_items((assignment,))

    payload = assignment_status_item_to_dict(item)
    assert payload["reason"] == "[redacted]"
    assert "super-secret-value" not in json.dumps(payload)


def test_worker_status_cli_lists_paused_and_blocked_assignments(tmp_path: Path, capsys) -> None:
    store_root = tmp_path / "agent-state"
    store = FileAgentAssignmentStore(store_root)
    store.create_assignment(_paused_assignment())
    store.create_assignment(_blocked_assignment())
    store.create_assignment(_queued_assignment())

    result = main(
        [
            "--env-file",
            str(tmp_path / "missing.env"),
            "worker",
            "status",
            "--assignment-store-root",
            str(store_root),
        ]
    )

    output = capsys.readouterr().out
    assert result == 0
    assert "assignment_id\tjira_issue_key\trole\tstatus\tcategory\treason\trecommended_next_action" in output
    assert "blocked-assignment\tAGENT-502\tdeveloper\tfailed\tblocked" in output
    assert "paused-assignment\tAGENT-501\tdeveloper\tpaused_limit\tpaused" in output
    assert "queued-assignment" not in output


def test_worker_status_cli_can_filter_by_project_id(tmp_path: Path, capsys) -> None:
    store_root = tmp_path / "agent-state"
    store = FileAgentAssignmentStore(store_root)
    store.create_assignment(replace(_paused_assignment(), project_id="AP"))
    store.create_assignment(replace(_blocked_assignment(), project_id="AGENT"))

    result = main(
        [
            "--env-file",
            str(tmp_path / "missing.env"),
            "worker",
            "status",
            "--assignment-store-root",
            str(store_root),
            "--project-id",
            "AP",
        ]
    )

    output = capsys.readouterr().out
    assert result == 0
    assert "paused-assignment\tAGENT-501\tdeveloper\tpaused_limit\tpaused" in output
    assert output.rstrip().endswith("\tAP")
    assert "blocked-assignment" not in output


def test_worker_status_cli_json_is_ui_consumable(tmp_path: Path, capsys) -> None:
    store_root = tmp_path / "agent-state"
    store = FileAgentAssignmentStore(store_root)
    store.create_assignment(_paused_assignment())
    store.create_assignment(_blocked_assignment())

    result = main(
        [
            "--env-file",
            str(tmp_path / "missing.env"),
            "worker",
            "status",
            "--assignment-store-root",
            str(store_root),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert result == 0
    assert [item["category"] for item in payload["items"]] == ["blocked", "paused"]
    assert payload["items"][0]["recommended_next_action"]
    assert payload["items"][1]["codex_job_id"] == "codex-job-AGENT-501"


def test_worker_status_cli_reports_no_paused_or_blocked_assignments(tmp_path: Path, capsys) -> None:
    store_root = tmp_path / "agent-state"
    FileAgentAssignmentStore(store_root).create_assignment(_queued_assignment())

    result = main(
        [
            "--env-file",
            str(tmp_path / "missing.env"),
            "worker",
            "status",
            "--assignment-store-root",
            str(store_root),
        ]
    )

    assert result == 0
    assert capsys.readouterr().out == "No paused or blocked assignments.\n"


def _assignment(issue_key: str, *, assignment_id: str) -> AgentAssignment:
    return AgentAssignment(
        id=assignment_id,
        jira_issue_key=issue_key,
        role=AgentRole.DEVELOPER,
        status=AssignmentStatus.QUEUED,
        paths=AssignmentPaths(
            context_pack_path=f"data/context-packs/{issue_key}/context.json",
            codex_job_path=f"data/codex-jobs/{issue_key}/job.json",
            output_path=f"data/codex-results/{issue_key}/result.json",
        ),
        branch_name=f"feature/{issue_key}-assignment-status",
        created_at="2026-07-14T18:00:00Z",
        updated_at="2026-07-14T18:00:00Z",
    )


def _paused_assignment() -> AgentAssignment:
    return replace(
        _assignment("AGENT-501", assignment_id="paused-assignment"),
        status=AssignmentStatus.PAUSED_LIMIT,
        worker_id="developer-1",
        codex_job_id="codex-job-AGENT-501",
        pause_reason="5-hour Codex limit below threshold",
        paths=AssignmentPaths(
            context_pack_path="data/context-packs/AGENT-501/context.json",
            codex_job_path="data/codex-jobs/AGENT-501/job.json",
            output_path="data/codex-results/AGENT-501/result.json",
            failed_request_path="data/codex-jobs/AGENT-501/failed-request.json",
        ),
    )


def _blocked_assignment() -> AgentAssignment:
    return replace(
        _assignment("AGENT-502", assignment_id="blocked-assignment"),
        status=AssignmentStatus.FAILED,
        failure_reason="dependency blocked by AGENT-501",
        attempt_count=2,
    )


def _po_paused_assignment() -> AgentAssignment:
    return replace(
        _assignment("AGENT-504", assignment_id="po-paused-assignment"),
        status=AssignmentStatus.PAUSED_PO,
        worker_id="developer-1",
        pause_reason="PO input required: confirm API retry policy",
        po_inbox_item_id="po-blocker-po-paused-assignment",
        paths=AssignmentPaths(
            context_pack_path="data/context-packs/AGENT-504/context.json",
            codex_job_path="data/codex-jobs/AGENT-504/job.json",
            output_path="data/codex-results/AGENT-504/result.json",
            po_inbox_resume_context_path="data/agent-state/po-inbox-resume-contexts/po-paused-assignment.json",
        ),
    )


def _queued_assignment() -> AgentAssignment:
    return _assignment("AGENT-503", assignment_id="queued-assignment")
