from agentic_boilerplate.domain import (
    AgileTestArtifactType,
    AgileTestMappingConfig,
    RegressionClassification,
    RegressionClassificationConfig,
    RegressionClassificationError,
    build_agiletest_mapping_plan,
    build_release_regression_scope_query,
    classify_test_issue,
    default_regression_classification_config,
    regression_classification_config_from_dict,
    regression_classification_config_to_dict,
    regression_scope_query_to_jql,
)


def test_classify_test_issue_adds_configured_regression_labels() -> None:
    test_issue = classify_test_issue(
        test_issue_key="AGENT-289",
        summary="Release Manager scope selection regression",
        covered_issue_key="AGENT-52",
        classifications=(
            RegressionClassification.REGRESSION_CANDIDATE,
            RegressionClassification.RELEASE_REGRESSION,
        ),
        existing_labels=("agiletest-test-case",),
    )

    assert test_issue.labels == (
        "agiletest-test-case",
        "regression-candidate",
        "release-regression",
    )


def test_classification_label_mapping_is_project_configurable() -> None:
    config = default_regression_classification_config()
    config.label_by_classification[RegressionClassification.RELEASE_REGRESSION] = "client-release-suite"

    test_issue = classify_test_issue(
        test_issue_key="AGENT-293",
        summary="Release branch workflow regression",
        covered_issue_key="AGENT-53",
        classifications=(RegressionClassification.RELEASE_REGRESSION,),
        config=config,
    )

    assert test_issue.labels == ("client-release-suite",)


def test_release_regression_scope_query_renders_jql_with_release_and_sprint_labels() -> None:
    query = build_release_regression_scope_query(
        project_key="AGENT",
        release_label="release-mvp",
        sprint_label="mvp-sprint-09",
    )

    jql = regression_scope_query_to_jql(query)

    assert jql == (
        'project = AGENT AND issuetype = Test AND labels in '
        '("mvp-sprint-09", "regression-candidate", "release-mvp", '
        '"release-regression", "smoke-regression") ORDER BY key ASC'
    )


def test_one_time_validation_requires_explicit_query_opt_in() -> None:
    try:
        build_release_regression_scope_query(
            project_key="AGENT",
            release_label="release-mvp",
            classification_filters=(RegressionClassification.ONE_TIME_VALIDATION,),
        )
    except RegressionClassificationError as error:
        assert "include_one_time_validations must be true" in str(error)
    else:
        raise AssertionError("Expected one-time validation filter to require opt-in")


def test_agiletest_mapping_disabled_returns_warning_without_mappings() -> None:
    test_issue = classify_test_issue(
        test_issue_key="AGENT-297",
        summary="Hotfix workflow regression",
        covered_issue_key="AGENT-54",
        classifications=(RegressionClassification.RELEASE_REGRESSION,),
    )

    plan = build_agiletest_mapping_plan(
        classified_tests=(test_issue,),
        config=AgileTestMappingConfig(enabled=False),
    )

    assert plan.enabled is False
    assert plan.mappings == ()
    assert plan.warnings == ("AgileTest mapping is disabled for this project.",)


def test_agiletest_mapping_plan_preserves_jira_links_when_enabled() -> None:
    test_issue = classify_test_issue(
        test_issue_key="AGENT-297",
        summary="Hotfix workflow regression",
        covered_issue_key="AGENT-54",
        classifications=(RegressionClassification.RELEASE_REGRESSION,),
    )

    plan = build_agiletest_mapping_plan(
        classified_tests=(test_issue,),
        config=AgileTestMappingConfig(enabled=True),
    )

    assert plan.enabled is True
    assert plan.warnings == ()
    assert len(plan.mappings) == 1
    mapping = plan.mappings[0]
    assert mapping.artifact_type is AgileTestArtifactType.TEST_CASE
    assert mapping.source_test_issue_key == "AGENT-297"
    assert mapping.covered_issue_key == "AGENT-54"
    assert mapping.link_type == "AgileTest"
    assert mapping.outward_relationship == "tests"


def test_agiletest_mapping_skips_one_time_validations_by_default() -> None:
    test_issue = classify_test_issue(
        test_issue_key="AGENT-300",
        summary="One-time validation",
        covered_issue_key="AGENT-85",
        classifications=(RegressionClassification.ONE_TIME_VALIDATION,),
    )

    plan = build_agiletest_mapping_plan(
        classified_tests=(test_issue,),
        config=AgileTestMappingConfig(enabled=True),
    )

    assert plan.mappings == ()
    assert plan.warnings == ("AGENT-300 is one-time validation and is not mapped by default.",)


def test_regression_classification_config_round_trips() -> None:
    config = RegressionClassificationConfig(
        label_by_classification=default_regression_classification_config().label_by_classification,
        agiletest_enabled=True,
    )

    restored = regression_classification_config_from_dict(
        regression_classification_config_to_dict(config)
    )

    assert restored == config


def test_config_must_include_all_supported_classifications() -> None:
    config = default_regression_classification_config()
    del config.label_by_classification[RegressionClassification.MANUAL_ONLY]

    try:
        classify_test_issue(
            test_issue_key="AGENT-297",
            summary="Hotfix workflow regression",
            covered_issue_key="AGENT-54",
            classifications=(RegressionClassification.RELEASE_REGRESSION,),
            config=config,
        )
    except RegressionClassificationError as error:
        assert "manual-only" in str(error)
    else:
        raise AssertionError("Expected incomplete mapping config to fail")
