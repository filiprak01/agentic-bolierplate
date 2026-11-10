"""Release branch and version tag planning workflow."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any


DEFAULT_MAIN_BRANCH = "main"
RELEASE_BRANCH_PATTERN = re.compile(r"^release/(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.x$")
VERSION_TAG_PATTERN = re.compile(r"^v(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)$")


@dataclass(frozen=True)
class ReleaseVersion:
    """Version metadata following major_update.sprint_scope.hotfix."""

    major_update: int
    sprint_scope: int
    hotfix: int = 0

    @property
    def value(self) -> str:
        return f"{self.major_update}.{self.sprint_scope}.{self.hotfix}"

    @property
    def release_branch_name(self) -> str:
        return f"release/{self.major_update}.{self.sprint_scope}.x"

    @property
    def version_tag_name(self) -> str:
        return f"v{self.value}"


@dataclass(frozen=True)
class ReleaseIncludedWorkItem:
    """Story, bug, task, or PR included in a release branch plan."""

    issue_key: str
    summary: str
    pull_request_url: str = ""
    merge_commit_sha: str = ""


@dataclass(frozen=True)
class ReleaseBranchPlan:
    """Release Manager plan for creating a release maintenance branch and tag."""

    release_version: ReleaseVersion
    release_branch_name: str
    version_tag_name: str
    source_ref: str
    main_branch: str
    included_work_items: tuple[ReleaseIncludedWorkItem, ...]
    merge_back_target: str
    merge_forward_required: bool
    manual_approval_required: bool
    rationale: str


class ReleaseAutomationAction(str, Enum):
    """Release branch/tag automation action names."""

    FETCH_MAIN = "fetch_main"
    CREATE_RELEASE_BRANCH = "create_release_branch"
    CREATE_VERSION_TAG = "create_version_tag"
    PUSH_RELEASE_BRANCH = "push_release_branch"
    PUSH_VERSION_TAG = "push_version_tag"
    PUBLISH_CHECKLIST = "publish_checklist"


@dataclass(frozen=True)
class ReleaseBranchAutomationPlan:
    """Executable release branch/tag checklist gated by regression status."""

    branch_plan: ReleaseBranchPlan
    regression_passed: bool
    regression_evidence_path: str
    blocking_bug_keys: tuple[str, ...]
    ready_to_execute: bool
    blockers: tuple[str, ...]
    actions: tuple[ReleaseAutomationAction, ...]
    git_commands: tuple[str, ...]
    checklist_markdown: str


class ReleaseBranchWorkflowError(ValueError):
    """Raised when release branch workflow input is invalid."""


def build_release_branch_plan(
    *,
    major_update: int,
    sprint_scope: int,
    source_ref: str,
    included_work_items: tuple[ReleaseIncludedWorkItem, ...],
    hotfix: int = 0,
    main_branch: str = DEFAULT_MAIN_BRANCH,
    manual_approval_required: bool = True,
    rationale: str,
) -> ReleaseBranchPlan:
    """Build a deterministic release branch and tag plan."""

    version = ReleaseVersion(
        major_update=_require_non_negative_int("major_update", major_update),
        sprint_scope=_require_non_negative_int("sprint_scope", sprint_scope),
        hotfix=_require_non_negative_int("hotfix", hotfix),
    )
    _require_text("source_ref", source_ref)
    _require_text("main_branch", main_branch)
    _require_text("rationale", rationale)
    if not included_work_items:
        raise ReleaseBranchWorkflowError("included_work_items must contain at least one item")
    for index, item in enumerate(included_work_items):
        _validate_work_item(index, item)

    return ReleaseBranchPlan(
        release_version=version,
        release_branch_name=version.release_branch_name,
        version_tag_name=version.version_tag_name,
        source_ref=source_ref.strip(),
        main_branch=main_branch.strip(),
        included_work_items=included_work_items,
        merge_back_target=version.release_branch_name,
        merge_forward_required=True,
        manual_approval_required=manual_approval_required,
        rationale=rationale.strip(),
    )


def validate_release_branch_name(branch_name: str) -> ReleaseVersion:
    """Validate and parse a release maintenance branch name."""

    match = RELEASE_BRANCH_PATTERN.match(_require_text("branch_name", branch_name))
    if not match:
        raise ReleaseBranchWorkflowError("branch_name must match release/{MAJOR}.{MINOR}.x")
    return ReleaseVersion(
        major_update=int(match.group("major")),
        sprint_scope=int(match.group("minor")),
        hotfix=0,
    )


def validate_version_tag_name(tag_name: str) -> ReleaseVersion:
    """Validate and parse a release version tag name."""

    match = VERSION_TAG_PATTERN.match(_require_text("tag_name", tag_name))
    if not match:
        raise ReleaseBranchWorkflowError("tag_name must match v{MAJOR}.{MINOR}.{PATCH}")
    return ReleaseVersion(
        major_update=int(match.group("major")),
        sprint_scope=int(match.group("minor")),
        hotfix=int(match.group("patch")),
    )


def release_branch_plan_to_dict(plan: ReleaseBranchPlan) -> dict[str, Any]:
    """Convert a release branch plan to JSON-compatible data."""

    _validate_plan(plan)
    return {
        "release_version": {
            "major_update": plan.release_version.major_update,
            "sprint_scope": plan.release_version.sprint_scope,
            "hotfix": plan.release_version.hotfix,
            "value": plan.release_version.value,
        },
        "release_branch_name": plan.release_branch_name,
        "version_tag_name": plan.version_tag_name,
        "source_ref": plan.source_ref,
        "main_branch": plan.main_branch,
        "included_work_items": [
            {
                "issue_key": item.issue_key,
                "summary": item.summary,
                "pull_request_url": item.pull_request_url,
                "merge_commit_sha": item.merge_commit_sha,
            }
            for item in plan.included_work_items
        ],
        "merge_back_target": plan.merge_back_target,
        "merge_forward_required": plan.merge_forward_required,
        "manual_approval_required": plan.manual_approval_required,
        "rationale": plan.rationale,
    }


def release_branch_plan_from_dict(data: dict[str, Any]) -> ReleaseBranchPlan:
    """Build a release branch plan from JSON-compatible data."""

    version_data = data.get("release_version")
    if not isinstance(version_data, dict):
        raise ReleaseBranchWorkflowError("release_version is required")
    plan = ReleaseBranchPlan(
        release_version=ReleaseVersion(
            major_update=_int_value(version_data.get("major_update")),
            sprint_scope=_int_value(version_data.get("sprint_scope")),
            hotfix=_int_value(version_data.get("hotfix")),
        ),
        release_branch_name=_optional_text(data.get("release_branch_name")),
        version_tag_name=_optional_text(data.get("version_tag_name")),
        source_ref=_optional_text(data.get("source_ref")),
        main_branch=_optional_text(data.get("main_branch")),
        included_work_items=tuple(
            ReleaseIncludedWorkItem(
                issue_key=_optional_text(item.get("issue_key")),
                summary=_optional_text(item.get("summary")),
                pull_request_url=_optional_text(item.get("pull_request_url")),
                merge_commit_sha=_optional_text(item.get("merge_commit_sha")),
            )
            for item in data.get("included_work_items", ())
        ),
        merge_back_target=_optional_text(data.get("merge_back_target")),
        merge_forward_required=bool(data.get("merge_forward_required")),
        manual_approval_required=bool(data.get("manual_approval_required", True)),
        rationale=_optional_text(data.get("rationale")),
    )
    _validate_plan(plan)
    return plan


def render_release_branch_plan(plan: ReleaseBranchPlan) -> str:
    """Render a release branch plan for Jira, evidence, or Confluence."""

    _validate_plan(plan)
    lines = [
        f"# Release Branch Plan - {plan.release_version.value}",
        "",
        f"- Release branch: {plan.release_branch_name}",
        f"- Version tag: {plan.version_tag_name}",
        f"- Source ref: {plan.source_ref}",
        f"- Main branch: {plan.main_branch}",
        f"- Merge back target: {plan.merge_back_target}",
        f"- Merge forward required: {'yes' if plan.merge_forward_required else 'no'}",
        f"- Manual approval required: {'yes' if plan.manual_approval_required else 'no'}",
        f"- Rationale: {plan.rationale}",
        "",
        "## Included Work",
    ]
    for item in plan.included_work_items:
        detail = item.issue_key
        if item.pull_request_url:
            detail += f" - {item.pull_request_url}"
        if item.merge_commit_sha:
            detail += f" ({item.merge_commit_sha})"
        lines.append(f"- {detail}: {item.summary}")
    return "\n".join(lines).strip() + "\n"


def build_release_branch_automation_plan(
    *,
    branch_plan: ReleaseBranchPlan,
    regression_passed: bool,
    regression_evidence_path: str,
    blocking_bug_keys: tuple[str, ...] = (),
) -> ReleaseBranchAutomationPlan:
    """Build the gated branch/tag automation checklist after regression."""

    _validate_plan(branch_plan)
    blockers = _release_automation_blockers(
        branch_plan=branch_plan,
        regression_passed=regression_passed,
        regression_evidence_path=regression_evidence_path,
        blocking_bug_keys=blocking_bug_keys,
    )
    ready = not blockers
    actions = (
        ReleaseAutomationAction.FETCH_MAIN,
        ReleaseAutomationAction.CREATE_RELEASE_BRANCH,
        ReleaseAutomationAction.CREATE_VERSION_TAG,
        ReleaseAutomationAction.PUSH_RELEASE_BRANCH,
        ReleaseAutomationAction.PUSH_VERSION_TAG,
        ReleaseAutomationAction.PUBLISH_CHECKLIST,
    )
    git_commands = _release_automation_commands(branch_plan) if ready else ()
    checklist = render_release_branch_automation_checklist(
        branch_plan=branch_plan,
        regression_passed=regression_passed,
        regression_evidence_path=regression_evidence_path,
        blocking_bug_keys=blocking_bug_keys,
        blockers=blockers,
        git_commands=git_commands,
    )
    return ReleaseBranchAutomationPlan(
        branch_plan=branch_plan,
        regression_passed=regression_passed,
        regression_evidence_path=regression_evidence_path.strip(),
        blocking_bug_keys=tuple(key.strip() for key in blocking_bug_keys if key.strip()),
        ready_to_execute=ready,
        blockers=blockers,
        actions=actions if ready else (),
        git_commands=git_commands,
        checklist_markdown=checklist,
    )


def render_release_branch_automation_checklist(
    *,
    branch_plan: ReleaseBranchPlan,
    regression_passed: bool,
    regression_evidence_path: str,
    blocking_bug_keys: tuple[str, ...] = (),
    blockers: tuple[str, ...] | None = None,
    git_commands: tuple[str, ...] | None = None,
) -> str:
    """Render the Release Manager checklist for branch/tag execution."""

    _validate_plan(branch_plan)
    blockers = (
        _release_automation_blockers(
            branch_plan=branch_plan,
            regression_passed=regression_passed,
            regression_evidence_path=regression_evidence_path,
            blocking_bug_keys=blocking_bug_keys,
        )
        if blockers is None
        else blockers
    )
    git_commands = (
        _release_automation_commands(branch_plan)
        if git_commands is None and not blockers
        else (git_commands or ())
    )
    lines = [
        f"# Release Branch Automation Checklist - {branch_plan.release_version.value}",
        "",
        f"- Ready to execute: {'yes' if not blockers else 'no'}",
        f"- Release branch: `{branch_plan.release_branch_name}`",
        f"- Version tag: `{branch_plan.version_tag_name}`",
        f"- Source ref: `{branch_plan.source_ref}`",
        f"- Regression passed: {'yes' if regression_passed else 'no'}",
        f"- Regression evidence: `{regression_evidence_path.strip() or 'missing'}`",
        f"- Manual approval required: {'yes' if branch_plan.manual_approval_required else 'no'}",
        "",
        "## Blocking Bugs",
    ]
    if blocking_bug_keys:
        lines.extend(f"- {key}" for key in blocking_bug_keys)
    else:
        lines.append("- none")
    lines.extend(["", "## Blockers"])
    if blockers:
        lines.extend(f"- {blocker}" for blocker in blockers)
    else:
        lines.append("- none")
    lines.extend(["", "## Git Commands"])
    if git_commands:
        lines.append("```bash")
        lines.extend(git_commands)
        lines.append("```")
    else:
        lines.append("No commands are executable until blockers are resolved.")
    lines.extend(["", "## Checklist"])
    lines.extend(
        [
            "- [ ] Regression evidence is linked in Jira.",
            "- [ ] Release scope matches included work items.",
            "- [ ] Blocking bugs list is empty.",
            "- [ ] Branch creation command completed.",
            "- [ ] Version tag command completed.",
            "- [ ] Branch and tag were pushed to origin.",
            "- [ ] Checklist was published to the release evidence location.",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def _validate_plan(plan: ReleaseBranchPlan) -> None:
    expected_branch = plan.release_version.release_branch_name
    expected_tag = plan.release_version.version_tag_name
    if plan.release_branch_name != expected_branch:
        raise ReleaseBranchWorkflowError(f"release_branch_name must be {expected_branch}")
    if plan.version_tag_name != expected_tag:
        raise ReleaseBranchWorkflowError(f"version_tag_name must be {expected_tag}")
    if plan.merge_back_target != expected_branch:
        raise ReleaseBranchWorkflowError("merge_back_target must be the release branch")
    _require_text("source_ref", plan.source_ref)
    _require_text("main_branch", plan.main_branch)
    _require_text("rationale", plan.rationale)
    if not plan.included_work_items:
        raise ReleaseBranchWorkflowError("included_work_items must contain at least one item")
    for index, item in enumerate(plan.included_work_items):
        _validate_work_item(index, item)


def _validate_work_item(index: int, item: ReleaseIncludedWorkItem) -> None:
    _require_text(f"included_work_items[{index}].issue_key", item.issue_key)
    _require_text(f"included_work_items[{index}].summary", item.summary)


def _release_automation_blockers(
    *,
    branch_plan: ReleaseBranchPlan,
    regression_passed: bool,
    regression_evidence_path: str,
    blocking_bug_keys: tuple[str, ...],
) -> tuple[str, ...]:
    blockers: list[str] = []
    if not regression_passed:
        blockers.append("regression must pass before release branch/tag automation")
    if not regression_evidence_path.strip():
        blockers.append("regression evidence path is required")
    normalized_blocking_bugs = tuple(key.strip() for key in blocking_bug_keys if key.strip())
    if normalized_blocking_bugs:
        blockers.append("blocking bugs must be resolved before release branch/tag automation")
    if not branch_plan.included_work_items:
        blockers.append("release branch plan must include at least one work item")
    return tuple(blockers)


def _release_automation_commands(plan: ReleaseBranchPlan) -> tuple[str, ...]:
    quoted_message = f"Release {plan.release_version.value}"
    return (
        f"git fetch origin {plan.main_branch}",
        f"git switch {plan.main_branch}",
        f"git pull --ff-only origin {plan.main_branch}",
        f"git switch -c {plan.release_branch_name} {plan.source_ref}",
        f"git tag -a {plan.version_tag_name} -m \"{quoted_message}\"",
        f"git push origin {plan.release_branch_name}",
        f"git push origin {plan.version_tag_name}",
    )


def _optional_text(value: object) -> str:
    return str(value or "").strip()


def _int_value(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ReleaseBranchWorkflowError("integer value is required")
    return value


def _require_text(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReleaseBranchWorkflowError(f"{name} is required")
    return value.strip()


def _require_non_negative_int(name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ReleaseBranchWorkflowError(f"{name} must be a non-negative integer")
    return value
