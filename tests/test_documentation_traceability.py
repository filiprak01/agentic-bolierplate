from pathlib import Path

from agentic_boilerplate.domain.documentation_traceability import (
    DocumentationTraceabilityAuditConfig,
    DocumentationTraceabilityClassification,
    DocumentationTraceabilityIssue,
    DocumentationTraceabilityProject,
    TraceabilityFollowUpPolicy,
    audit_documentation_traceability,
    build_traceability_follow_up_plan,
    documentation_traceability_report_from_dict,
    documentation_traceability_report_to_dict,
)
from agentic_boilerplate.domain.po_inbox import InboxMessageType
from agentic_boilerplate.storage.documentation_traceability import FileDocumentationTraceabilityReportStore


def test_traceability_audit_extracts_commitments_and_classifies_rows(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs"
    mirror_root = tmp_path / "confluence-mirror"
    docs_root.mkdir()
    mirror_root.mkdir()
    (docs_root / "roadmap.md").write_text(
        """# Roadmap

## Operator UI

- MUST add multi-project inbox dashboard for Product Owner visibility.
- [doc-only] Keep AI role notes optimized for worker context.
- [deferred] Add managed cloud autoscaling after local Docker workers.
- [rejected] Replace Jira with email approvals.
- Decide with PO whether client reports need a branded export?
- Implement GitHub Pages reports for clients. AGENT-700
""",
        encoding="utf-8",
    )
    (mirror_root / "release-plan.md").write_text(
        """# Release Plan

## Integrations

- REQUIRED AgileTest regression execution summary for release closure.
""",
        encoding="utf-8",
    )
    issues = (
        DocumentationTraceabilityIssue(
            key="AGENT-700",
            summary="Implement GitHub Pages reports for clients",
            issue_type="Story",
            status="FUNNEL",
            labels=("github-pages",),
        ),
    )

    report = audit_documentation_traceability(
        DocumentationTraceabilityAuditConfig(
            report_id="traceability-r12-s7",
            created_at="2026-08-13T15:00:00Z",
            project=DocumentationTraceabilityProject(
                project_id="AGENT",
                project_name="Agentic Boilerplate",
                jira_project_key="AGENT",
                docs_roots=(str(docs_root),),
                confluence_mirror_roots=(str(mirror_root),),
                release_target="1.2.0",
            ),
        ),
        jira_issues=issues,
    )

    classifications = {row.commitment.text: row.classification for row in report.rows}

    assert classifications["MUST add multi-project inbox dashboard for Product Owner visibility."] == (
        DocumentationTraceabilityClassification.MISSING_JIRA_REFLECTION
    )
    assert classifications["[doc-only] Keep AI role notes optimized for worker context."] == (
        DocumentationTraceabilityClassification.COVERED_BY_DOC_ONLY
    )
    assert classifications["[deferred] Add managed cloud autoscaling after local Docker workers."] == (
        DocumentationTraceabilityClassification.DEFERRED_ROADMAP
    )
    assert classifications["[rejected] Replace Jira with email approvals."] == (
        DocumentationTraceabilityClassification.REJECTED
    )
    assert classifications["Decide with PO whether client reports need a branded export?"] == (
        DocumentationTraceabilityClassification.NEEDS_PO_DECISION
    )
    covered = classifications["Implement GitHub Pages reports for clients. AGENT-700"]
    assert covered == DocumentationTraceabilityClassification.COVERED_BY_JIRA

    confluence_row = next(row for row in report.rows if row.source.source_type == "confluence_mirror")
    assert confluence_row.project_id == "AGENT"
    assert confluence_row.jira_project_key == "AGENT"
    assert confluence_row.release_target == "1.2.0"
    assert confluence_row.source.heading == "Integrations"
    assert confluence_row.source.line >= 5

    summary = report.summary
    assert summary["covered-by-jira"] == 1
    assert summary["covered-by-doc-only"] == 1
    assert summary["deferred-roadmap"] == 1
    assert summary["rejected"] == 1
    assert summary["needs-po-decision"] == 1
    assert summary["missing-jira-reflection"] == 2


def test_traceability_audit_matches_by_issue_metadata_and_detects_duplicates(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs"
    docs_root.mkdir()
    (docs_root / "planning.md").write_text(
        """# Planning

## Capacity

- MUST add sprint capacity notes before release planning. AGENT-701
- MUST add sprint capacity notes before release planning. AGENT-701
- REQUIRED security review checklist for high-risk projects.
""",
        encoding="utf-8",
    )
    issues = (
        DocumentationTraceabilityIssue(
            key="AGENT-701",
            summary="Security review checklist for high risk projects",
            issue_type="Story",
            status="READY TO START",
            labels=("documentation-traceability",),
            description="Source: planning.md:7",
        ),
    )

    report = audit_documentation_traceability(
        DocumentationTraceabilityAuditConfig(
            report_id="traceability-duplicates",
            created_at="2026-08-13T15:10:00Z",
            project=DocumentationTraceabilityProject(
                project_id="AGENT",
                project_name="Agentic Boilerplate",
                jira_project_key="AGENT",
                docs_roots=(str(docs_root),),
                release_target="1.2.0",
            ),
        ),
        jira_issues=issues,
    )

    first_capacity, duplicate_capacity = [
        row for row in report.rows if "sprint capacity notes" in row.commitment.text
    ]
    assert first_capacity.classification == DocumentationTraceabilityClassification.COVERED_BY_JIRA
    assert first_capacity.matched_jira_keys == ("AGENT-701",)
    assert duplicate_capacity.classification == DocumentationTraceabilityClassification.DUPLICATE
    assert duplicate_capacity.duplicate_of_commitment_id == first_capacity.commitment.id

    security = next(row for row in report.rows if "security review checklist" in row.commitment.text)
    assert security.classification == DocumentationTraceabilityClassification.COVERED_BY_JIRA
    assert security.match_reasons


def test_missing_commitments_create_candidates_or_po_questions_by_policy(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs"
    docs_root.mkdir()
    (docs_root / "improvements.md").write_text(
        """# Improvements

- MUST add deterministic agent communication replay.
""",
        encoding="utf-8",
    )
    report = audit_documentation_traceability(
        DocumentationTraceabilityAuditConfig(
            report_id="traceability-followups",
            created_at="2026-08-13T15:20:00Z",
            project=DocumentationTraceabilityProject(
                project_id="AP",
                project_name="Airline POC",
                jira_project_key="AP",
                docs_roots=(str(docs_root),),
                release_target="R1",
            ),
        ),
        jira_issues=(),
    )

    draft_plan = build_traceability_follow_up_plan(
        report,
        policy=TraceabilityFollowUpPolicy.DRAFT_BACKLOG_CANDIDATE,
        created_at="2026-08-13T15:21:00Z",
    )
    po_plan = build_traceability_follow_up_plan(
        report,
        policy=TraceabilityFollowUpPolicy.PO_INBOX_QUESTION,
        created_at="2026-08-13T15:22:00Z",
    )
    report_only_plan = build_traceability_follow_up_plan(
        report,
        policy=TraceabilityFollowUpPolicy.REPORT_ONLY,
        created_at="2026-08-13T15:23:00Z",
    )

    assert draft_plan.draft_candidates[0].target_status == "FUNNEL"
    assert draft_plan.draft_candidates[0].project_id == "AP"
    assert draft_plan.draft_candidates[0].release_target == "R1"
    assert draft_plan.po_inbox_questions == ()

    assert po_plan.draft_candidates == ()
    assert po_plan.po_inbox_questions[0].message_type == InboxMessageType.BLOCKING_QUESTION
    assert po_plan.po_inbox_questions[0].project_id == "AP"
    assert po_plan.po_inbox_questions[0].jira_project_key == "AP"

    assert report_only_plan.draft_candidates == ()
    assert report_only_plan.po_inbox_questions == ()


def test_traceability_report_round_trips_and_persists(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs"
    docs_root.mkdir()
    (docs_root / "process.md").write_text(
        """# Process

- MUST keep every implementation change traceable to Jira.
""",
        encoding="utf-8",
    )
    report = audit_documentation_traceability(
        DocumentationTraceabilityAuditConfig(
            report_id="traceability-roundtrip",
            created_at="2026-08-13T15:30:00Z",
            project=DocumentationTraceabilityProject(
                project_id="AGENT",
                project_name="Agentic Boilerplate",
                jira_project_key="AGENT",
                docs_roots=(str(docs_root),),
                release_target="1.2.0",
            ),
        ),
        jira_issues=(),
    )

    payload = documentation_traceability_report_to_dict(report)
    restored = documentation_traceability_report_from_dict(payload)
    store = FileDocumentationTraceabilityReportStore(tmp_path / "reports")
    location = store.save(restored)

    assert location.report_id == "traceability-roundtrip"
    assert location.path.is_file()
    assert store.read("traceability-roundtrip").rows[0].commitment.text == (
        "MUST keep every implementation change traceable to Jira."
    )


def test_traceability_symbols_are_available_from_package_boundaries() -> None:
    import agentic_boilerplate.domain as domain
    import agentic_boilerplate.storage as storage

    assert domain.DocumentationTraceabilityAuditConfig is DocumentationTraceabilityAuditConfig
    assert domain.audit_documentation_traceability is audit_documentation_traceability
    assert storage.FileDocumentationTraceabilityReportStore is FileDocumentationTraceabilityReportStore


def test_agent_process_docs_reference_traceability_audit() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    traceability_doc = "docs/documentation-to-backlog-traceability-audit.md"

    required_files = (
        "docs/reference/platform-agent-instructions.md",
        "ai_agents/roles/product_planning.md",
        "ai_agents/roles/docs_confluence.md",
        "ai_agents/roles/orchestrator.md",
        "ai_agents/roles/release_manager.md",
        "docs/backlog-draft-workflow.md",
        "docs/context-pack-generator.md",
        "docs/documentation-governance.md",
        "docs/index.md",
        "docs/jira-story-creation-workflow.md",
        "docs/release-scope-model.md",
        "docs/retro-follow-up-roadmap.md",
    )

    for relative_path in required_files:
        content = (repo_root / relative_path).read_text(encoding="utf-8")
        expected_reference = (
            "documentation-to-backlog-traceability-audit.md"
            if relative_path == "docs/index.md"
            else traceability_doc
        )
        assert expected_reference in content, relative_path

    audit_doc = (repo_root / traceability_doc).read_text(encoding="utf-8")
    for required_term in (
        "covered-by-jira",
        "covered-by-doc-only",
        "deferred-roadmap",
        "rejected",
        "needs-po-decision",
        "missing-jira-reflection",
        "without live external calls",
    ):
        assert required_term in audit_doc
