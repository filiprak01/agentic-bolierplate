from agentic_boilerplate.domain import (
    RegressionCheckExposure,
    RegressionClassification,
    RegressionVisibilityCategory,
    RegressionVisibilityConfig,
    RegressionVisibilityError,
    build_regression_board_filter_plan,
    build_regression_overview_task_plan,
    build_regression_visibility_link_plans,
    classify_regression_visibility,
    classify_test_issue,
    regression_visibility_item_from_test_issue,
)


def test_user_and_worker_facing_checks_are_behavioral_regression() -> None:
    assert (
        classify_regression_visibility(RegressionCheckExposure.USER_FACING)
        is RegressionVisibilityCategory.BEHAVIORAL_REGRESSION
    )
    assert (
        classify_regression_visibility(RegressionCheckExposure.WORKER_FACING)
        is RegressionVisibilityCategory.BEHAVIORAL_REGRESSION
    )


def test_setup_schema_and_internal_checks_are_supporting_validation() -> None:
    assert (
        classify_regression_visibility(RegressionCheckExposure.SETUP_ONLY)
        is RegressionVisibilityCategory.SUPPORTING_VALIDATION
    )
    assert (
        classify_regression_visibility(RegressionCheckExposure.SCHEMA_ONLY)
        is RegressionVisibilityCategory.SUPPORTING_VALIDATION
    )
    assert (
        classify_regression_visibility(RegressionCheckExposure.INTERNAL_STORAGE)
        is RegressionVisibilityCategory.SUPPORTING_VALIDATION
    )


def test_regression_overview_task_plan_is_board_visible_and_labeled() -> None:
    config = RegressionVisibilityConfig(project_key="AGENT")
    behavioral = regression_visibility_item_from_test_issue(
        classify_test_issue(
            test_issue_key="AGENT-302",
            summary="Regression classification mapping",
            covered_issue_key="AGENT-85",
            classifications=(RegressionClassification.RELEASE_REGRESSION,),
        ),
        category=RegressionVisibilityCategory.BEHAVIORAL_REGRESSION,
        evidence_path="data/agent-logs/AGENT-85/test-evidence.md",
        automated=True,
    )
    supporting = regression_visibility_item_from_test_issue(
        classify_test_issue(
            test_issue_key="AGENT-400",
            summary="Schema-only validation",
            covered_issue_key="AGENT-133",
            classifications=(RegressionClassification.ONE_TIME_VALIDATION,),
        ),
        category=RegressionVisibilityCategory.SUPPORTING_VALIDATION,
    )

    plan = build_regression_overview_task_plan(
        sprint_name="Sprint 9",
        release_label="release-mvp",
        sprint_label="mvp-sprint-09",
        config=config,
        behavioral_items=(behavioral,),
        supporting_items=(supporting,),
        test_execution_key="AGENT-401",
    )

    assert plan.issue_type == "Task"
    assert plan.summary == "Sprint 9 Regression Overview"
    assert plan.labels == (
        "behavioral-regression",
        "mvp-sprint-09",
        "regression-overview",
        "release-mvp",
        "supporting-validation",
    )
    assert "AGENT-401" in plan.description
    assert "AGENT-302: Regression classification mapping covers AGENT-85; automated" in plan.description
    assert "AGENT-400: Schema-only validation covers AGENT-133; manual" in plan.description


def test_regression_visibility_link_plans_link_overview_to_execution_and_cases() -> None:
    links = build_regression_visibility_link_plans(
        overview_task_key="AGENT-500",
        config=RegressionVisibilityConfig(project_key="AGENT"),
        test_execution_key="AGENT-501",
        test_case_keys=("AGENT-302", "AGENT-302", "AGENT-400"),
    )

    assert [link.target_issue_key for link in links] == ["AGENT-501", "AGENT-302", "AGENT-400"]
    assert {link.source_issue_key for link in links} == {"AGENT-500"}
    assert {link.link_type for link in links} == {"Relates"}
    assert {link.relationship for link in links} == {"relates to"}


def test_regression_board_filter_excludes_agiletest_artifacts_from_delivery_board() -> None:
    plan = build_regression_board_filter_plan(RegressionVisibilityConfig(project_key="AGENT"))

    assert plan.excluded_issue_types == (
        "Test",
        "Test execution",
        "Test cycle",
        "Test script",
        "Test session",
    )
    assert plan.jql == (
        'project = AGENT AND issuetype not in ("Test", "Test execution", "Test cycle", '
        '"Test script", "Test session") ORDER BY Rank ASC'
    )


def test_overview_task_requires_at_least_one_visible_item() -> None:
    try:
        build_regression_overview_task_plan(
            sprint_name="Sprint 9",
            release_label="release-mvp",
            sprint_label="mvp-sprint-09",
            config=RegressionVisibilityConfig(project_key="AGENT"),
        )
    except RegressionVisibilityError as error:
        assert "at least one regression visibility item is required" in str(error)
    else:
        raise AssertionError("Expected empty overview scope to fail")
