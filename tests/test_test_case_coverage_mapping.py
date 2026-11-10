from agentic_boilerplate.domain import (
    CoverageMappingError,
    CoverageMappingMode,
    CoverageMappingWarningType,
    RegressionExecutionMode,
    RegressionExecutionResult,
    RegressionClassification,
    assess_coverage_mapping_readiness,
    build_automated_coverage_mapping,
    build_manual_only_coverage_mapping,
    build_regression_manifest_record_from_mapping,
    classify_test_issue,
    coverage_mapping_from_dict,
    coverage_mapping_to_dict,
    coverage_reference_from_mapping,
)


def test_automated_mapping_stores_command_file_and_optional_function() -> None:
    mapping = build_automated_coverage_mapping(
        test_case_key="AGENT-322",
        covered_issue_key="AGENT-84",
        command="PYTHONPATH=src python -m pytest -q tests/test_test_evidence_artifact.py",
        test_file="tests/test_test_evidence_artifact.py",
        test_function="test_render_test_evidence_markdown_redacts_secret_values",
        source_sprint="mvp-sprint-09",
    )

    reference = coverage_reference_from_mapping(mapping)

    assert mapping.mode is CoverageMappingMode.AUTOMATED
    assert reference.command.startswith("PYTHONPATH=src python")
    assert reference.test_file == "tests/test_test_evidence_artifact.py"
    assert reference.test_function == "test_render_test_evidence_markdown_redacts_secret_values"


def test_automated_mapping_requires_command_and_test_file() -> None:
    try:
        build_automated_coverage_mapping(
            test_case_key="AGENT-322",
            covered_issue_key="AGENT-84",
            command="PYTHONPATH=src python -m pytest -q",
            test_file="",
        )
    except CoverageMappingError as error:
        assert "test_file is required" in str(error)
    else:
        raise AssertionError("Expected automated mapping without test_file to fail")


def test_manual_only_mapping_remains_supported_without_automation_metadata() -> None:
    mapping = build_manual_only_coverage_mapping(
        test_case_key="AGENT-300",
        covered_issue_key="AGENT-49",
        source_sprint="mvp-sprint-08",
    )

    assert mapping.mode is CoverageMappingMode.MANUAL_ONLY
    assert mapping.command == ""
    assert mapping.test_file == ""


def test_mapping_round_trips_as_durable_json_compatible_data() -> None:
    mapping = build_automated_coverage_mapping(
        test_case_key="AGENT-314",
        covered_issue_key="AGENT-86",
        command="PYTHONPATH=src python -m pytest -q tests/test_agiletest_regression_suite.py",
        test_file="tests/test_agiletest_regression_suite.py",
        source_sprint="mvp-sprint-09",
        notes="Covered by focused AgileTest suite planning tests.",
    )

    data = coverage_mapping_to_dict(mapping)
    restored = coverage_mapping_from_dict(data)

    assert data["mode"] == "automated"
    assert restored == mapping


def test_readiness_warns_when_reusable_automated_test_has_no_mapping() -> None:
    automated_test = classify_test_issue(
        test_issue_key="AGENT-322",
        summary="Test evidence artifact workflow",
        covered_issue_key="AGENT-84",
        classifications=(
            RegressionClassification.RELEASE_REGRESSION,
            RegressionClassification.AUTOMATED_COVERED,
        ),
        existing_labels=("release-regression", "automated-covered"),
    )
    manual_test = classify_test_issue(
        test_issue_key="AGENT-300",
        summary="Manual tester workflow",
        covered_issue_key="AGENT-49",
        classifications=(RegressionClassification.MANUAL_ONLY,),
        existing_labels=("manual-only",),
    )

    readiness = assess_coverage_mapping_readiness(
        classified_tests=(automated_test, manual_test),
        mappings=(),
    )

    assert not readiness.is_ready
    assert len(readiness.warnings) == 1
    assert readiness.warnings[0].warning_type is CoverageMappingWarningType.MISSING_AUTOMATED_MAPPING
    assert readiness.warnings[0].test_case_key == "AGENT-322"


def test_readiness_warns_when_automated_test_has_manual_only_mapping() -> None:
    automated_test = classify_test_issue(
        test_issue_key="AGENT-322",
        summary="Test evidence artifact workflow",
        covered_issue_key="AGENT-84",
        classifications=(
            RegressionClassification.RELEASE_REGRESSION,
            RegressionClassification.AUTOMATED_COVERED,
        ),
        existing_labels=("release-regression", "automated-covered"),
    )
    manual_mapping = build_manual_only_coverage_mapping(
        test_case_key="AGENT-322",
        covered_issue_key="AGENT-84",
    )

    readiness = assess_coverage_mapping_readiness(
        classified_tests=(automated_test,),
        mappings=(manual_mapping,),
    )

    assert not readiness.is_ready
    assert readiness.warnings[0].test_case_key == "AGENT-322"


def test_readiness_accepts_mapped_automated_and_manual_only_tests() -> None:
    automated_test = classify_test_issue(
        test_issue_key="AGENT-322",
        summary="Test evidence artifact workflow",
        covered_issue_key="AGENT-84",
        classifications=(
            RegressionClassification.RELEASE_REGRESSION,
            RegressionClassification.AUTOMATED_COVERED,
        ),
        existing_labels=("release-regression", "automated-covered"),
    )
    manual_test = classify_test_issue(
        test_issue_key="AGENT-300",
        summary="Manual tester workflow",
        covered_issue_key="AGENT-49",
        classifications=(RegressionClassification.MANUAL_ONLY,),
        existing_labels=("manual-only",),
    )
    mapping = build_automated_coverage_mapping(
        test_case_key="AGENT-322",
        covered_issue_key="AGENT-84",
        command="PYTHONPATH=src python -m pytest -q tests/test_test_evidence_artifact.py",
        test_file="tests/test_test_evidence_artifact.py",
    )

    readiness = assess_coverage_mapping_readiness(
        classified_tests=(automated_test, manual_test),
        mappings=(mapping,),
    )

    assert readiness.is_ready
    assert readiness.warnings == ()


def test_mapping_builds_automated_manifest_record_with_coverage_reference() -> None:
    test_issue = classify_test_issue(
        test_issue_key="AGENT-322",
        summary="Test evidence artifact workflow",
        covered_issue_key="AGENT-84",
        classifications=(
            RegressionClassification.RELEASE_REGRESSION,
            RegressionClassification.AUTOMATED_COVERED,
        ),
        existing_labels=("release-regression", "automated-covered"),
    )
    mapping = build_automated_coverage_mapping(
        test_case_key="AGENT-322",
        covered_issue_key="AGENT-84",
        command="PYTHONPATH=src python -m pytest -q tests/test_test_evidence_artifact.py",
        test_file="tests/test_test_evidence_artifact.py",
        test_function="test_render_test_evidence_markdown_redacts_secret_values",
    )

    record = build_regression_manifest_record_from_mapping(
        test_issue=test_issue,
        mapping=mapping,
        source_sprint="mvp-sprint-09",
        result=RegressionExecutionResult.PASSED,
        evidence_path="data/agent-logs/REGRESSION-S9/evidence.md",
    )

    assert record.execution_mode is RegressionExecutionMode.AUTOMATED
    assert record.automated_reference is not None
    assert record.automated_reference.test_file == "tests/test_test_evidence_artifact.py"


def test_mapping_builds_manual_manifest_record_for_manual_only_test() -> None:
    test_issue = classify_test_issue(
        test_issue_key="AGENT-300",
        summary="Manual tester workflow",
        covered_issue_key="AGENT-49",
        classifications=(RegressionClassification.MANUAL_ONLY,),
        existing_labels=("manual-only",),
    )
    mapping = build_manual_only_coverage_mapping(
        test_case_key="AGENT-300",
        covered_issue_key="AGENT-49",
    )

    record = build_regression_manifest_record_from_mapping(
        test_issue=test_issue,
        mapping=mapping,
        source_sprint="mvp-sprint-08",
        result=RegressionExecutionResult.PASSED,
        evidence_path="data/agent-logs/REGRESSION-S8/manual.md",
    )

    assert record.execution_mode is RegressionExecutionMode.MANUAL
    assert record.automated_reference is None
