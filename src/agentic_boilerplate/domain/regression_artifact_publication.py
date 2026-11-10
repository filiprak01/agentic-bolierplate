"""Regression artifact publication orchestration from manifest data."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from agentic_boilerplate.domain.agiletest_test_execution_upsert import (
    AgileTestTestExecutionUpsertPlan,
)
from agentic_boilerplate.domain.evidence_publication import (
    EvidenceAttachmentPlan,
    EvidenceCommentPlan,
    EvidenceLinkPlan,
    EvidencePublicationMode,
    EvidencePublicationRequest,
    build_agiletest_evidence_link_plans,
    build_evidence_attachment_plan,
    build_evidence_comment_plan,
    build_evidence_publication_request,
)
from agentic_boilerplate.domain.regression_manifest import RegressionManifest


class RegressionArtifactPublicationError(ValueError):
    """Raised when regression artifact publication input is invalid."""


class PublicationReadinessWarningType(str, Enum):
    """Warnings emitted when publication inputs are incomplete."""

    MISSING_OVERVIEW_TASK = "missing-overview-task"
    MISSING_TEST_EXECUTION_REFERENCE = "missing-test-execution-reference"
    MISSING_INCLUDED_TEST_CASES = "missing-included-test-cases"
    MISSING_EVIDENCE_PATH = "missing-evidence-path"
    MISSING_FOCUSED_RESULT_SUMMARY = "missing-focused-result-summary"
    MISSING_FULL_RESULT_SUMMARY = "missing-full-result-summary"


@dataclass(frozen=True)
class PublicationReadinessWarning:
    """One warning describing missing or incomplete publication inputs."""

    warning_type: PublicationReadinessWarningType
    message: str


@dataclass(frozen=True)
class RegressionArtifactPublicationRequest:
    """Inputs required to prepare a publishable regression artifact bundle."""

    manifest: RegressionManifest
    evidence_path: str
    focused_result_summary: str
    full_result_summary: str
    mode: EvidencePublicationMode = EvidencePublicationMode.DRY_RUN
    test_execution_upsert_plan: AgileTestTestExecutionUpsertPlan | None = None
    include_attachments: bool = True


@dataclass(frozen=True)
class RegressionArtifactPublicationBundle:
    """Dry-run or live-ready publication bundle for regression artifacts."""

    manifest_key: str
    overview_task_key: str
    test_execution_key: str
    included_test_case_keys: tuple[str, ...]
    evidence_path: str
    focused_result_summary: str
    full_result_summary: str
    mode: EvidencePublicationMode
    publication_request: EvidencePublicationRequest | None
    warnings: tuple[PublicationReadinessWarning, ...] = ()

    @property
    def ready_for_publication(self) -> bool:
        return self.publication_request is not None and not self.warnings


def build_regression_artifact_publication_bundle(
    request: RegressionArtifactPublicationRequest,
) -> RegressionArtifactPublicationBundle:
    """Compose a manifest and helper outputs into one publication bundle."""

    _validate_request(request)
    manifest = request.manifest
    overview_task_key = manifest.references.overview_task_key.strip()
    test_execution_key = _resolve_test_execution_key(
        manifest=manifest,
        test_execution_upsert_plan=request.test_execution_upsert_plan,
    )
    included_test_case_keys = tuple(record.test_case_key for record in manifest.records)

    warnings: list[PublicationReadinessWarning] = []
    if not overview_task_key:
        warnings.append(
            PublicationReadinessWarning(
                warning_type=PublicationReadinessWarningType.MISSING_OVERVIEW_TASK,
                message="Regression manifest does not include an overview Task reference.",
            )
        )
    if not test_execution_key:
        warnings.append(
            PublicationReadinessWarning(
                warning_type=PublicationReadinessWarningType.MISSING_TEST_EXECUTION_REFERENCE,
                message="No AgileTest Test Execution key or upsert plan was provided.",
            )
        )
    if not included_test_case_keys:
        warnings.append(
            PublicationReadinessWarning(
                warning_type=PublicationReadinessWarningType.MISSING_INCLUDED_TEST_CASES,
                message="Manifest records do not include reusable Test Cases for publication.",
            )
        )
    if not request.evidence_path.strip():
        warnings.append(
            PublicationReadinessWarning(
                warning_type=PublicationReadinessWarningType.MISSING_EVIDENCE_PATH,
                message="A durable regression evidence path is required for comments and attachments.",
            )
        )
    if not request.focused_result_summary.strip():
        warnings.append(
            PublicationReadinessWarning(
                warning_type=PublicationReadinessWarningType.MISSING_FOCUSED_RESULT_SUMMARY,
                message="Focused regression result summary was not provided.",
            )
        )
    if not request.full_result_summary.strip():
        warnings.append(
            PublicationReadinessWarning(
                warning_type=PublicationReadinessWarningType.MISSING_FULL_RESULT_SUMMARY,
                message="Full-suite result summary was not provided.",
            )
        )

    comments = _build_comment_plans(
        manifest=manifest,
        overview_task_key=overview_task_key,
        test_execution_key=test_execution_key,
        evidence_path=request.evidence_path.strip(),
        focused_result_summary=request.focused_result_summary.strip() or "Focused result summary not provided.",
        full_result_summary=request.full_result_summary.strip() or "Full-suite result summary not provided.",
    )
    attachments = _build_attachment_plans(
        overview_task_key=overview_task_key,
        test_execution_key=test_execution_key,
        evidence_path=request.evidence_path.strip(),
        include_attachments=request.include_attachments,
    )
    links = _build_link_plans(
        overview_task_key=overview_task_key,
        test_execution_key=test_execution_key,
        included_test_case_keys=included_test_case_keys,
        test_execution_upsert_plan=request.test_execution_upsert_plan,
    )

    publication_request: EvidencePublicationRequest | None = None
    if comments or attachments or links:
        publication_request = build_evidence_publication_request(
            evidence_path=request.evidence_path.strip() or _fallback_evidence_path(manifest),
            mode=request.mode,
            comments=comments,
            attachments=attachments,
            links=links,
        )

    return RegressionArtifactPublicationBundle(
        manifest_key=manifest.manifest_key,
        overview_task_key=overview_task_key,
        test_execution_key=test_execution_key,
        included_test_case_keys=included_test_case_keys,
        evidence_path=request.evidence_path.strip(),
        focused_result_summary=request.focused_result_summary.strip(),
        full_result_summary=request.full_result_summary.strip(),
        mode=request.mode,
        publication_request=publication_request,
        warnings=tuple(warnings),
    )


def render_regression_artifact_publication_bundle(
    bundle: RegressionArtifactPublicationBundle,
) -> str:
    """Render a PO-readable dry-run summary of the publication bundle."""

    _validate_bundle(bundle)
    lines = [
        f"# Regression Artifact Publication - {bundle.manifest_key}",
        "",
        f"- Overview Task: {bundle.overview_task_key or 'missing'}",
        f"- Test Execution: {bundle.test_execution_key or 'missing'}",
        f"- Evidence path: {bundle.evidence_path or 'missing'}",
        f"- Focused result summary: {bundle.focused_result_summary or 'missing'}",
        f"- Full-suite result summary: {bundle.full_result_summary or 'missing'}",
        f"- Mode: {bundle.mode.value}",
        "",
        "## Included Test Cases",
    ]
    lines.extend(
        f"- {test_case_key}" for test_case_key in bundle.included_test_case_keys
    ) if bundle.included_test_case_keys else lines.append("- None")

    lines.extend(["", "## Planned Publication Actions"])
    if bundle.publication_request is None:
        lines.append("- No publication request could be built.")
    else:
        for comment in bundle.publication_request.comments:
            lines.append(f"- Comment -> {comment.issue_key}")
        for attachment in bundle.publication_request.attachments:
            lines.append(f"- Attachment -> {attachment.issue_key}")
        for link in bundle.publication_request.links:
            lines.append(
                f"- Link -> {link.source_issue_key} -> {link.target_issue_key} ({link.link_type})"
            )

    lines.extend(["", "## Warnings"])
    lines.extend(f"- {warning.message}" for warning in bundle.warnings) if bundle.warnings else lines.append("- None")
    return "\n".join(lines)


def _build_comment_plans(
    *,
    manifest: RegressionManifest,
    overview_task_key: str,
    test_execution_key: str,
    evidence_path: str,
    focused_result_summary: str,
    full_result_summary: str,
) -> tuple[EvidenceCommentPlan, ...]:
    if not evidence_path:
        return ()
    detail_lines = [
        f"Manifest: {manifest.manifest_key}",
        f"Release: {manifest.release_key}",
        f"Source sprint: {manifest.source_sprint}",
        f"Focused result: {focused_result_summary}",
        f"Full suite result: {full_result_summary}",
        f"Included Test Cases: {', '.join(record.test_case_key for record in manifest.records) or 'none'}",
        f"AgileTest Execution: {test_execution_key or 'not set'}",
    ]
    comments: list[EvidenceCommentPlan] = []
    if overview_task_key:
        comments.append(
            build_evidence_comment_plan(
                issue_key=overview_task_key,
                evidence_path=evidence_path,
                result_summary=f"Regression artifact publication prepared for {manifest.manifest_key}.",
                details="\n".join(detail_lines),
            )
        )
    if test_execution_key:
        comments.append(
            build_evidence_comment_plan(
                issue_key=test_execution_key,
                evidence_path=evidence_path,
                result_summary=f"Regression execution publication prepared for {manifest.manifest_key}.",
                details="\n".join(detail_lines),
            )
        )
    return tuple(comments)


def _build_attachment_plans(
    *,
    overview_task_key: str,
    test_execution_key: str,
    evidence_path: str,
    include_attachments: bool,
) -> tuple[EvidenceAttachmentPlan, ...]:
    if not include_attachments or not evidence_path:
        return ()
    attachments: list[EvidenceAttachmentPlan] = []
    if overview_task_key:
        attachments.append(
            build_evidence_attachment_plan(
                issue_key=overview_task_key,
                evidence_path=evidence_path,
            )
        )
    if test_execution_key:
        attachments.append(
            build_evidence_attachment_plan(
                issue_key=test_execution_key,
                evidence_path=evidence_path,
            )
        )
    return tuple(attachments)


def _build_link_plans(
    *,
    overview_task_key: str,
    test_execution_key: str,
    included_test_case_keys: tuple[str, ...],
    test_execution_upsert_plan: AgileTestTestExecutionUpsertPlan | None,
) -> tuple[EvidenceLinkPlan, ...]:
    if test_execution_upsert_plan is not None:
        return test_execution_upsert_plan.publication_request.links
    if not overview_task_key or not test_execution_key or not included_test_case_keys:
        return ()
    return build_agiletest_evidence_link_plans(
        overview_task_key=overview_task_key,
        test_execution_key=test_execution_key,
        test_case_keys=included_test_case_keys,
    )


def _resolve_test_execution_key(
    *,
    manifest: RegressionManifest,
    test_execution_upsert_plan: AgileTestTestExecutionUpsertPlan | None,
) -> str:
    if test_execution_upsert_plan is not None:
        return test_execution_upsert_plan.execution_issue_key
    return manifest.references.agiletest_execution_key.strip()


def _fallback_evidence_path(manifest: RegressionManifest) -> str:
    if not manifest.records:
        return "missing-evidence-path"
    return manifest.records[0].evidence_path


def _validate_request(request: RegressionArtifactPublicationRequest) -> None:
    if not isinstance(request.mode, EvidencePublicationMode):
        raise RegressionArtifactPublicationError("mode must be EvidencePublicationMode")
    _require_text("manifest.manifest_key", request.manifest.manifest_key)
    _require_text("manifest.release_key", request.manifest.release_key)
    _require_text("manifest.source_sprint", request.manifest.source_sprint)


def _validate_bundle(bundle: RegressionArtifactPublicationBundle) -> None:
    _require_text("manifest_key", bundle.manifest_key)
    if not isinstance(bundle.mode, EvidencePublicationMode):
        raise RegressionArtifactPublicationError("mode must be EvidencePublicationMode")


def _require_text(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RegressionArtifactPublicationError(f"{name} is required")
    return value.strip()
