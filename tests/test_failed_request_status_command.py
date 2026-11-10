import json
from pathlib import Path

from agentic_boilerplate.cli import main
from agentic_boilerplate.domain import (
    AgentRole,
    CodexFailedRequestArtifact,
    CodexPauseReason,
    CodexResumeAction,
)
from agentic_boilerplate.storage import FileCodexPauseStore


def test_worker_failed_requests_cli_lists_retry_metadata(tmp_path: Path, capsys) -> None:
    store_root = tmp_path / "codex-jobs"
    FileCodexPauseStore(store_root).create_failed_request(_failed_request())

    result = main(
        [
            "--env-file",
            str(tmp_path / "missing.env"),
            "worker",
            "failed-requests",
            "--codex-jobs-root",
            str(store_root),
        ]
    )

    output = capsys.readouterr().out
    assert result == 0
    assert "id\tjira_issue_key\trole\treason\tnext_action\tretry_policy" in output
    assert "failed-request-001\tAGENT-626\tdeveloper\texecution_failed\tmanual_review" in output
    assert "stage-2" in output
    assert "AGENT-626:codex-job-626:stage-2" in output
    assert "developer_manual_recovery" in output


def test_worker_failed_requests_cli_json_is_ui_consumable(tmp_path: Path, capsys) -> None:
    store_root = tmp_path / "codex-jobs"
    FileCodexPauseStore(store_root).create_failed_request(_failed_request())

    result = main(
        [
            "--env-file",
            str(tmp_path / "missing.env"),
            "worker",
            "failed-requests",
            "--codex-jobs-root",
            str(store_root),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    item = payload["items"][0]
    assert result == 0
    assert item["id"] == "failed-request-001"
    assert item["jira_issue_key"] == "AGENT-626"
    assert item["stage_id"] == "stage-2"
    assert item["retry_policy"] == "manual_review_before_retry"
    assert item["replay_guard_key"] == "AGENT-626:codex-job-626:stage-2"
    assert item["suggested_next_role_action"] == "developer_manual_recovery"


def test_worker_failed_requests_cli_reports_empty_state(tmp_path: Path, capsys) -> None:
    result = main(
        [
            "--env-file",
            str(tmp_path / "missing.env"),
            "worker",
            "failed-requests",
            "--codex-jobs-root",
            str(tmp_path / "codex-jobs"),
        ]
    )

    assert result == 0
    assert capsys.readouterr().out == "No failed Codex requests found.\n"


def _failed_request() -> CodexFailedRequestArtifact:
    return CodexFailedRequestArtifact(
        id="failed-request-001",
        codex_job_id="codex-job-626",
        jira_issue_key="AGENT-626",
        worker_role=AgentRole.DEVELOPER,
        reason=CodexPauseReason.EXECUTION_FAILED,
        failed_at="2026-08-09T20:30:00Z",
        request_summary="Redacted failed request.",
        error_summary="Executor failed.",
        next_action=CodexResumeAction.MANUAL_REVIEW,
        stage_id="stage-2",
        stdout_snippet="partial output",
        stderr_snippet="stderr output",
        retry_policy="manual_review_before_retry",
        suggested_next_role_action="developer_manual_recovery",
        side_effect_idempotency_key="AGENT-626:codex-job-626:stage-2",
    )
