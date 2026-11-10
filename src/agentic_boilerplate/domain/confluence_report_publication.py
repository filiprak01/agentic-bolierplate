"""Confluence report publication workflow for evidence and sprint artifacts."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from html import escape
from pathlib import Path
from typing import Any

from agentic_boilerplate.domain.evidence_publication import EvidenceCommentPlan, build_evidence_comment_plan
from agentic_boilerplate.integrations import (
    ConfluenceDocumentationAdapter,
    ConfluenceMirrorRecord,
    ConfluencePage,
    ConfluencePageFields,
)


class ReportArtifactType(str, Enum):
    """Supported report artifact classes for Confluence publication."""

    STORY_TEST_EVIDENCE = "story-test-evidence"
    REGRESSION_REPORT = "regression-report"
    REGRESSION_MANIFEST = "regression-manifest"
    SPRINT_RETRO = "sprint-retro"
    SPRINT_CLOSURE = "sprint-closure"
    POST_MORTEM = "post-mortem"
    PARTNER_SUMMARY = "partner-summary"


class ReportAudience(str, Enum):
    """Audience level used for partner-safe filtering."""

    INTERNAL_ONLY = "internal-only"
    SHARED = "shared"
    PARTNER_SAFE = "partner-safe"


@dataclass(frozen=True)
class ReportArtifact:
    """One local artifact prepared for Confluence publication."""

    title: str
    local_path: str
    artifact_type: ReportArtifactType
    summary: str = ""
    jira_issue_keys: tuple[str, ...] = ()
    github_pull_request_urls: tuple[str, ...] = ()
    audience: ReportAudience = ReportAudience.SHARED
    role_specific_notes: tuple[str, ...] = ()
    raw_debug_log_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConfluenceReportPublicationPlan:
    """Publication plan for one Confluence report page."""

    publication_issue_key: str
    page_title: str
    summary: str
    artifacts: tuple[ReportArtifact, ...]
    partner_safe: bool = False
    related_jira_issue_keys: tuple[str, ...] = ()
    parent_page_id: str = ""


@dataclass(frozen=True)
class ConfluenceReportPublicationResult:
    """Durable publication result for Jira comments and local metadata."""

    publication_issue_key: str
    page_id: str
    page_title: str
    page_url: str
    mirror_path: str
    partner_safe: bool
    published_artifact_paths: tuple[str, ...]
    jira_comment_plans: tuple[EvidenceCommentPlan, ...]


@dataclass(frozen=True)
class ConfluenceReportPublicationIssue:
    """Validation issue for report publication input."""

    field: str
    message: str


class ConfluenceReportPublicationError(ValueError):
    """Raised when a report publication plan is invalid."""

    def __init__(self, issues: Sequence[ConfluenceReportPublicationIssue]) -> None:
        self.issues = tuple(issues)
        super().__init__(format_confluence_report_publication_issues(self.issues))


def classify_report_artifact_type(*, local_path: str, title: str = "") -> ReportArtifactType:
    """Classify a report artifact from its path or title."""

    haystack = f"{local_path} {title}".lower()
    if "post-mortem" in haystack or "post_mortem" in haystack:
        return ReportArtifactType.POST_MORTEM
    if "partner" in haystack or "client" in haystack:
        return ReportArtifactType.PARTNER_SUMMARY
    if "manifest" in haystack:
        return ReportArtifactType.REGRESSION_MANIFEST
    if "regression" in haystack:
        return ReportArtifactType.REGRESSION_REPORT
    if "closure" in haystack:
        return ReportArtifactType.SPRINT_CLOSURE
    if "retro" in haystack:
        return ReportArtifactType.SPRINT_RETRO
    return ReportArtifactType.STORY_TEST_EVIDENCE


def build_report_artifact(
    *,
    title: str,
    local_path: str,
    artifact_type: ReportArtifactType | None = None,
    summary: str = "",
    jira_issue_keys: tuple[str, ...] = (),
    github_pull_request_urls: tuple[str, ...] = (),
    audience: ReportAudience = ReportAudience.SHARED,
    role_specific_notes: tuple[str, ...] = (),
    raw_debug_log_paths: tuple[str, ...] = (),
) -> ReportArtifact:
    """Build a classified report artifact."""

    return ReportArtifact(
        title=title.strip(),
        local_path=local_path.strip(),
        artifact_type=artifact_type or classify_report_artifact_type(local_path=local_path, title=title),
        summary=summary.strip(),
        jira_issue_keys=tuple(key.strip() for key in jira_issue_keys if key.strip()),
        github_pull_request_urls=tuple(url.strip() for url in github_pull_request_urls if url.strip()),
        audience=audience,
        role_specific_notes=tuple(note.strip() for note in role_specific_notes if note.strip()),
        raw_debug_log_paths=tuple(path.strip() for path in raw_debug_log_paths if path.strip()),
    )


def validate_confluence_report_publication_plan(
    plan: ConfluenceReportPublicationPlan,
) -> list[ConfluenceReportPublicationIssue]:
    """Return plan validation issues."""

    issues: list[ConfluenceReportPublicationIssue] = []
    _require_text(issues, "publication_issue_key", plan.publication_issue_key)
    _require_text(issues, "page_title", plan.page_title)
    _require_text(issues, "summary", plan.summary)
    if not plan.artifacts:
        issues.append(ConfluenceReportPublicationIssue("artifacts", "At least one report artifact is required."))
    for index, artifact in enumerate(plan.artifacts):
        _require_text(issues, f"artifacts[{index}].title", artifact.title)
        _require_text(issues, f"artifacts[{index}].local_path", artifact.local_path)
    return issues


def require_valid_confluence_report_publication_plan(
    plan: ConfluenceReportPublicationPlan,
) -> ConfluenceReportPublicationPlan:
    """Raise when a report publication plan is incomplete."""

    issues = validate_confluence_report_publication_plan(plan)
    if issues:
        raise ConfluenceReportPublicationError(issues)
    return plan


def build_confluence_report_page_fields(plan: ConfluenceReportPublicationPlan) -> ConfluencePageFields:
    """Build Confluence page fields from a validated plan."""

    require_valid_confluence_report_publication_plan(plan)
    return ConfluencePageFields(
        title=plan.page_title,
        body_storage=render_confluence_report_body(plan),
        parent_page_id=plan.parent_page_id,
    )


def execute_confluence_report_publication(
    adapter: ConfluenceDocumentationAdapter,
    plan: ConfluenceReportPublicationPlan,
    *,
    mirror_root: Path,
) -> ConfluenceReportPublicationResult:
    """Publish or update one Confluence report page and mirror it locally."""

    fields = build_confluence_report_page_fields(plan)
    page = adapter.create_or_update_child_page(fields)
    mirror = adapter.mirror_page(page, mirror_root)
    return confluence_report_publication_result(plan, page, mirror)


def confluence_report_publication_result(
    plan: ConfluenceReportPublicationPlan,
    page: ConfluencePage,
    mirror: ConfluenceMirrorRecord,
) -> ConfluenceReportPublicationResult:
    """Build a durable publication result with Jira comment plans."""

    comment_targets = dict.fromkeys((plan.publication_issue_key, *plan.related_jira_issue_keys))
    comment_plans = tuple(
        build_evidence_comment_plan(
            issue_key=issue_key,
            evidence_path=str(mirror.path),
            result_summary=f"Confluence report published: {page.web_url}",
            details=(
                f"Confluence page: {page.title}\n"
                f"Published artifact paths: {', '.join(artifact.local_path for artifact in plan.artifacts)}"
            ),
        )
        for issue_key in comment_targets
        if issue_key.strip()
    )
    return ConfluenceReportPublicationResult(
        publication_issue_key=plan.publication_issue_key,
        page_id=page.id,
        page_title=page.title,
        page_url=page.web_url,
        mirror_path=str(mirror.path),
        partner_safe=plan.partner_safe,
        published_artifact_paths=tuple(artifact.local_path for artifact in _included_artifacts(plan)),
        jira_comment_plans=comment_plans,
    )


def confluence_report_publication_result_to_dict(
    result: ConfluenceReportPublicationResult,
) -> dict[str, Any]:
    """Convert a publication result into JSON-compatible data."""

    return {
        "publication_issue_key": result.publication_issue_key,
        "page_id": result.page_id,
        "page_title": result.page_title,
        "page_url": result.page_url,
        "mirror_path": result.mirror_path,
        "partner_safe": result.partner_safe,
        "published_artifact_paths": list(result.published_artifact_paths),
        "jira_comment_plans": [
            {
                "issue_key": plan.issue_key,
                "evidence_path": plan.evidence_path,
                "body": plan.body,
            }
            for plan in result.jira_comment_plans
        ],
    }


def render_confluence_report_body(plan: ConfluenceReportPublicationPlan) -> str:
    """Render Confluence storage-format HTML for a report page."""

    require_valid_confluence_report_publication_plan(plan)
    lines = [f"<p>{escape(plan.summary)}</p>"]
    if plan.related_jira_issue_keys:
        lines.extend(["<h2>Related Jira</h2>", "<ul>"])
        for key in plan.related_jira_issue_keys:
            lines.append(f"<li>{escape(key)}</li>")
        lines.append("</ul>")
    lines.append("<h2>Artifacts</h2>")
    for artifact in _included_artifacts(plan):
        lines.extend(
            [
                f"<h3>{escape(artifact.title)}</h3>",
                "<ul>",
                f"<li>Type: {escape(artifact.artifact_type.value)}</li>",
                f"<li>Local path: {escape(artifact.local_path)}</li>",
            ]
        )
        if artifact.jira_issue_keys:
            lines.append(
                f"<li>Jira issues: {escape(', '.join(artifact.jira_issue_keys))}</li>"
            )
        if artifact.github_pull_request_urls:
            link_markup = ", ".join(_link(url) for url in artifact.github_pull_request_urls)
            lines.append(f"<li>GitHub PRs: {link_markup}</li>")
        lines.append("</ul>")
        if artifact.summary:
            lines.append(f"<p>{escape(artifact.summary)}</p>")
        if artifact.role_specific_notes and not plan.partner_safe:
            lines.extend(["<p>Role-specific notes:</p>", "<ul>"])
            for note in artifact.role_specific_notes:
                lines.append(f"<li>{escape(note)}</li>")
            lines.append("</ul>")
        if artifact.raw_debug_log_paths and not plan.partner_safe:
            lines.extend(["<p>Raw debug logs:</p>", "<ul>"])
            for path in artifact.raw_debug_log_paths:
                lines.append(f"<li>{escape(path)}</li>")
            lines.append("</ul>")
    return "\n".join(lines)


def format_confluence_report_publication_issues(
    issues: Sequence[ConfluenceReportPublicationIssue],
) -> str:
    return "; ".join(f"{issue.field}: {issue.message}" for issue in issues)


def _included_artifacts(plan: ConfluenceReportPublicationPlan) -> tuple[ReportArtifact, ...]:
    if not plan.partner_safe:
        return plan.artifacts
    return tuple(
        artifact for artifact in plan.artifacts if artifact.audience is not ReportAudience.INTERNAL_ONLY
    )


def _link(url: str) -> str:
    escaped = escape(url)
    return f'<a href="{escaped}">{escaped}</a>'


def _require_text(
    issues: list[ConfluenceReportPublicationIssue],
    field: str,
    value: str,
) -> None:
    if not value.strip():
        issues.append(ConfluenceReportPublicationIssue(field=field, message="Value is required."))
