"""Automated Test Case coverage mapping for regression manifests."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from agentic_boilerplate.domain.regression_classification import ClassifiedTestIssue
from agentic_boilerplate.domain.regression_manifest import AutomatedCoverageReference
from agentic_boilerplate.domain.regression_manifest import (
    RegressionExecutionMode,
    RegressionExecutionResult,
    RegressionManifestRecord,
    build_regression_manifest_record,
)
from agentic_boilerplate.domain.tester_manual_test_workflow import RegressionClassification


class CoverageMappingError(ValueError):
    """Raised when Test Case coverage mapping input is invalid."""


class CoverageMappingMode(str, Enum):
    """How a reusable Test Case is covered for regression."""

    AUTOMATED = "automated"
    MANUAL_ONLY = "manual-only"


class CoverageMappingWarningType(str, Enum):
    """Warning categories for release-regression readiness checks."""

    MISSING_AUTOMATED_MAPPING = "missing-automated-mapping"


@dataclass(frozen=True)
class TestCaseCoverageMapping:
    """Durable mapping between a Jira Test Case and its regression coverage."""

    test_case_key: str
    covered_issue_key: str
    mode: CoverageMappingMode
    command: str = ""
    test_file: str = ""
    test_function: str = ""
    source_sprint: str = ""
    notes: str = ""


@dataclass(frozen=True)
class CoverageMappingWarning:
    """Readiness warning for a Test Case without required coverage mapping."""

    test_case_key: str
    covered_issue_key: str
    warning_type: CoverageMappingWarningType
    message: str


@dataclass(frozen=True)
class CoverageMappingReadiness:
    """Coverage mapping readiness result for release regression planning."""

    mappings: tuple[TestCaseCoverageMapping, ...]
    warnings: tuple[CoverageMappingWarning, ...] = ()

    @property
    def is_ready(self) -> bool:
        return not self.warnings


def build_automated_coverage_mapping(
    *,
    test_case_key: str,
    covered_issue_key: str,
    command: str,
    test_file: str,
    test_function: str = "",
    source_sprint: str = "",
    notes: str = "",
) -> TestCaseCoverageMapping:
    """Build an automated coverage mapping with command and test-file metadata."""

    mapping = TestCaseCoverageMapping(
        test_case_key=_require_text("test_case_key", test_case_key),
        covered_issue_key=_require_text("covered_issue_key", covered_issue_key),
        mode=CoverageMappingMode.AUTOMATED,
        command=_require_text("command", command),
        test_file=_require_text("test_file", test_file),
        test_function=_optional_text(test_function),
        source_sprint=_optional_text(source_sprint),
        notes=_optional_text(notes),
    )
    return require_valid_coverage_mapping(mapping)


def build_manual_only_coverage_mapping(
    *,
    test_case_key: str,
    covered_issue_key: str,
    source_sprint: str = "",
    notes: str = "",
) -> TestCaseCoverageMapping:
    """Build a manual-only coverage mapping without automation metadata."""

    mapping = TestCaseCoverageMapping(
        test_case_key=_require_text("test_case_key", test_case_key),
        covered_issue_key=_require_text("covered_issue_key", covered_issue_key),
        mode=CoverageMappingMode.MANUAL_ONLY,
        source_sprint=_optional_text(source_sprint),
        notes=_optional_text(notes),
    )
    return require_valid_coverage_mapping(mapping)


def coverage_reference_from_mapping(mapping: TestCaseCoverageMapping) -> AutomatedCoverageReference:
    """Convert an automated mapping into a regression manifest coverage reference."""

    mapping = require_valid_coverage_mapping(mapping)
    if mapping.mode is not CoverageMappingMode.AUTOMATED:
        raise CoverageMappingError("coverage reference requires an automated mapping")
    return AutomatedCoverageReference(
        command=mapping.command,
        test_file=mapping.test_file,
        test_function=mapping.test_function,
    )


def build_regression_manifest_record_from_mapping(
    *,
    test_issue: ClassifiedTestIssue,
    mapping: TestCaseCoverageMapping,
    source_sprint: str,
    result: RegressionExecutionResult,
    evidence_path: str,
) -> RegressionManifestRecord:
    """Build a manifest record using automated or manual-only coverage mapping."""

    _validate_classified_test(test_issue)
    mapping = require_valid_coverage_mapping(mapping)
    if mapping.test_case_key != test_issue.test_issue_key:
        raise CoverageMappingError("mapping.test_case_key must match test_issue.test_issue_key")
    if mapping.covered_issue_key != test_issue.covered_issue_key:
        raise CoverageMappingError("mapping.covered_issue_key must match test_issue.covered_issue_key")
    if mapping.mode is CoverageMappingMode.AUTOMATED:
        return build_regression_manifest_record(
            test_issue=test_issue,
            source_sprint=source_sprint,
            execution_mode=RegressionExecutionMode.AUTOMATED,
            result=result,
            evidence_path=evidence_path,
            automated_reference=coverage_reference_from_mapping(mapping),
        )
    return build_regression_manifest_record(
        test_issue=test_issue,
        source_sprint=source_sprint,
        execution_mode=RegressionExecutionMode.MANUAL,
        result=result,
        evidence_path=evidence_path,
    )


def assess_coverage_mapping_readiness(
    *,
    classified_tests: tuple[ClassifiedTestIssue, ...],
    mappings: tuple[TestCaseCoverageMapping, ...],
) -> CoverageMappingReadiness:
    """Report missing automated mappings for reusable automated Test Cases."""

    mapping_by_key = {mapping.test_case_key: require_valid_coverage_mapping(mapping) for mapping in mappings}
    warnings: list[CoverageMappingWarning] = []
    for test in classified_tests:
        _validate_classified_test(test)
        mapping = mapping_by_key.get(test.test_issue_key)
        if RegressionClassification.MANUAL_ONLY in test.classifications:
            continue
        if _requires_automated_mapping(test) and (
            mapping is None or mapping.mode is not CoverageMappingMode.AUTOMATED
        ):
            warnings.append(
                CoverageMappingWarning(
                    test_case_key=test.test_issue_key,
                    covered_issue_key=test.covered_issue_key,
                    warning_type=CoverageMappingWarningType.MISSING_AUTOMATED_MAPPING,
                    message=(
                        f"{test.test_issue_key} is reusable automated regression coverage "
                        "but has no command/test-file mapping."
                    ),
                )
            )
    return CoverageMappingReadiness(mappings=tuple(mapping_by_key.values()), warnings=tuple(warnings))


def coverage_mapping_to_dict(mapping: TestCaseCoverageMapping) -> dict[str, object]:
    """Convert a coverage mapping to JSON-compatible data."""

    mapping = require_valid_coverage_mapping(mapping)
    return {
        "test_case_key": mapping.test_case_key,
        "covered_issue_key": mapping.covered_issue_key,
        "mode": mapping.mode.value,
        "command": mapping.command,
        "test_file": mapping.test_file,
        "test_function": mapping.test_function,
        "source_sprint": mapping.source_sprint,
        "notes": mapping.notes,
    }


def coverage_mapping_from_dict(data: dict[str, Any]) -> TestCaseCoverageMapping:
    """Build a coverage mapping from JSON-compatible data."""

    try:
        mode = CoverageMappingMode(str(data.get("mode") or ""))
    except ValueError as exc:
        raise CoverageMappingError("mode must be a valid CoverageMappingMode") from exc
    mapping = TestCaseCoverageMapping(
        test_case_key=str(data.get("test_case_key") or ""),
        covered_issue_key=str(data.get("covered_issue_key") or ""),
        mode=mode,
        command=str(data.get("command") or ""),
        test_file=str(data.get("test_file") or ""),
        test_function=str(data.get("test_function") or ""),
        source_sprint=str(data.get("source_sprint") or ""),
        notes=str(data.get("notes") or ""),
    )
    return require_valid_coverage_mapping(mapping)


def require_valid_coverage_mapping(mapping: TestCaseCoverageMapping) -> TestCaseCoverageMapping:
    """Validate and return a coverage mapping."""

    _require_text("test_case_key", mapping.test_case_key)
    _require_text("covered_issue_key", mapping.covered_issue_key)
    if not isinstance(mapping.mode, CoverageMappingMode):
        raise CoverageMappingError("mode must be CoverageMappingMode")
    if mapping.mode is CoverageMappingMode.AUTOMATED:
        _require_text("command", mapping.command)
        _require_text("test_file", mapping.test_file)
    if mapping.mode is CoverageMappingMode.MANUAL_ONLY and any(
        (mapping.command.strip(), mapping.test_file.strip(), mapping.test_function.strip())
    ):
        raise CoverageMappingError("manual-only mappings must not include automation metadata")
    return mapping


def _requires_automated_mapping(test: ClassifiedTestIssue) -> bool:
    classifications = set(test.classifications)
    automated = {
        RegressionClassification.AUTOMATED_CANDIDATE,
        RegressionClassification.AUTOMATED_COVERED,
    }
    reusable = {
        RegressionClassification.REGRESSION_CANDIDATE,
        RegressionClassification.SMOKE_REGRESSION,
        RegressionClassification.RELEASE_REGRESSION,
    }
    return bool(classifications & automated) and bool(classifications & reusable)


def _validate_classified_test(test: ClassifiedTestIssue) -> None:
    _require_text("test.test_issue_key", test.test_issue_key)
    _require_text("test.covered_issue_key", test.covered_issue_key)
    if not test.classifications:
        raise CoverageMappingError("test.classifications is required")


def _optional_text(value: object) -> str:
    return str(value or "").strip()


def _require_text(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CoverageMappingError(f"{name} is required")
    return value.strip()
