"""Hotfix branch planning workflow."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from agentic_boilerplate.domain.release_branch_version import (
    DEFAULT_MAIN_BRANCH,
    ReleaseVersion,
    validate_release_branch_name,
    validate_version_tag_name,
)


HOTFIX_BRANCH_PATTERN = re.compile(
    r"^hotfix/(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>[1-9]\d*)-(?P<slug>[A-Za-z0-9][A-Za-z0-9._-]*)$"
)


class HotfixSourceType(str, Enum):
    """Allowed hotfix source refs."""

    RELEASE_BRANCH = "release-branch"
    RELEASE_TAG = "release-tag"


@dataclass(frozen=True)
class HotfixBugReference:
    """Bug fixed by a hotfix branch."""

    issue_key: str
    summary: str
    environment: str = ""
    severity: str = ""


@dataclass(frozen=True)
class HotfixBranchPlan:
    """Release Manager plan for a hotfix branch."""

    hotfix_version: ReleaseVersion
    hotfix_branch_name: str
    source_ref: str
    source_type: HotfixSourceType
    fixed_bug: HotfixBugReference
    merge_back_target: str
    forward_port_target: str
    conflict_resolution_required: bool
    manual_approval_points: tuple[str, ...]
    rationale: str


class HotfixBranchWorkflowError(ValueError):
    """Raised when hotfix workflow input is invalid."""


def build_hotfix_branch_plan(
    *,
    major_update: int,
    sprint_scope: int,
    hotfix: int,
    jira_key_or_slug: str,
    source_ref: str,
    fixed_bug: HotfixBugReference,
    forward_port_target: str = DEFAULT_MAIN_BRANCH,
    conflict_resolution_required: bool = False,
    manual_approval_points: tuple[str, ...] = (
        "Release Manager approves hotfix scope.",
        "Product Owner accepts the fixed behavior before release.",
    ),
    rationale: str,
) -> HotfixBranchPlan:
    """Build a deterministic hotfix branch plan."""

    version = ReleaseVersion(
        major_update=_require_non_negative_int("major_update", major_update),
        sprint_scope=_require_non_negative_int("sprint_scope", sprint_scope),
        hotfix=_require_positive_int("hotfix", hotfix),
    )
    slug = normalize_hotfix_slug(jira_key_or_slug)
    _require_text("source_ref", source_ref)
    _require_text("forward_port_target", forward_port_target)
    _require_text("rationale", rationale)
    _validate_bug_reference(fixed_bug)
    _validate_manual_approval_points(manual_approval_points)
    source_type = classify_hotfix_source_ref(source_ref, version)

    return HotfixBranchPlan(
        hotfix_version=version,
        hotfix_branch_name=build_hotfix_branch_name(version, slug),
        source_ref=source_ref.strip(),
        source_type=source_type,
        fixed_bug=fixed_bug,
        merge_back_target=version.release_branch_name,
        forward_port_target=forward_port_target.strip(),
        conflict_resolution_required=conflict_resolution_required,
        manual_approval_points=tuple(point.strip() for point in manual_approval_points),
        rationale=rationale.strip(),
    )


def build_hotfix_branch_name(version: ReleaseVersion, jira_key_or_slug: str) -> str:
    """Build a hotfix branch name from version metadata and a Jira key or slug."""

    _validate_version(version)
    if version.hotfix <= 0:
        raise HotfixBranchWorkflowError("version.hotfix must be greater than zero for hotfix branches")
    return f"hotfix/{version.value}-{normalize_hotfix_slug(jira_key_or_slug)}"


def validate_hotfix_branch_name(branch_name: str) -> tuple[ReleaseVersion, str]:
    """Validate and parse a hotfix branch name."""

    match = HOTFIX_BRANCH_PATTERN.match(_require_text("branch_name", branch_name))
    if not match:
        raise HotfixBranchWorkflowError(
            "branch_name must match hotfix/{MAJOR}.{MINOR}.{PATCH}-{jira-key-or-slug}"
        )
    return (
        ReleaseVersion(
            major_update=int(match.group("major")),
            sprint_scope=int(match.group("minor")),
            hotfix=int(match.group("patch")),
        ),
        match.group("slug"),
    )


def classify_hotfix_source_ref(source_ref: str, hotfix_version: ReleaseVersion) -> HotfixSourceType:
    """Classify and validate the branch or tag used as a hotfix source."""

    source_ref = _require_text("source_ref", source_ref)
    _validate_version(hotfix_version)
    try:
        release_branch_version = validate_release_branch_name(source_ref)
    except ValueError:
        release_branch_version = None
    if release_branch_version is not None:
        _require_same_release_line(release_branch_version, hotfix_version)
        return HotfixSourceType.RELEASE_BRANCH

    try:
        tag_version = validate_version_tag_name(source_ref)
    except ValueError as exc:
        raise HotfixBranchWorkflowError(
            "source_ref must be the matching release branch or a prior release tag"
        ) from exc
    _require_same_release_line(tag_version, hotfix_version)
    if tag_version.hotfix >= hotfix_version.hotfix:
        raise HotfixBranchWorkflowError("source release tag must be earlier than the hotfix version")
    return HotfixSourceType.RELEASE_TAG


def hotfix_branch_plan_to_dict(plan: HotfixBranchPlan) -> dict[str, Any]:
    """Convert a hotfix branch plan to JSON-compatible data."""

    _validate_plan(plan)
    return {
        "hotfix_version": {
            "major_update": plan.hotfix_version.major_update,
            "sprint_scope": plan.hotfix_version.sprint_scope,
            "hotfix": plan.hotfix_version.hotfix,
            "value": plan.hotfix_version.value,
        },
        "hotfix_branch_name": plan.hotfix_branch_name,
        "source_ref": plan.source_ref,
        "source_type": plan.source_type.value,
        "fixed_bug": {
            "issue_key": plan.fixed_bug.issue_key,
            "summary": plan.fixed_bug.summary,
            "environment": plan.fixed_bug.environment,
            "severity": plan.fixed_bug.severity,
        },
        "merge_back_target": plan.merge_back_target,
        "forward_port_target": plan.forward_port_target,
        "conflict_resolution_required": plan.conflict_resolution_required,
        "manual_approval_points": list(plan.manual_approval_points),
        "rationale": plan.rationale,
    }


def hotfix_branch_plan_from_dict(data: dict[str, Any]) -> HotfixBranchPlan:
    """Build a hotfix branch plan from JSON-compatible data."""

    version_data = data.get("hotfix_version")
    bug_data = data.get("fixed_bug")
    if not isinstance(version_data, dict):
        raise HotfixBranchWorkflowError("hotfix_version is required")
    if not isinstance(bug_data, dict):
        raise HotfixBranchWorkflowError("fixed_bug is required")
    plan = HotfixBranchPlan(
        hotfix_version=ReleaseVersion(
            major_update=_int_value(version_data.get("major_update")),
            sprint_scope=_int_value(version_data.get("sprint_scope")),
            hotfix=_int_value(version_data.get("hotfix")),
        ),
        hotfix_branch_name=_optional_text(data.get("hotfix_branch_name")),
        source_ref=_optional_text(data.get("source_ref")),
        source_type=HotfixSourceType(_optional_text(data.get("source_type"))),
        fixed_bug=HotfixBugReference(
            issue_key=_optional_text(bug_data.get("issue_key")),
            summary=_optional_text(bug_data.get("summary")),
            environment=_optional_text(bug_data.get("environment")),
            severity=_optional_text(bug_data.get("severity")),
        ),
        merge_back_target=_optional_text(data.get("merge_back_target")),
        forward_port_target=_optional_text(data.get("forward_port_target")),
        conflict_resolution_required=bool(data.get("conflict_resolution_required")),
        manual_approval_points=tuple(_optional_text(item) for item in data.get("manual_approval_points", ())),
        rationale=_optional_text(data.get("rationale")),
    )
    _validate_plan(plan)
    return plan


def render_hotfix_branch_plan(plan: HotfixBranchPlan) -> str:
    """Render a hotfix branch plan for Jira, evidence, or Confluence."""

    _validate_plan(plan)
    lines = [
        f"# Hotfix Branch Plan - {plan.hotfix_version.value}",
        "",
        f"- Hotfix branch: {plan.hotfix_branch_name}",
        f"- Source ref: {plan.source_ref}",
        f"- Source type: {plan.source_type.value}",
        f"- Fixed bug: {plan.fixed_bug.issue_key} - {plan.fixed_bug.summary}",
        f"- Merge back target: {plan.merge_back_target}",
        f"- Forward port target: {plan.forward_port_target}",
        f"- Conflict resolution required: {'yes' if plan.conflict_resolution_required else 'no'}",
        f"- Rationale: {plan.rationale}",
        "",
        "## Manual Approval Points",
    ]
    lines.extend(f"- {point}" for point in plan.manual_approval_points)
    return "\n".join(lines).strip() + "\n"


def normalize_hotfix_slug(value: str) -> str:
    """Normalize a Jira key or slug for the hotfix branch suffix."""

    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", _require_text("jira_key_or_slug", value)).strip("-")
    if not slug:
        raise HotfixBranchWorkflowError("jira_key_or_slug must contain at least one branch-safe character")
    return slug


def _validate_plan(plan: HotfixBranchPlan) -> None:
    expected_branch = build_hotfix_branch_name(plan.hotfix_version, validate_hotfix_branch_name(plan.hotfix_branch_name)[1])
    if plan.hotfix_branch_name != expected_branch:
        raise HotfixBranchWorkflowError(f"hotfix_branch_name must be {expected_branch}")
    if classify_hotfix_source_ref(plan.source_ref, plan.hotfix_version) != plan.source_type:
        raise HotfixBranchWorkflowError("source_type does not match source_ref")
    if plan.merge_back_target != plan.hotfix_version.release_branch_name:
        raise HotfixBranchWorkflowError("merge_back_target must be the release maintenance branch")
    _require_text("forward_port_target", plan.forward_port_target)
    _validate_bug_reference(plan.fixed_bug)
    _validate_manual_approval_points(plan.manual_approval_points)
    _require_text("rationale", plan.rationale)


def _validate_version(version: ReleaseVersion) -> None:
    _require_non_negative_int("version.major_update", version.major_update)
    _require_non_negative_int("version.sprint_scope", version.sprint_scope)
    _require_non_negative_int("version.hotfix", version.hotfix)


def _validate_bug_reference(bug: HotfixBugReference) -> None:
    _require_text("fixed_bug.issue_key", bug.issue_key)
    _require_text("fixed_bug.summary", bug.summary)


def _validate_manual_approval_points(points: tuple[str, ...]) -> None:
    if not points:
        raise HotfixBranchWorkflowError("manual_approval_points must contain at least one point")
    for index, point in enumerate(points):
        _require_text(f"manual_approval_points[{index}]", point)


def _require_same_release_line(source_version: ReleaseVersion, hotfix_version: ReleaseVersion) -> None:
    if (
        source_version.major_update != hotfix_version.major_update
        or source_version.sprint_scope != hotfix_version.sprint_scope
    ):
        raise HotfixBranchWorkflowError("source_ref must use the same major and minor release line")


def _optional_text(value: object) -> str:
    return str(value or "").strip()


def _int_value(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise HotfixBranchWorkflowError("integer value is required")
    return value


def _require_text(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HotfixBranchWorkflowError(f"{name} is required")
    return value.strip()


def _require_positive_int(name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise HotfixBranchWorkflowError(f"{name} must be a positive integer")
    return value


def _require_non_negative_int(name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise HotfixBranchWorkflowError(f"{name} must be a non-negative integer")
    return value
