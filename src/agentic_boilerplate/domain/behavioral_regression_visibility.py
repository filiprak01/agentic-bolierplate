"""Behavioral regression visibility planning."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from agentic_boilerplate.domain.regression_classification import ClassifiedTestIssue
from agentic_boilerplate.domain.tester_manual_test_workflow import RegressionClassification


BEHAVIORAL_REGRESSION_LABEL = "behavioral-regression"
SUPPORTING_VALIDATION_LABEL = "supporting-validation"
REGRESSION_OVERVIEW_LABEL = "regression-overview"
DEFAULT_DELIVERY_BOARD_EXCLUDED_ISSUE_TYPES = (
    "Test",
    "Test execution",
    "Test cycle",
    "Test script",
    "Test session",
)


class RegressionVisibilityError(ValueError):
    """Raised when regression visibility inputs are incomplete."""


class RegressionVisibilityCategory(str, Enum):
    """Visibility category used for sprint and release regression scope."""

    BEHAVIORAL_REGRESSION = "behavioral-regression"
    SUPPORTING_VALIDATION = "supporting-validation"


class RegressionCheckExposure(str, Enum):
    """The product surface exposed by a regression check."""

    USER_FACING = "user-facing"
    WORKER_FACING = "worker-facing"
    SETUP_ONLY = "setup-only"
    SCHEMA_ONLY = "schema-only"
    INTERNAL_STORAGE = "internal-storage"


@dataclass(frozen=True)
class RegressionVisibilityConfig:
    """Project-specific Jira visibility settings."""

    project_key: str
    overview_task_issue_type: str = "Task"
    test_case_issue_type: str = "Test"
    test_execution_issue_type: str = "Test execution"
    overview_link_type: str = "Relates"
    board_excluded_issue_types: tuple[str, ...] = DEFAULT_DELIVERY_BOARD_EXCLUDED_ISSUE_TYPES
    behavioral_label: str = BEHAVIORAL_REGRESSION_LABEL
    supporting_label: str = SUPPORTING_VALIDATION_LABEL
    overview_label: str = REGRESSION_OVERVIEW_LABEL


@dataclass(frozen=True)
class RegressionVisibilityItem:
    """One Test Case or validation item included in a regression overview."""

    key: str
    summary: str
    category: RegressionVisibilityCategory
    source_issue_key: str = ""
    evidence_path: str = ""
    automated: bool = False


@dataclass(frozen=True)
class RegressionOverviewTaskPlan:
    """Board-visible Task used to represent a regression run."""

    summary: str
    description: str
    issue_type: str
    labels: tuple[str, ...]
    sprint_label: str
    release_label: str
    behavioral_items: tuple[RegressionVisibilityItem, ...]
    supporting_items: tuple[RegressionVisibilityItem, ...]


@dataclass(frozen=True)
class RegressionVisibilityLinkPlan:
    """Jira link from the overview Task to a regression artifact."""

    source_issue_key: str
    target_issue_key: str
    link_type: str
    relationship: str


@dataclass(frozen=True)
class RegressionBoardFilterPlan:
    """Recommended delivery board filter behavior."""

    project_key: str
    excluded_issue_types: tuple[str, ...]
    jql: str
    editable_filter_required: bool = True


def classify_regression_visibility(
    exposure: RegressionCheckExposure,
) -> RegressionVisibilityCategory:
    """Classify whether a check is behavioral or supporting validation."""

    if not isinstance(exposure, RegressionCheckExposure):
        raise RegressionVisibilityError("exposure must be a RegressionCheckExposure")
    if exposure in {RegressionCheckExposure.USER_FACING, RegressionCheckExposure.WORKER_FACING}:
        return RegressionVisibilityCategory.BEHAVIORAL_REGRESSION
    return RegressionVisibilityCategory.SUPPORTING_VALIDATION


def regression_visibility_labels(
    category: RegressionVisibilityCategory,
    config: RegressionVisibilityConfig,
) -> tuple[str, ...]:
    """Return labels for a visibility category."""

    _validate_config(config)
    if category is RegressionVisibilityCategory.BEHAVIORAL_REGRESSION:
        return (config.behavioral_label,)
    if category is RegressionVisibilityCategory.SUPPORTING_VALIDATION:
        return (config.supporting_label,)
    raise RegressionVisibilityError("category must be a RegressionVisibilityCategory")


def regression_visibility_item_from_test_issue(
    test_issue: ClassifiedTestIssue,
    *,
    category: RegressionVisibilityCategory,
    evidence_path: str = "",
    automated: bool = False,
) -> RegressionVisibilityItem:
    """Build a visibility item from a classified Jira Test issue."""

    _require_text("test_issue.test_issue_key", test_issue.test_issue_key)
    _require_text("test_issue.summary", test_issue.summary)
    if not isinstance(category, RegressionVisibilityCategory):
        raise RegressionVisibilityError("category must be a RegressionVisibilityCategory")
    return RegressionVisibilityItem(
        key=test_issue.test_issue_key.strip(),
        summary=test_issue.summary.strip(),
        category=category,
        source_issue_key=test_issue.covered_issue_key.strip(),
        evidence_path=evidence_path.strip(),
        automated=automated,
    )


def build_regression_board_filter_plan(config: RegressionVisibilityConfig) -> RegressionBoardFilterPlan:
    """Build the recommended Scrum board filter for delivery visibility."""

    _validate_config(config)
    issue_types = ", ".join(f'"{issue_type}"' for issue_type in config.board_excluded_issue_types)
    return RegressionBoardFilterPlan(
        project_key=config.project_key.strip(),
        excluded_issue_types=config.board_excluded_issue_types,
        jql=f"project = {config.project_key.strip()} AND issuetype not in ({issue_types}) ORDER BY Rank ASC",
    )


def build_regression_overview_task_plan(
    *,
    sprint_name: str,
    release_label: str,
    sprint_label: str,
    config: RegressionVisibilityConfig,
    behavioral_items: tuple[RegressionVisibilityItem, ...] = (),
    supporting_items: tuple[RegressionVisibilityItem, ...] = (),
    test_execution_key: str = "",
) -> RegressionOverviewTaskPlan:
    """Build fields for the board-visible regression overview Task."""

    _validate_config(config)
    sprint_name = _require_text("sprint_name", sprint_name)
    release_label = _require_text("release_label", release_label)
    sprint_label = _require_text("sprint_label", sprint_label)
    _validate_items(behavioral_items, RegressionVisibilityCategory.BEHAVIORAL_REGRESSION)
    _validate_items(supporting_items, RegressionVisibilityCategory.SUPPORTING_VALIDATION)
    if not behavioral_items and not supporting_items:
        raise RegressionVisibilityError("at least one regression visibility item is required")

    labels = {config.overview_label, release_label, sprint_label}
    if behavioral_items:
        labels.add(config.behavioral_label)
    if supporting_items:
        labels.add(config.supporting_label)

    return RegressionOverviewTaskPlan(
        summary=f"{sprint_name} Regression Overview",
        description=_render_overview_description(
            sprint_name=sprint_name,
            behavioral_items=behavioral_items,
            supporting_items=supporting_items,
            test_execution_key=test_execution_key,
        ),
        issue_type=config.overview_task_issue_type,
        labels=tuple(sorted(labels)),
        sprint_label=sprint_label,
        release_label=release_label,
        behavioral_items=behavioral_items,
        supporting_items=supporting_items,
    )


def build_regression_visibility_link_plans(
    *,
    overview_task_key: str,
    config: RegressionVisibilityConfig,
    test_execution_key: str = "",
    test_case_keys: tuple[str, ...] = (),
) -> tuple[RegressionVisibilityLinkPlan, ...]:
    """Plan Jira links from the overview Task to execution and Test Case artifacts."""

    _validate_config(config)
    overview_task_key = _require_text("overview_task_key", overview_task_key)
    targets: list[str] = []
    if test_execution_key.strip():
        targets.append(test_execution_key.strip())
    targets.extend(_unique_texts("test_case_keys", test_case_keys))
    if not targets:
        raise RegressionVisibilityError("at least one Test execution or Test Case key is required")
    return tuple(
        RegressionVisibilityLinkPlan(
            source_issue_key=overview_task_key,
            target_issue_key=target,
            link_type=config.overview_link_type,
            relationship="relates to",
        )
        for target in targets
    )


def _validate_config(config: RegressionVisibilityConfig) -> None:
    _require_text("project_key", config.project_key)
    _require_text("overview_task_issue_type", config.overview_task_issue_type)
    _require_text("test_case_issue_type", config.test_case_issue_type)
    _require_text("test_execution_issue_type", config.test_execution_issue_type)
    _require_text("overview_link_type", config.overview_link_type)
    _require_text("behavioral_label", config.behavioral_label)
    _require_text("supporting_label", config.supporting_label)
    _require_text("overview_label", config.overview_label)
    if not config.board_excluded_issue_types:
        raise RegressionVisibilityError("board_excluded_issue_types is required")
    for index, issue_type in enumerate(config.board_excluded_issue_types):
        _require_text(f"board_excluded_issue_types[{index}]", issue_type)


def _validate_items(
    items: tuple[RegressionVisibilityItem, ...],
    expected_category: RegressionVisibilityCategory,
) -> None:
    for index, item in enumerate(items):
        _require_text(f"items[{index}].key", item.key)
        _require_text(f"items[{index}].summary", item.summary)
        if item.category is not expected_category:
            raise RegressionVisibilityError(
                f"items[{index}].category must be {expected_category.value}"
            )


def _render_overview_description(
    *,
    sprint_name: str,
    behavioral_items: tuple[RegressionVisibilityItem, ...],
    supporting_items: tuple[RegressionVisibilityItem, ...],
    test_execution_key: str,
) -> str:
    lines = [
        f"Regression overview for {sprint_name}.",
        "",
        "Board visibility:",
        "- This Task is visible on the Scrum board.",
        "- AgileTest Test execution and Test Case artifacts remain linked records.",
        "",
    ]
    if test_execution_key.strip():
        lines.extend(["Test execution:", f"- {test_execution_key.strip()}", ""])
    lines.append("Behavioral regression:")
    lines.extend(_render_item_lines(behavioral_items) or ["- None"])
    lines.extend(["", "Supporting validation:"])
    lines.extend(_render_item_lines(supporting_items) or ["- None"])
    return "\n".join(lines)


def _render_item_lines(items: tuple[RegressionVisibilityItem, ...]) -> list[str]:
    lines: list[str] = []
    for item in items:
        source = f" covers {item.source_issue_key}" if item.source_issue_key else ""
        automation = " automated" if item.automated else " manual"
        evidence = f" evidence {item.evidence_path}" if item.evidence_path else ""
        lines.append(f"- {item.key}: {item.summary}{source};{automation}{evidence}")
    return lines


def _unique_texts(name: str, values: tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for index, value in enumerate(values):
        text = _require_text(f"{name}[{index}]", value)
        if text not in seen:
            normalized.append(text)
            seen.add(text)
    return tuple(normalized)


def _require_text(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RegressionVisibilityError(f"{name} is required")
    return value.strip()
