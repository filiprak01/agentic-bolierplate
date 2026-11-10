from pathlib import Path

from agentic_boilerplate.domain import build_automated_coverage_mapping
from agentic_boilerplate.storage import (
    COVERAGE_MAPPING_FILE,
    FileCoverageMappingStore,
    InvalidCoverageMappingKeyError,
)


def test_file_store_writes_and_reads_mapping_at_deterministic_path(tmp_path: Path) -> None:
    store = FileCoverageMappingStore(tmp_path)
    mapping = build_automated_coverage_mapping(
        test_case_key="AGENT-322",
        covered_issue_key="AGENT-84",
        command="PYTHONPATH=src python -m pytest -q tests/test_test_evidence_artifact.py",
        test_file="tests/test_test_evidence_artifact.py",
        test_function="test_render_test_evidence_markdown_redacts_secret_values",
        source_sprint="mvp-sprint-09",
    )

    location = store.write(mapping)
    restored = store.read("AGENT-322")

    assert location.path == tmp_path / "AGENT-322" / COVERAGE_MAPPING_FILE
    assert location.path.is_file()
    assert restored == mapping


def test_file_store_lists_mappings_in_stable_order(tmp_path: Path) -> None:
    store = FileCoverageMappingStore(tmp_path)
    second = build_automated_coverage_mapping(
        test_case_key="AGENT-322",
        covered_issue_key="AGENT-84",
        command="PYTHONPATH=src python -m pytest -q tests/test_test_evidence_artifact.py",
        test_file="tests/test_test_evidence_artifact.py",
    )
    first = build_automated_coverage_mapping(
        test_case_key="AGENT-314",
        covered_issue_key="AGENT-86",
        command="PYTHONPATH=src python -m pytest -q tests/test_agiletest_regression_suite.py",
        test_file="tests/test_agiletest_regression_suite.py",
    )

    store.write(second)
    store.write(first)

    assert tuple(mapping.test_case_key for mapping in store.list_mappings()) == ("AGENT-314", "AGENT-322")


def test_file_store_rejects_unsafe_test_case_key(tmp_path: Path) -> None:
    store = FileCoverageMappingStore(tmp_path)

    try:
        store.mapping_path("../AGENT-322")
    except InvalidCoverageMappingKeyError as error:
        assert "Test Case keys may contain" in str(error)
    else:
        raise AssertionError("Expected unsafe Test Case key to fail")
