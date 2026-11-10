import json
from pathlib import Path

from agentic_boilerplate.cli import main


def test_docs_traceability_audit_cli_writes_report_and_candidates(tmp_path: Path, capsys) -> None:
    docs_root = tmp_path / "docs"
    mirror_root = tmp_path / "confluence"
    report_root = tmp_path / "traceability-reports"
    docs_root.mkdir()
    mirror_root.mkdir()
    (docs_root / "roadmap.md").write_text(
        """# Roadmap

## Agent Communication

- MUST add visual agent communication replay.
- Implement existing GitHub Pages publication. AGENT-700
""",
        encoding="utf-8",
    )
    (mirror_root / "operator.md").write_text(
        """# Operator

- [doc-only] Keep setup notes optimized for worker context.
""",
        encoding="utf-8",
    )
    jira_issues_json = tmp_path / "jira-issues.json"
    jira_issues_json.write_text(
        json.dumps(
            [
                {
                    "key": "AGENT-700",
                    "summary": "Implement existing GitHub Pages publication",
                    "issue_type": "Story",
                    "status": "FUNNEL",
                    "labels": ["github-pages"],
                    "description": "Source: docs/roadmap.md#agent-communication",
                }
            ]
        ),
        encoding="utf-8",
    )

    result = main(
        [
            "docs-traceability",
            "audit",
            "--docs-root",
            str(docs_root),
            "--confluence-mirror-root",
            str(mirror_root),
            "--jira-issues-json",
            str(jira_issues_json),
            "--report-root",
            str(report_root),
            "--report-id",
            "traceability-cli",
            "--created-at",
            "2026-08-13T15:40:00Z",
            "--project-id",
            "AGENT",
            "--project-name",
            "Agentic Boilerplate",
            "--jira-project-key",
            "AGENT",
            "--release-target",
            "1.2.0",
            "--follow-up-policy",
            "draft-backlog-candidate",
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert result == 1
    assert payload["report_id"] == "traceability-cli"
    assert Path(payload["report_path"]).is_file()
    assert payload["summary"]["covered-by-jira"] == 1
    assert payload["summary"]["covered-by-doc-only"] == 1
    assert payload["summary"]["missing-jira-reflection"] == 1
    assert payload["follow_up_policy"] == "draft-backlog-candidate"
    assert payload["draft_candidates"][0]["target_status"] == "FUNNEL"
    assert payload["po_inbox_items"] == []


def test_docs_traceability_audit_cli_can_route_missing_items_to_po_inbox(tmp_path: Path, capsys) -> None:
    docs_root = tmp_path / "docs"
    inbox_root = tmp_path / "po-inbox"
    docs_root.mkdir()
    (docs_root / "improvements.md").write_text(
        """# Improvements

- MUST add release readiness audit before deployment.
""",
        encoding="utf-8",
    )
    jira_issues_json = tmp_path / "jira-issues.json"
    jira_issues_json.write_text("[]", encoding="utf-8")

    result = main(
        [
            "--inbox-root",
            str(inbox_root),
            "docs-traceability",
            "audit",
            "--docs-root",
            str(docs_root),
            "--jira-issues-json",
            str(jira_issues_json),
            "--report-root",
            str(tmp_path / "reports"),
            "--report-id",
            "traceability-po",
            "--created-at",
            "2026-08-13T15:45:00Z",
            "--project-id",
            "AP",
            "--project-name",
            "Airline POC",
            "--jira-project-key",
            "AP",
            "--release-target",
            "R1",
            "--follow-up-policy",
            "po-inbox-question",
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert result == 1
    assert payload["po_inbox_items"][0]["status"] == "open"
    inbox_file = Path(payload["po_inbox_items"][0]["path"])
    assert inbox_file.is_file()
    inbox_payload = json.loads(inbox_file.read_text(encoding="utf-8"))
    assert inbox_payload["project_id"] == "AP"
    assert inbox_payload["jira_project_key"] == "AP"
