import json
from pathlib import Path

from agentic_boilerplate.cli import main
from agentic_boilerplate.domain import (
    GitHubPagesReportArtifact,
    GitHubPagesReportArtifactType,
    GitHubPagesReportPublicationInput,
    GitHubPagesReportVisibility,
    publish_report_artifacts_to_docs,
    report_publication_input_from_dict,
    report_publication_result_to_dict,
)


def test_publish_report_artifacts_writes_metadata_pages_and_keeps_local_evidence_paths(tmp_path: Path) -> None:
    source = tmp_path / "data" / "agent-logs" / "AGENT-698" / "test-evidence.md"
    source.parent.mkdir(parents=True)
    source.write_text("Focused tests passed.", encoding="utf-8")

    result = publish_report_artifacts_to_docs(
        GitHubPagesReportPublicationInput(
            release_id="1.2.0",
            sprint_id="R1.2 S5",
            generated_at="2026-08-10T13:30:00Z",
            artifacts=(
                    GitHubPagesReportArtifact(
                        title="AGENT-698 GitHub Pages deployment evidence",
                        artifact_type=GitHubPagesReportArtifactType.TEST_EVIDENCE,
                    source_path="data/agent-logs/AGENT-698/test-evidence.md",
                    visibility=GitHubPagesReportVisibility.PO_VISIBLE,
                    summary="Post-merge validation passed for the deployment workflow.",
                    jira_issue_key="AGENT-698",
                    github_pr_url="https://github.com/example-org/agentic-boilerplate/pull/191",
                    agiletest_key="AGENT-914",
                ),
            ),
        ),
        docs_root=tmp_path / "docs",
        retry_root=tmp_path / "data" / "publication-retries",
        project_root=tmp_path,
    )

    assert result.passed
    assert len(result.published_pages) == 1
    page_path = Path(result.published_pages[0].docs_path)
    page = page_path.read_text(encoding="utf-8")
    assert "AGENT-698" in page
    assert "https://github.com/example-org/agentic-boilerplate/pull/191" in page
    assert "AGENT-914" in page
    assert "data/agent-logs/AGENT-698/test-evidence.md" in page
    assert "Raw logs, secrets" in page
    assert Path(result.index_path).is_file()


def test_publish_report_artifacts_skips_internal_and_records_retry_failures(tmp_path: Path) -> None:
    internal = tmp_path / "data" / "agent-logs" / "AGENT-1" / "internal.md"
    internal.parent.mkdir(parents=True)
    internal.write_text("internal detail", encoding="utf-8")
    partner = tmp_path / "data" / "agent-logs" / "AGENT-2" / "partner.md"
    partner.parent.mkdir(parents=True)
    partner.write_text("GITHUB_TOKEN=secret", encoding="utf-8")

    result = publish_report_artifacts_to_docs(
        GitHubPagesReportPublicationInput(
            release_id="1.2.0",
            sprint_id="R1.2 S5",
            generated_at="2026-08-10T13:30:00Z",
            artifacts=(
                GitHubPagesReportArtifact(
                    title="Internal role note",
                    artifact_type=GitHubPagesReportArtifactType.SPRINT_RETRO,
                    source_path="data/agent-logs/AGENT-1/internal.md",
                    visibility=GitHubPagesReportVisibility.INTERNAL_ONLY,
                ),
                GitHubPagesReportArtifact(
                    title="Partner report with token",
                    artifact_type=GitHubPagesReportArtifactType.PARTNER_REPORT,
                    source_path="data/agent-logs/AGENT-2/partner.md",
                    visibility=GitHubPagesReportVisibility.PARTNER_REPORT,
                    summary="Partner summary",
                ),
            ),
        ),
        docs_root=tmp_path / "docs",
        retry_root=tmp_path / "data" / "publication-retries",
        project_root=tmp_path,
    )

    assert not result.passed
    assert result.skipped_internal_artifacts == ("Internal role note",)
    assert len(result.failures) == 1
    retry_path = Path(result.failures[0].retry_record_path)
    retry = json.loads(retry_path.read_text(encoding="utf-8"))
    assert retry["reason"] == "partner-facing source artifact contains secret markers and needs redaction"
    assert retry["next_action"] == "Redact or restore the source artifact, then retry publication."
    assert "Internal role note" in Path(result.index_path).read_text(encoding="utf-8")


def test_report_publication_input_from_dict_and_result_payload(tmp_path: Path) -> None:
    source = tmp_path / "evidence.md"
    source.write_text("safe evidence", encoding="utf-8")
    payload = {
        "release_id": "1.2.0",
        "sprint_id": "R1.2 S5",
        "generated_at": "2026-08-10T13:30:00Z",
        "artifacts": [
            {
                "title": "Regression summary",
                "artifact_type": "regression_evidence",
                "source_path": str(source),
                "visibility": "po_visible",
                "summary": "Regression passed.",
                "jira_issue_key": "AGENT-656",
            }
        ],
    }

    publication_input = report_publication_input_from_dict(payload)
    result = publish_report_artifacts_to_docs(
        publication_input,
        docs_root=tmp_path / "docs",
        retry_root=tmp_path / "retries",
        project_root=tmp_path,
    )
    result_payload = report_publication_result_to_dict(result)

    assert result_payload["passed"] is True
    assert result_payload["published_pages"][0]["jira_issue_key"] == "AGENT-656"
    assert result_payload["published_pages"][0]["artifact_type"] == "regression_evidence"


def test_docs_site_publish_reports_cli_writes_pages_and_json(tmp_path: Path, capsys) -> None:
    source = tmp_path / "data" / "agent-logs" / "AGENT-698" / "test-evidence.md"
    source.parent.mkdir(parents=True)
    source.write_text("safe evidence", encoding="utf-8")
    input_path = tmp_path / "publication.json"
    input_path.write_text(
        json.dumps(
            {
                "release_id": "1.2.0",
                "sprint_id": "R1.2 S5",
                "generated_at": "2026-08-10T13:30:00Z",
                "artifacts": [
                    {
                        "title": "AGENT-698 GitHub Pages deployment evidence",
                        "artifact_type": "test_evidence",
                        "source_path": "data/agent-logs/AGENT-698/test-evidence.md",
                        "visibility": "po_visible",
                        "summary": "Validation passed.",
                        "jira_issue_key": "AGENT-698",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "docs-site",
                "publish-reports",
                "--input",
                str(input_path),
                "--docs-root",
                str(tmp_path / "docs"),
                "--retry-root",
                str(tmp_path / "data" / "publication-retries"),
                "--project-root",
                str(tmp_path),
                "--json",
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert '"passed": true' in output
    assert "AGENT-698 GitHub Pages deployment evidence" in output
