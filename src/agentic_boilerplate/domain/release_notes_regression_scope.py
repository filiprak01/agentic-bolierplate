"""Release notes and regression scope draft planning."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from pathlib import PurePosixPath

from agentic_boilerplate.domain.regression_classification import (
    AgileTestMappingPlan,
    ClassifiedTestIssue,
)
from agentic_boilerplate.domain.tester_manual_test_workflow import RegressionClassification


class ReleaseDraftError(ValueError):
    """Raised when release draft input is incomplete."""


class ReleaseDraftStatus(str, Enum):
    """Product Owner review status for release draft artifacts."""

    DRAFT = "draft"
    PO_APPROVED = "po-approved"
    CHANGES_REQUESTED = "changes-requested"


@dataclass(frozen=True)
class ReleaseDraftWorkItem:
    """Story or bug included in release notes."""

    key: str
    title: str
    issue_type: str
    status: str
    pull_requests: tuple[str, ...] = ()
    test_issue_keys: tuple[str, ...] = ()
    linked_bug_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReleaseKnownLimitation:
    """Known limitation that Product Owner should review before release."""

    summary: str
    impact: str
    workaround: str = ""
    linked_issue_key: str = ""


@dataclass(frozen=True)
class RegressionScopeBucket:
    """Grouped Test issues for one regression classification."""

    classification: RegressionClassification
    test_issue_keys: tuple[str, ...]


@dataclass(frozen=True)
class ReleaseNotesDraft:
    """Release notes draft prepared for local storage and Confluence sync."""

    release_key: str
    release_version: str
    title: str
    generated_at: str
    included_items: tuple[ReleaseDraftWorkItem, ...]
    known_limitations: tuple[ReleaseKnownLimitation, ...] = ()
    status: ReleaseDraftStatus = ReleaseDraftStatus.DRAFT
    confluence_ready: bool = True


@dataclass(frozen=True)
class RegressionScopeDraft:
    """Regression scope draft grouped by Test issue classifications."""

    release_key: str
    release_version: str
    generated_at: str
    classified_tests: tuple[ClassifiedTestIssue, ...]
    changed_areas: tuple[str, ...]
    agiletest_mapping_plan: AgileTestMappingPlan | None = None
    status: ReleaseDraftStatus = ReleaseDraftStatus.DRAFT
    confluence_ready: bool = True

    @property
    def buckets(self) -> tuple[RegressionScopeBucket, ...]:
        """Return Test issues grouped into stable regression classification buckets."""

        return regression_scope_buckets(self.classified_tests)


@dataclass(frozen=True)
class ReleaseDraftPaths:
    """Durable local paths for release draft artifacts."""

    root: str
    release_notes_path: str
    regression_scope_path: str


@dataclass(frozen=True)
class ReleaseDraftBundle:
    """Release draft bundle that can be stored locally and synced to Confluence."""

    release_notes: ReleaseNotesDraft
    regression_scope: RegressionScopeDraft
    paths: ReleaseDraftPaths


def build_release_notes_draft(
    *,
    release_key: str,
    release_version: str,
    title: str,
    generated_at: str,
    included_items: tuple[ReleaseDraftWorkItem, ...],
    known_limitations: tuple[ReleaseKnownLimitation, ...] = (),
) -> ReleaseNotesDraft:
    """Build a Product Owner reviewable release notes draft."""

    _require_text("release_key", release_key)
    _require_text("release_version", release_version)
    _require_text("title", title)
    _require_text("generated_at", generated_at)
    if not included_items:
        raise ReleaseDraftError("included_items is required")
    for item in included_items:
        _validate_work_item(item)
    for limitation in known_limitations:
        _validate_known_limitation(limitation)
    return ReleaseNotesDraft(
        release_key=release_key.strip(),
        release_version=release_version.strip(),
        title=title.strip(),
        generated_at=generated_at.strip(),
        included_items=included_items,
        known_limitations=known_limitations,
    )


def build_regression_scope_draft(
    *,
    release_key: str,
    release_version: str,
    generated_at: str,
    classified_tests: tuple[ClassifiedTestIssue, ...],
    changed_areas: tuple[str, ...],
    agiletest_mapping_plan: AgileTestMappingPlan | None = None,
) -> RegressionScopeDraft:
    """Build a Product Owner reviewable regression scope draft."""

    _require_text("release_key", release_key)
    _require_text("release_version", release_version)
    _require_text("generated_at", generated_at)
    if not classified_tests:
        raise ReleaseDraftError("classified_tests is required")
    for test in classified_tests:
        _validate_classified_test(test)
    changed_areas = _unique_texts("changed_areas", changed_areas)
    if not changed_areas:
        raise ReleaseDraftError("changed_areas is required")
    return RegressionScopeDraft(
        release_key=release_key.strip(),
        release_version=release_version.strip(),
        generated_at=generated_at.strip(),
        classified_tests=classified_tests,
        changed_areas=changed_areas,
        agiletest_mapping_plan=agiletest_mapping_plan,
    )


def approve_release_notes_draft(draft: ReleaseNotesDraft) -> ReleaseNotesDraft:
    """Mark release notes draft as Product Owner approved."""

    _validate_release_notes_draft(draft)
    return replace(draft, status=ReleaseDraftStatus.PO_APPROVED)


def request_release_notes_changes(draft: ReleaseNotesDraft) -> ReleaseNotesDraft:
    """Mark release notes draft as requiring Product Owner-requested changes."""

    _validate_release_notes_draft(draft)
    return replace(draft, status=ReleaseDraftStatus.CHANGES_REQUESTED)


def approve_regression_scope_draft(draft: RegressionScopeDraft) -> RegressionScopeDraft:
    """Mark regression scope draft as Product Owner approved."""

    _validate_regression_scope_draft(draft)
    return replace(draft, status=ReleaseDraftStatus.PO_APPROVED)


def request_regression_scope_changes(draft: RegressionScopeDraft) -> RegressionScopeDraft:
    """Mark regression scope draft as requiring Product Owner-requested changes."""

    _validate_regression_scope_draft(draft)
    return replace(draft, status=ReleaseDraftStatus.CHANGES_REQUESTED)


def regression_scope_buckets(
    classified_tests: tuple[ClassifiedTestIssue, ...],
) -> tuple[RegressionScopeBucket, ...]:
    """Group Test issue keys by regression classification."""

    grouped: dict[RegressionClassification, list[str]] = {
        RegressionClassification.ONE_TIME_VALIDATION: [],
        RegressionClassification.SMOKE_REGRESSION: [],
        RegressionClassification.RELEASE_REGRESSION: [],
        RegressionClassification.REGRESSION_CANDIDATE: [],
        RegressionClassification.AUTOMATED_CANDIDATE: [],
        RegressionClassification.AUTOMATED_COVERED: [],
        RegressionClassification.MANUAL_ONLY: [],
    }
    for test in classified_tests:
        _validate_classified_test(test)
        for classification in test.classifications:
            grouped[classification].append(test.test_issue_key)
    return tuple(
        RegressionScopeBucket(classification, tuple(sorted(set(keys))))
        for classification, keys in grouped.items()
        if keys
    )


def suggest_release_draft_paths(*, root: str, release_key: str) -> ReleaseDraftPaths:
    """Suggest durable local Markdown paths for release draft artifacts."""

    root = _require_text("root", root)
    release_key = _safe_path_segment("release_key", release_key)
    release_root = PurePosixPath(root) / release_key
    return ReleaseDraftPaths(
        root=str(release_root),
        release_notes_path=str(release_root / "release-notes.md"),
        regression_scope_path=str(release_root / "regression-scope.md"),
    )


def render_release_notes_markdown(draft: ReleaseNotesDraft) -> str:
    """Render release notes for Jira comments, local files, or Confluence sync."""

    _validate_release_notes_draft(draft)
    lines = [
        f"# {draft.title}",
        "",
        f"- Release key: {draft.release_key}",
        f"- Version: {draft.release_version}",
        f"- Generated at: {draft.generated_at}",
        f"- Status: {draft.status.value}",
        f"- Confluence ready: {'yes' if draft.confluence_ready else 'no'}",
        "",
        "## Included Work",
    ]
    for item in draft.included_items:
        lines.append(f"- {item.key} ({item.issue_type}, {item.status}): {item.title}")
        _append_optional_list(lines, "  - PR", item.pull_requests)
        _append_optional_list(lines, "  - Test", item.test_issue_keys)
        _append_optional_list(lines, "  - Bug", item.linked_bug_keys)
    lines.extend(["", "## Known Limitations"])
    if not draft.known_limitations:
        lines.append("- None")
    for limitation in draft.known_limitations:
        suffix = f" ({limitation.linked_issue_key})" if limitation.linked_issue_key else ""
        lines.append(f"- {limitation.summary}{suffix}")
        lines.append(f"  - Impact: {limitation.impact}")
        if limitation.workaround:
            lines.append(f"  - Workaround: {limitation.workaround}")
    return "\n".join(lines)


def render_regression_scope_markdown(draft: RegressionScopeDraft) -> str:
    """Render regression scope for Product Owner review."""

    _validate_regression_scope_draft(draft)
    lines = [
        f"# Regression Scope - {draft.release_key}",
        "",
        f"- Version: {draft.release_version}",
        f"- Generated at: {draft.generated_at}",
        f"- Status: {draft.status.value}",
        f"- Confluence ready: {'yes' if draft.confluence_ready else 'no'}",
        "",
        "## Changed Areas",
    ]
    for area in draft.changed_areas:
        lines.append(f"- {area}")
    lines.extend(["", "## Regression Buckets"])
    for bucket in draft.buckets:
        lines.append(f"### {bucket.classification.value}")
        for key in bucket.test_issue_keys:
            lines.append(f"- {key}")
    lines.extend(["", "## AgileTest Mapping"])
    if draft.agiletest_mapping_plan is None:
        lines.append("- Not configured")
    else:
        lines.append(f"- Enabled: {'yes' if draft.agiletest_mapping_plan.enabled else 'no'}")
        for mapping in draft.agiletest_mapping_plan.mappings:
            lines.append(
                "- "
                f"{mapping.source_test_issue_key} -> {mapping.covered_issue_key} "
                f"({mapping.artifact_type.value}, {mapping.link_type}/{mapping.outward_relationship})"
            )
        for warning in draft.agiletest_mapping_plan.warnings:
            lines.append(f"- Warning: {warning}")
    return "\n".join(lines)


def _validate_release_notes_draft(draft: ReleaseNotesDraft) -> None:
    build_release_notes_draft(
        release_key=draft.release_key,
        release_version=draft.release_version,
        title=draft.title,
        generated_at=draft.generated_at,
        included_items=draft.included_items,
        known_limitations=draft.known_limitations,
    )


def _validate_regression_scope_draft(draft: RegressionScopeDraft) -> None:
    build_regression_scope_draft(
        release_key=draft.release_key,
        release_version=draft.release_version,
        generated_at=draft.generated_at,
        classified_tests=draft.classified_tests,
        changed_areas=draft.changed_areas,
        agiletest_mapping_plan=draft.agiletest_mapping_plan,
    )


def _append_optional_list(lines: list[str], prefix: str, values: tuple[str, ...]) -> None:
    for value in values:
        lines.append(f"{prefix}: {value}")


def _validate_work_item(item: ReleaseDraftWorkItem) -> None:
    _require_text("item.key", item.key)
    _require_text("item.title", item.title)
    _require_text("item.issue_type", item.issue_type)
    _require_text("item.status", item.status)
    _unique_texts("item.pull_requests", item.pull_requests)
    _unique_texts("item.test_issue_keys", item.test_issue_keys)
    _unique_texts("item.linked_bug_keys", item.linked_bug_keys)


def _validate_known_limitation(limitation: ReleaseKnownLimitation) -> None:
    _require_text("limitation.summary", limitation.summary)
    _require_text("limitation.impact", limitation.impact)


def _validate_classified_test(test: ClassifiedTestIssue) -> None:
    _require_text("test.test_issue_key", test.test_issue_key)
    _require_text("test.summary", test.summary)
    _require_text("test.covered_issue_key", test.covered_issue_key)
    if not test.classifications:
        raise ReleaseDraftError("test.classifications is required")


def _unique_texts(name: str, values: tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for index, value in enumerate(values):
        text = _require_text(f"{name}[{index}]", value)
        if text not in seen:
            normalized.append(text)
            seen.add(text)
    return tuple(normalized)


def _safe_path_segment(name: str, value: str) -> str:
    text = _require_text(name, value)
    if "/" in text or "\\" in text or text in {".", ".."}:
        raise ReleaseDraftError(f"{name} must be a safe path segment")
    return text


def _require_text(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReleaseDraftError(f"{name} is required")
    return value.strip()
