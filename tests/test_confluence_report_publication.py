from pathlib import Path

from agentic_boilerplate.domain import (
    ConfluenceReportPublicationPlan,
    ReportAudience,
    ReportArtifactType,
    build_confluence_report_page_fields,
    build_report_artifact,
    classify_report_artifact_type,
    execute_confluence_report_publication,
)
from agentic_boilerplate.integrations import (
    ConfluenceAdapterConfig,
    MockConfluenceDocumentationAdapter,
)
from agentic_boilerplate.storage import FileConfluenceReportPublicationStore


def test_artifact_type_classifier_detects_supported_report_classes() -> None:
    assert classify_report_artifact_type(local_path="data/agent-logs/AGENT-8/test-evidence.md") is ReportArtifactType.STORY_TEST_EVIDENCE
    assert classify_report_artifact_type(local_path="data/agent-logs/REGRESSION-S11/regression-manifest.md") is ReportArtifactType.REGRESSION_MANIFEST
    assert classify_report_artifact_type(local_path="data/agent-logs/SPRINT-11/sprint-11-retro.md") is ReportArtifactType.SPRINT_RETRO
    assert classify_report_artifact_type(local_path="reports/partner-summary.md") is ReportArtifactType.PARTNER_SUMMARY


def test_partner_safe_page_excludes_internal_only_and_raw_debug_sections() -> None:
    plan = ConfluenceReportPublicationPlan(
        publication_issue_key="AGENT-201",
        page_title="Sprint 11 Publication",
        summary="Publish sprint reports to Confluence.",
        partner_safe=True,
        artifacts=(
            build_report_artifact(
                title="Regression report",
                local_path="data/agent-logs/REGRESSION-S11/regression-evidence.md",
                summary="Behavioral regression passed.",
                jira_issue_keys=("AGENT-244",),
                github_pull_request_urls=("https://github.com/example-org/agentic-boilerplate/pull/65",),
                raw_debug_log_paths=("logs/internal-debug.log",),
            ),
            build_report_artifact(
                title="Internal note",
                local_path="data/agent-logs/SPRINT-11/internal-note.md",
                audience=ReportAudience.INTERNAL_ONLY,
                role_specific_notes=("Escalation detail",),
            ),
        ),
    )

    body = build_confluence_report_page_fields(plan).body_storage

    assert "Regression report" in body
    assert "internal-debug.log" not in body
    assert "Internal note" not in body


def test_execute_publication_returns_page_url_mirror_and_jira_comment_plans(tmp_path: Path) -> None:
    adapter = MockConfluenceDocumentationAdapter(
        ConfluenceAdapterConfig(
            base_url="https://example.atlassian.net/wiki",
            space_key="DOCS",
            parent_page_id="12345",
        )
    )
    plan = ConfluenceReportPublicationPlan(
        publication_issue_key="AGENT-201",
        page_title="Sprint 11 Publication",
        summary="Publish sprint reports to Confluence.",
        related_jira_issue_keys=("AGENT-244",),
        artifacts=(
            build_report_artifact(
                title="Sprint retro",
                local_path="data/agent-logs/SPRINT-11/sprint-11-retro.md",
                jira_issue_keys=("AGENT-245",),
            ),
        ),
    )

    result = execute_confluence_report_publication(adapter, plan, mirror_root=tmp_path)
    location = FileConfluenceReportPublicationStore(tmp_path / "results").write(result)

    assert result.page_url.endswith("/Sprint 11 Publication")
    assert result.mirror_path.endswith(".md")
    assert [comment.issue_key for comment in result.jira_comment_plans] == ["AGENT-201", "AGENT-244"]
    assert location.path.name == "confluence-report-publication.json"
    assert "Sprint 11 Publication" in location.path.read_text(encoding="utf-8")
