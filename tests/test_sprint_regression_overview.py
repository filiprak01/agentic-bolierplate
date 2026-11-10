from datetime import datetime, timezone

import pytest

from agentic_boilerplate.domain import (
    RegressionBoardFilterPlan,
    RegressionOverviewTaskPlan,
    RegressionVisibilityCategory,
    RegressionVisibilityConfig,
    RegressionVisibilityError,
    RegressionVisibilityItem,
    SprintRegressionOverviewError,
    SprintRegressionOverviewWarningType,
    build_sprint_regression_overview_plan,
    render_sprint_regression_overview_jira_comment,
    render_sprint_regression_overview_plan,
)
from agentic_boilerplate.storage import write_sprint_regression_overview_plan


def test_sprint_regression_overview_plan_combines_board_task_filter_and_links() -> None:
    plan = build_sprint_regression_overview_plan(
        sprint_name="Sprint 11",
        release_label="release-mvp",
        sprint_label="mvp-sprint-11",
        config=RegressionVisibilityConfig(project_key="AGENT"),
        behavioral_items=(
            RegressionVisibilityItem(
                key="AGENT-302",
                summary="Regression classification workflow",
                category=RegressionVisibilityCategory.BEHAVIORAL_REGRESSION,
                source_issue_key="AGENT-85",
                evidence_path="data/agent-logs/REGRESSION-S11/regression-evidence.md",
                automated=True,
            ),
        ),
        supporting_items=(
            RegressionVisibilityItem(
                key="AGENT-400",
                summary="Schema-only validation",
                category=RegressionVisibilityCategory.SUPPORTING_VALIDATION,
                source_issue_key="AGENT-133",
            ),
        ),
        test_execution_key="AGENT-401",
        manifest_key="REGRESSION-S11",
        manifest_path="data/agent-logs/REGRESSION-S11/regression-manifest.md",
        evidence_path="data/agent-logs/REGRESSION-S11/regression-evidence.md",
    )

    assert plan.overview_task_plan.summary == "Sprint 11 Regression Overview"
    assert plan.overview_task_plan.issue_type == "Task"
    assert plan.board_filter_plan.jql == (
        'project = AGENT AND issuetype not in ("Test", "Test execution", "Test cycle", '
        '"Test script", "Test session") ORDER BY Rank ASC'
    )
    assert plan.test_execution_key == "AGENT-401"
    assert plan.manifest_key == "REGRESSION-S11"
    assert plan.ready_for_publication is True
    assert [link.target_issue_key for link in plan.link_plans] == ["AGENT-401", "AGENT-302", "AGENT-400"]
    assert "AGENT-401" in render_sprint_regression_overview_plan(plan)
    assert "AGENT-401" in render_sprint_regression_overview_jira_comment(plan)


def test_sprint_regression_overview_plan_warns_when_publication_inputs_are_missing() -> None:
    plan = build_sprint_regression_overview_plan(
        sprint_name="Sprint 11",
        release_label="release-mvp",
        sprint_label="mvp-sprint-11",
        config=RegressionVisibilityConfig(project_key="AGENT"),
        behavioral_items=(
            RegressionVisibilityItem(
                key="AGENT-302",
                summary="Regression classification workflow",
                category=RegressionVisibilityCategory.BEHAVIORAL_REGRESSION,
            ),
        ),
    )

    assert {warning.warning_type for warning in plan.warnings} == {
        SprintRegressionOverviewWarningType.MISSING_MANIFEST_KEY,
        SprintRegressionOverviewWarningType.MISSING_MANIFEST_PATH,
        SprintRegressionOverviewWarningType.MISSING_EVIDENCE_PATH,
        SprintRegressionOverviewWarningType.MISSING_TEST_EXECUTION_KEY,
    }
    assert plan.ready_for_publication is False


def test_sprint_regression_overview_requires_at_least_one_item() -> None:
    with pytest.raises(SprintRegressionOverviewError) as exc_info:
        build_sprint_regression_overview_plan(
            sprint_name="Sprint 11",
            release_label="release-mvp",
            sprint_label="mvp-sprint-11",
            config=RegressionVisibilityConfig(project_key="AGENT"),
        )

    assert "At least one behavioral or supporting regression item is required." in str(exc_info.value)


def test_sprint_regression_overview_writes_timestamped_markdown(tmp_path) -> None:
    plan = build_sprint_regression_overview_plan(
        sprint_name="Sprint 11",
        release_label="release-mvp",
        sprint_label="mvp-sprint-11",
        config=RegressionVisibilityConfig(project_key="AGENT"),
        behavioral_items=(
            RegressionVisibilityItem(
                key="AGENT-302",
                summary="Regression classification workflow",
                category=RegressionVisibilityCategory.BEHAVIORAL_REGRESSION,
            ),
        ),
        test_execution_key="AGENT-401",
        manifest_key="REGRESSION-S11",
        manifest_path="data/agent-logs/REGRESSION-S11/regression-manifest.md",
        evidence_path="data/agent-logs/REGRESSION-S11/regression-evidence.md",
    )

    path = write_sprint_regression_overview_plan(
        plan,
        tmp_path,
        created_at=datetime(2026, 7, 6, tzinfo=timezone.utc),
    )

    assert path.name == "sprint-regression-overview-sprint-11-20260706T000000Z.md"
    assert "Sprint: Sprint 11" in path.read_text(encoding="utf-8")


def test_sprint_regression_overview_rejects_invalid_config() -> None:
    with pytest.raises(SprintRegressionOverviewError):
        build_sprint_regression_overview_plan(
            sprint_name="Sprint 11",
            release_label="release-mvp",
            sprint_label="mvp-sprint-11",
            config=RegressionVisibilityConfig(project_key="", board_excluded_issue_types=()),
            behavioral_items=(
                RegressionVisibilityItem(
                    key="AGENT-302",
                    summary="Regression classification workflow",
                    category=RegressionVisibilityCategory.BEHAVIORAL_REGRESSION,
                ),
            ),
        )
