"""Sprint regression overview planning for Release Manager."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from agentic_boilerplate.domain.behavioral_regression_visibility import (
    RegressionBoardFilterPlan,
    RegressionOverviewTaskPlan,
    RegressionVisibilityCategory,
    RegressionVisibilityConfig,
    RegressionVisibilityError,
    RegressionVisibilityItem,
    RegressionVisibilityLinkPlan,
    build_regression_board_filter_plan,
    build_regression_overview_task_plan,
    build_regression_visibility_link_plans,
)


class SprintRegressionOverviewWarningType(str, Enum):
    """Warnings for missing regression overview publication inputs."""

    MISSING_MANIFEST_KEY = "missing-manifest-key"
    MISSING_MANIFEST_PATH = "missing-manifest-path"
    MISSING_EVIDENCE_PATH = "missing-evidence-path"
    MISSING_TEST_EXECUTION_KEY = "missing-test-execution-key"


@dataclass(frozen=True)
class SprintRegressionOverviewWarning:
    """One warning describing incomplete regression overview inputs."""

    warning_type: SprintRegressionOverviewWarningType
    message: str


@dataclass(frozen=True)
class SprintRegressionOverviewPlan:
    """Board-visible Sprint regression overview and publication plan."""

    sprint_name: str
    release_label: str
    sprint_label: str
    config: RegressionVisibilityConfig
    overview_task_plan: RegressionOverviewTaskPlan
    board_filter_plan: RegressionBoardFilterPlan
    link_plans: tuple[RegressionVisibilityLinkPlan, ...]
    test_execution_key: str
    manifest_key: str
    manifest_path: str
    evidence_path: str
    warnings: tuple[SprintRegressionOverviewWarning, ...]

    @property
    def ready_for_publication(self) -> bool:
        return not self.warnings


@dataclass(frozen=True)
class SprintRegressionOverviewIssue:
    """Validation issue for regression overview planning."""

    field: str
    message: str


class SprintRegressionOverviewError(ValueError):
    """Raised when regression overview input is incomplete."""

    def __init__(self, issues: Sequence[SprintRegressionOverviewIssue]) -> None:
        self.issues = tuple(issues)
        super().__init__(format_sprint_regression_overview_issues(self.issues))


def build_sprint_regression_overview_plan(
    *,
    sprint_name: str,
    release_label: str,
    sprint_label: str,
    config: RegressionVisibilityConfig,
    behavioral_items: tuple[RegressionVisibilityItem, ...] = (),
    supporting_items: tuple[RegressionVisibilityItem, ...] = (),
    test_execution_key: str = "",
    manifest_key: str = "",
    manifest_path: str = "",
    evidence_path: str = "",
) -> SprintRegressionOverviewPlan:
    """Build a board-visible overview plan for sprint regression execution."""

    issues: list[SprintRegressionOverviewIssue] = []
    _require_text(issues, "sprint_name", sprint_name)
    _require_text(issues, "release_label", release_label)
    _require_text(issues, "sprint_label", sprint_label)
    _validate_config(config, issues)
    if not behavioral_items and not supporting_items:
        issues.append(
            SprintRegressionOverviewIssue(
                "items",
                "At least one behavioral or supporting regression item is required.",
            )
        )
    if issues:
        raise SprintRegressionOverviewError(issues)

    overview_task_plan = build_regression_overview_task_plan(
        sprint_name=sprint_name,
        release_label=release_label,
        sprint_label=sprint_label,
        config=config,
        behavioral_items=behavioral_items,
        supporting_items=supporting_items,
        test_execution_key=test_execution_key,
    )
    board_filter_plan = build_regression_board_filter_plan(config)
    link_plans = build_regression_visibility_link_plans(
        overview_task_key=manifest_key.strip() or _publication_placeholder(sprint_name),
        config=config,
        test_execution_key=test_execution_key,
        test_case_keys=tuple(item.key for item in (*behavioral_items, *supporting_items)),
    )
    warnings = _build_warnings(
        manifest_key=manifest_key,
        manifest_path=manifest_path,
        evidence_path=evidence_path,
        test_execution_key=test_execution_key,
    )
    return SprintRegressionOverviewPlan(
        sprint_name=sprint_name.strip(),
        release_label=release_label.strip(),
        sprint_label=sprint_label.strip(),
        config=config,
        overview_task_plan=overview_task_plan,
        board_filter_plan=board_filter_plan,
        link_plans=link_plans,
        test_execution_key=test_execution_key.strip(),
        manifest_key=manifest_key.strip(),
        manifest_path=manifest_path.strip(),
        evidence_path=evidence_path.strip(),
        warnings=warnings,
    )


def render_sprint_regression_overview_plan(plan: SprintRegressionOverviewPlan) -> str:
    """Render a durable Markdown summary for Jira comments or local evidence."""

    _validate_plan(plan)
    lines = [
        f"Sprint: {plan.sprint_name}",
        f"Release label: {plan.release_label}",
        f"Sprint label: {plan.sprint_label}",
        f"Overview task summary: {plan.overview_task_plan.summary}",
        f"Overview issue type: {plan.overview_task_plan.issue_type}",
        f"Ready for publication: {'yes' if plan.ready_for_publication else 'no'}",
        "",
        "Board filter:",
        plan.board_filter_plan.jql,
        "",
        "Included items:",
    ]
    for item in plan.overview_task_plan.behavioral_items:
        lines.append(f"- behavioral: {item.key} -> {item.summary} [{item.evidence_path or 'no evidence path'}]")
    for item in plan.overview_task_plan.supporting_items:
        lines.append(f"- supporting: {item.key} -> {item.summary} [{item.evidence_path or 'no evidence path'}]")
    if plan.test_execution_key:
        lines.append(f"Test execution key: {plan.test_execution_key}")
    if plan.manifest_key:
        lines.extend(["", f"Manifest key: {plan.manifest_key}"])
    if plan.manifest_path:
        lines.append(f"Manifest path: {plan.manifest_path}")
    if plan.evidence_path:
        lines.append(f"Evidence path: {plan.evidence_path}")
    if plan.link_plans:
        lines.extend(["", "Links:"])
        for link in plan.link_plans:
            lines.append(f"- {link.source_issue_key} -> {link.target_issue_key} ({link.link_type})")
    if plan.warnings:
        lines.extend(["", "Warnings:"])
        for warning in plan.warnings:
            lines.append(f"- {warning.message}")
    return "\n".join(lines).strip()


def render_sprint_regression_overview_jira_comment(plan: SprintRegressionOverviewPlan) -> str:
    """Render a Jira-ready summary for the overview task or publication note."""

    _validate_plan(plan)
    lines = [
        f"Sprint regression overview prepared for {plan.sprint_name}.",
        f"Board filter: {plan.board_filter_plan.jql}",
        f"Ready for publication: {'yes' if plan.ready_for_publication else 'no'}",
    ]
    if plan.manifest_key:
        lines.append(f"Manifest key: {plan.manifest_key}")
    if plan.evidence_path:
        lines.append(f"Evidence path: {plan.evidence_path}")
    if plan.test_execution_key:
        lines.append(f"Test execution key: {plan.test_execution_key}")
    if plan.link_plans:
        lines.append(f"Links planned: {len(plan.link_plans)}")
    if plan.warnings:
        lines.append("Warnings:")
        lines.extend(f"- {warning.message}" for warning in plan.warnings)
    return "\n".join(lines).strip()


def format_sprint_regression_overview_issues(issues: Sequence[SprintRegressionOverviewIssue]) -> str:
    return "; ".join(f"{issue.field}: {issue.message}" for issue in issues)


def _build_warnings(
    *,
    manifest_key: str,
    manifest_path: str,
    evidence_path: str,
    test_execution_key: str,
) -> tuple[SprintRegressionOverviewWarning, ...]:
    warnings: list[SprintRegressionOverviewWarning] = []
    if not manifest_key.strip():
        warnings.append(
            SprintRegressionOverviewWarning(
                warning_type=SprintRegressionOverviewWarningType.MISSING_MANIFEST_KEY,
                message="Regression manifest key was not provided.",
            )
        )
    if not manifest_path.strip():
        warnings.append(
            SprintRegressionOverviewWarning(
                warning_type=SprintRegressionOverviewWarningType.MISSING_MANIFEST_PATH,
                message="Durable regression manifest path was not provided.",
            )
        )
    if not evidence_path.strip():
        warnings.append(
            SprintRegressionOverviewWarning(
                warning_type=SprintRegressionOverviewWarningType.MISSING_EVIDENCE_PATH,
                message="Durable regression evidence path was not provided.",
            )
        )
    if not test_execution_key.strip():
        warnings.append(
            SprintRegressionOverviewWarning(
                warning_type=SprintRegressionOverviewWarningType.MISSING_TEST_EXECUTION_KEY,
                message="Test execution key was not provided.",
            )
        )
    return tuple(warnings)


def _validate_plan(plan: SprintRegressionOverviewPlan) -> None:
    issues: list[SprintRegressionOverviewIssue] = []
    _require_text(issues, "sprint_name", plan.sprint_name)
    _require_text(issues, "release_label", plan.release_label)
    _require_text(issues, "sprint_label", plan.sprint_label)
    if not isinstance(plan.config, RegressionVisibilityConfig):
        issues.append(SprintRegressionOverviewIssue("config", "config must be a RegressionVisibilityConfig"))
    if not isinstance(plan.overview_task_plan, RegressionOverviewTaskPlan):
        issues.append(SprintRegressionOverviewIssue("overview_task_plan", "overview_task_plan is invalid"))
    if issues:
        raise SprintRegressionOverviewError(issues)


def _validate_config(config: RegressionVisibilityConfig, issues: list[SprintRegressionOverviewIssue]) -> None:
    try:
        if not isinstance(config, RegressionVisibilityConfig):
            raise RegressionVisibilityError("config must be a RegressionVisibilityConfig")
        build_regression_board_filter_plan(config)
    except RegressionVisibilityError as error:
        issues.append(SprintRegressionOverviewIssue("config", str(error)))


def _require_text(issues: list[SprintRegressionOverviewIssue], field: str, value: str) -> str:
    normalized = value.strip()
    if not normalized:
        issues.append(SprintRegressionOverviewIssue(field, "Value is required."))
    return normalized


def _publication_placeholder(sprint_name: str) -> str:
    normalized = "".join(character.lower() if character.isalnum() else "-" for character in sprint_name.strip())
    while "--" in normalized:
        normalized = normalized.replace("--", "-")
    return f"{normalized.strip('-') or 'sprint'}-regression-overview"
