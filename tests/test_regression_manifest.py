from agentic_boilerplate.domain import (
    AutomatedCoverageReference,
    RegressionClassification,
    RegressionExecutionMode,
    RegressionExecutionResult,
    RegressionManifestError,
    RegressionManifestReferences,
    build_regression_manifest,
    build_regression_manifest_record,
    classify_test_issue,
    regression_manifest_to_dict,
    render_regression_manifest_markdown,
)


def test_manifest_includes_manual_and_automated_reusable_records() -> None:
    manual_test = classify_test_issue(
        test_issue_key="AGENT-306",
        summary="Behavioral visibility workflow",
        covered_issue_key="AGENT-133",
        classifications=(RegressionClassification.RELEASE_REGRESSION,),
        existing_labels=("release-regression",),
    )
    automated_test = classify_test_issue(
        test_issue_key="AGENT-314",
        summary="AgileTest suite integration workflow",
        covered_issue_key="AGENT-86",
        classifications=(
            RegressionClassification.REGRESSION_CANDIDATE,
            RegressionClassification.AUTOMATED_COVERED,
        ),
        existing_labels=("regression-candidate", "automated-covered"),
    )

    manifest = build_regression_manifest(
        manifest_key="REGRESSION-S9",
        release_key="release-mvp",
        source_sprint="mvp-sprint-09",
        generated_at="2026-07-04T19:30:00Z",
        references=RegressionManifestReferences(
            overview_task_key="AGENT-320",
            agiletest_execution_key="AGENT-321",
        ),
        records=(
            build_regression_manifest_record(
                test_issue=manual_test,
                source_sprint="mvp-sprint-09",
                execution_mode=RegressionExecutionMode.MANUAL,
                result=RegressionExecutionResult.PASSED,
                evidence_path="data/agent-logs/REGRESSION-S9/manual.md",
            ),
            build_regression_manifest_record(
                test_issue=automated_test,
                source_sprint="mvp-sprint-09",
                execution_mode=RegressionExecutionMode.AUTOMATED,
                result=RegressionExecutionResult.PASSED,
                evidence_path="data/agent-logs/REGRESSION-S9/automated.md",
                automated_reference=AutomatedCoverageReference(
                    command="PYTHONPATH=src python -m pytest -q tests/test_agiletest_regression_suite.py",
                    test_file="tests/test_agiletest_regression_suite.py",
                    test_function="test_build_agiletest_suite_plan_from_classified_regression_tests",
                ),
            ),
        ),
    )

    assert [record.test_case_key for record in manifest.records] == ["AGENT-306", "AGENT-314"]
    assert manifest.references.overview_task_key == "AGENT-320"
    assert manifest.references.agiletest_execution_key == "AGENT-321"
    data = regression_manifest_to_dict(manifest)
    assert data["records"][1]["automated_reference"]["test_file"] == "tests/test_agiletest_regression_suite.py"


def test_automated_manifest_record_requires_command_file_or_function_mapping() -> None:
    test_issue = classify_test_issue(
        test_issue_key="AGENT-314",
        summary="AgileTest suite integration workflow",
        covered_issue_key="AGENT-86",
        classifications=(RegressionClassification.AUTOMATED_COVERED,),
        existing_labels=("automated-covered",),
    )

    try:
        build_regression_manifest_record(
            test_issue=test_issue,
            source_sprint="mvp-sprint-09",
            execution_mode=RegressionExecutionMode.AUTOMATED,
            result=RegressionExecutionResult.PASSED,
            evidence_path="data/agent-logs/REGRESSION-S9/automated.md",
            automated_reference=AutomatedCoverageReference(),
        )
    except RegressionManifestError as error:
        assert "automated_reference must include command, test_file, or test_function" in str(error)
    else:
        raise AssertionError("Expected automated record without mapping to fail")


def test_manifest_excludes_one_time_validations_by_default() -> None:
    reusable = classify_test_issue(
        test_issue_key="AGENT-314",
        summary="AgileTest suite integration workflow",
        covered_issue_key="AGENT-86",
        classifications=(RegressionClassification.RELEASE_REGRESSION,),
        existing_labels=("release-regression",),
    )
    one_time = classify_test_issue(
        test_issue_key="AGENT-999",
        summary="One-time setup validation",
        covered_issue_key="AGENT-135",
        classifications=(RegressionClassification.ONE_TIME_VALIDATION,),
        existing_labels=("one-time-validation",),
    )

    manifest = build_regression_manifest(
        manifest_key="REGRESSION-S9",
        release_key="release-mvp",
        source_sprint="mvp-sprint-09",
        generated_at="2026-07-04T19:30:00Z",
        references=RegressionManifestReferences(overview_task_key="AGENT-320"),
        records=(
            build_regression_manifest_record(
                test_issue=reusable,
                source_sprint="mvp-sprint-09",
                execution_mode=RegressionExecutionMode.MANUAL,
                result=RegressionExecutionResult.PASSED,
                evidence_path="data/agent-logs/REGRESSION-S9/reusable.md",
            ),
            build_regression_manifest_record(
                test_issue=one_time,
                source_sprint="mvp-sprint-09",
                execution_mode=RegressionExecutionMode.SUPPORTING_VALIDATION,
                result=RegressionExecutionResult.PASSED,
                evidence_path="data/agent-logs/REGRESSION-S9/setup.md",
            ),
        ),
    )

    assert [record.test_case_key for record in manifest.records] == ["AGENT-314"]


def test_manifest_markdown_references_overview_and_agiletest_execution() -> None:
    test_issue = classify_test_issue(
        test_issue_key="AGENT-314",
        summary="AgileTest suite integration workflow",
        covered_issue_key="AGENT-86",
        classifications=(RegressionClassification.RELEASE_REGRESSION,),
        existing_labels=("release-regression",),
    )
    manifest = build_regression_manifest(
        manifest_key="REGRESSION-S9",
        release_key="release-mvp",
        source_sprint="mvp-sprint-09",
        generated_at="2026-07-04T19:30:00Z",
        references=RegressionManifestReferences(
            overview_task_key="AGENT-320",
            agiletest_execution_key="AGENT-321",
        ),
        records=(
            build_regression_manifest_record(
                test_issue=test_issue,
                source_sprint="mvp-sprint-09",
                execution_mode=RegressionExecutionMode.MANUAL,
                result=RegressionExecutionResult.PASSED,
                evidence_path="data/agent-logs/REGRESSION-S9/reusable.md",
            ),
        ),
    )

    markdown = render_regression_manifest_markdown(manifest)

    assert "# Regression Manifest - REGRESSION-S9" in markdown
    assert "Overview Task: AGENT-320" in markdown
    assert "AgileTest Execution: AGENT-321" in markdown
    assert "AGENT-314 -> AGENT-86" in markdown
    assert "Evidence: data/agent-logs/REGRESSION-S9/reusable.md" in markdown
