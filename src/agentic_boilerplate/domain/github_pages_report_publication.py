"""GitHub Pages report publication planning."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


class ReportPublicationError(ValueError):
    """Raised when report publication input is invalid."""


class ReportArtifactType(str, Enum):
    TEST_EVIDENCE = "test_evidence"
    REGRESSION_EVIDENCE = "regression_evidence"
    REGRESSION_MANIFEST = "regression_manifest"
    SPRINT_RETRO = "sprint_retro"
    SPRINT_CLOSURE = "sprint_closure"
    RELEASE_NOTES = "release_notes"
    PARTNER_REPORT = "partner_report"


class ReportVisibility(str, Enum):
    PO_VISIBLE = "po_visible"
    PARTNER_REPORT = "partner_report"
    INTERNAL_ONLY = "internal_only"


@dataclass(frozen=True)
class ReportArtifact:
    title: str
    artifact_type: ReportArtifactType
    source_path: str
    visibility: ReportVisibility
    summary: str = ""
    jira_issue_key: str = ""
    github_pr_url: str = ""
    agiletest_key: str = ""
    release_id: str = ""
    sprint_id: str = ""


@dataclass(frozen=True)
class ReportPublicationInput:
    release_id: str
    sprint_id: str
    generated_at: str
    artifacts: tuple[ReportArtifact, ...]


@dataclass(frozen=True)
class PublishedReportPage:
    artifact_title: str
    artifact_type: ReportArtifactType
    visibility: ReportVisibility
    source_path: str
    docs_path: str
    jira_issue_key: str
    github_pr_url: str
    agiletest_key: str


@dataclass(frozen=True)
class ReportPublicationFailure:
    artifact_title: str
    source_path: str
    reason: str
    retry_record_path: str


@dataclass(frozen=True)
class ReportPublicationResult:
    release_id: str
    sprint_id: str
    generated_at: str
    index_path: str
    published_pages: tuple[PublishedReportPage, ...]
    skipped_internal_artifacts: tuple[str, ...]
    failures: tuple[ReportPublicationFailure, ...]

    @property
    def passed(self) -> bool:
        return not self.failures


SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)(api[_-]?token|github[_-]?token|jira[_-]?token|password|secret)\s*[:=]"),
    re.compile(r"(?i)(ghp|github_pat|sk-[A-Za-z0-9])"),
    re.compile(r"(?i)\.env"),
)


def report_publication_input_from_dict(payload: dict[str, Any]) -> ReportPublicationInput:
    """Build publication input from a JSON-compatible payload."""

    artifacts = tuple(_artifact_from_dict(item) for item in payload.get("artifacts", ()))
    if not artifacts:
        raise ReportPublicationError("At least one report artifact is required.")
    return ReportPublicationInput(
        release_id=_required_text(payload, "release_id"),
        sprint_id=_required_text(payload, "sprint_id"),
        generated_at=_required_text(payload, "generated_at"),
        artifacts=artifacts,
    )


def publish_report_artifacts_to_docs(
    publication_input: ReportPublicationInput,
    docs_root: str | Path,
    retry_root: str | Path,
    *,
    project_root: str | Path = ".",
) -> ReportPublicationResult:
    """Publish report summaries into the GitHub Pages docs tree.

    The publisher writes metadata and summaries only. Raw local evidence stays
    in durable storage and is referenced by path for worker context.
    """

    docs_path = Path(docs_root)
    retry_path = Path(retry_root)
    project_path = Path(project_root)
    report_root = docs_path / "reports" / _slug(publication_input.release_id) / _slug(publication_input.sprint_id)
    report_root.mkdir(parents=True, exist_ok=True)
    retry_path.mkdir(parents=True, exist_ok=True)

    published: list[PublishedReportPage] = []
    skipped: list[str] = []
    failures: list[ReportPublicationFailure] = []

    for artifact in publication_input.artifacts:
        failure_reason = _publication_failure_reason(artifact, project_path)
        if failure_reason:
            failures.append(_write_retry_record(artifact, publication_input, retry_path, failure_reason))
            continue
        if artifact.visibility == ReportVisibility.INTERNAL_ONLY:
            skipped.append(artifact.title)
            continue
        page_path = report_root / f"{_slug(artifact.title)}.md"
        page_path.write_text(_render_artifact_page(artifact, publication_input), encoding="utf-8")
        published.append(
            PublishedReportPage(
                artifact_title=artifact.title,
                artifact_type=artifact.artifact_type,
                visibility=artifact.visibility,
                source_path=artifact.source_path,
                docs_path=str(page_path),
                jira_issue_key=artifact.jira_issue_key,
                github_pr_url=artifact.github_pr_url,
                agiletest_key=artifact.agiletest_key,
            )
        )

    index_path = report_root / "index.md"
    index_path.write_text(_render_report_index(publication_input, published, skipped, failures), encoding="utf-8")
    return ReportPublicationResult(
        release_id=publication_input.release_id,
        sprint_id=publication_input.sprint_id,
        generated_at=publication_input.generated_at,
        index_path=str(index_path),
        published_pages=tuple(published),
        skipped_internal_artifacts=tuple(skipped),
        failures=tuple(failures),
    )


def report_publication_result_to_dict(result: ReportPublicationResult) -> dict[str, Any]:
    return {
        "release_id": result.release_id,
        "sprint_id": result.sprint_id,
        "generated_at": result.generated_at,
        "index_path": result.index_path,
        "passed": result.passed,
        "published_pages": [
            {
                "artifact_title": page.artifact_title,
                "artifact_type": page.artifact_type.value,
                "visibility": page.visibility.value,
                "source_path": page.source_path,
                "docs_path": page.docs_path,
                "jira_issue_key": page.jira_issue_key,
                "github_pr_url": page.github_pr_url,
                "agiletest_key": page.agiletest_key,
            }
            for page in result.published_pages
        ],
        "skipped_internal_artifacts": list(result.skipped_internal_artifacts),
        "failures": [
            {
                "artifact_title": failure.artifact_title,
                "source_path": failure.source_path,
                "reason": failure.reason,
                "retry_record_path": failure.retry_record_path,
            }
            for failure in result.failures
        ],
    }


def _artifact_from_dict(payload: dict[str, Any]) -> ReportArtifact:
    return ReportArtifact(
        title=_required_text(payload, "title"),
        artifact_type=ReportArtifactType(_required_text(payload, "artifact_type")),
        source_path=_required_text(payload, "source_path"),
        visibility=ReportVisibility(_required_text(payload, "visibility")),
        summary=str(payload.get("summary", "")).strip(),
        jira_issue_key=str(payload.get("jira_issue_key", "")).strip(),
        github_pr_url=str(payload.get("github_pr_url", "")).strip(),
        agiletest_key=str(payload.get("agiletest_key", "")).strip(),
        release_id=str(payload.get("release_id", "")).strip(),
        sprint_id=str(payload.get("sprint_id", "")).strip(),
    )


def _required_text(payload: dict[str, Any], field: str) -> str:
    value = str(payload.get(field, "")).strip()
    if not value:
        raise ReportPublicationError(f"{field} is required.")
    return value


def _publication_failure_reason(artifact: ReportArtifact, project_root: Path) -> str:
    source_path = Path(artifact.source_path)
    resolved = source_path if source_path.is_absolute() else project_root / source_path
    if not resolved.is_file():
        return "source_path does not exist or is not a file"
    summary = artifact.summary
    if _contains_secret_marker(summary):
        return "summary contains a secret marker and must be redacted before publication"
    if artifact.visibility == ReportVisibility.PARTNER_REPORT:
        source_text = resolved.read_text(encoding="utf-8", errors="replace")
        if _contains_secret_marker(source_text):
            return "partner-facing source artifact contains secret markers and needs redaction"
    return ""


def _contains_secret_marker(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def _write_retry_record(
    artifact: ReportArtifact,
    publication_input: ReportPublicationInput,
    retry_root: Path,
    reason: str,
) -> ReportPublicationFailure:
    path = retry_root / f"{_slug(publication_input.release_id)}-{_slug(publication_input.sprint_id)}-{_slug(artifact.title)}.json"
    path.write_text(
        json.dumps(
            {
                "release_id": publication_input.release_id,
                "sprint_id": publication_input.sprint_id,
                "generated_at": publication_input.generated_at,
                "artifact": {
                    "title": artifact.title,
                    "artifact_type": artifact.artifact_type.value,
                    "source_path": artifact.source_path,
                    "visibility": artifact.visibility.value,
                    "jira_issue_key": artifact.jira_issue_key,
                    "github_pr_url": artifact.github_pr_url,
                    "agiletest_key": artifact.agiletest_key,
                },
                "reason": reason,
                "next_action": "Redact or restore the source artifact, then retry publication.",
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return ReportPublicationFailure(
        artifact_title=artifact.title,
        source_path=artifact.source_path,
        reason=reason,
        retry_record_path=str(path),
    )


def _render_report_index(
    publication_input: ReportPublicationInput,
    published: list[PublishedReportPage],
    skipped: list[str],
    failures: list[ReportPublicationFailure],
) -> str:
    lines = [
        f"# Reports - {publication_input.release_id} - {publication_input.sprint_id}",
        "",
        f"Generated at: `{publication_input.generated_at}`",
        "",
        "## Published Reports",
        "",
    ]
    if published:
        for page in published:
            lines.append(
                f"- [{page.artifact_title}]({Path(page.docs_path).name}) - "
                f"{page.artifact_type.value}, visibility `{page.visibility.value}`, "
                f"source `{page.source_path}`"
            )
    else:
        lines.append("- No report pages were published.")
    lines.extend(["", "## Internal-Only Artifacts", ""])
    if skipped:
        lines.extend(f"- {title}" for title in skipped)
    else:
        lines.append("- None")
    lines.extend(["", "## Publication Failures", ""])
    if failures:
        for failure in failures:
            lines.append(f"- {failure.artifact_title}: {failure.reason}; retry `{failure.retry_record_path}`")
    else:
        lines.append("- None")
    return "\n".join(lines) + "\n"


def _render_artifact_page(artifact: ReportArtifact, publication_input: ReportPublicationInput) -> str:
    summary = artifact.summary or "No summary supplied. Use the local evidence path for worker context."
    fields = (
        ("Release", artifact.release_id or publication_input.release_id),
        ("Sprint", artifact.sprint_id or publication_input.sprint_id),
        ("Artifact type", artifact.artifact_type.value),
        ("Visibility", artifact.visibility.value),
        ("Local evidence path", artifact.source_path),
        ("Jira issue", artifact.jira_issue_key),
        ("GitHub PR", artifact.github_pr_url),
        ("AgileTest/Test reference", artifact.agiletest_key),
    )
    lines = [f"# {artifact.title}", "", "## Summary", "", _escape_summary(summary), "", "## References", ""]
    for label, value in fields:
        if value:
            lines.append(f"- {label}: `{value}`")
    lines.extend(
        [
            "",
            "## Publication Boundary",
            "",
            "This page publishes metadata and a curated summary only. Raw logs, secrets, role scratch notes, and unredacted partner data stay in local durable evidence unless the Product Owner explicitly approves publication.",
            "",
        ]
    )
    return "\n".join(lines)


def _escape_summary(summary: str) -> str:
    return summary.replace("\r\n", "\n").strip()


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-").lower()
    return slug or "report"
