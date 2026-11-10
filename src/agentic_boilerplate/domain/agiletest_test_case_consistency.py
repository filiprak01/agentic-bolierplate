"""Consistency validation for reusable AgileTest Test Cases."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from agentic_boilerplate.domain.regression_classification import (
    DEFAULT_REGRESSION_CLASSIFICATION_LABELS,
)
from agentic_boilerplate.domain.regression_manifest import AutomatedCoverageReference
from agentic_boilerplate.domain.tester_manual_test_workflow import (
    ManualTestStep,
    RegressionClassification,
)


class TestCaseExecutionMode(str, Enum):
    """How a reusable Test Case is expected to execute."""

    __test__ = False

    MANUAL = "manual"
    AUTOMATED = "automated"


class TestCaseConsistencyFindingType(str, Enum):
    """Categories of consistency findings for reusable Test Cases."""

    __test__ = False

    WRONG_PROJECT_KEY = "wrong-project-key"
    WRONG_ISSUE_TYPE = "wrong-issue-type"
    MISSING_AGILETEST_LABEL = "missing-agiletest-label"
    MISSING_RELEASE_LABEL = "missing-release-label"
    MISSING_SPRINT_LABEL = "missing-sprint-label"
    MISSING_REGRESSION_LABEL = "missing-regression-label"
    MISSING_MANUAL_LABEL = "missing-manual-label"
    MISSING_AUTOMATED_LABEL = "missing-automated-label"
    MISSING_SCENARIO = "missing-scenario"
    MISSING_PRECONDITIONS = "missing-preconditions"
    MISSING_STEPS = "missing-steps"
    MISSING_EXPECTED_RESULT = "missing-expected-result"
    MISSING_EVIDENCE_REFERENCE = "missing-evidence-reference"
    MISSING_COMMAND_REFERENCE = "missing-command-reference"


@dataclass(frozen=True)
class AgileTestTestCaseConsistencyConfig:
    """Project-configurable rules for reusable AgileTest Test Case validation."""

    project_key: str
    test_issue_type: str = "Test"
    agiletest_labels: tuple[str, ...] = ("agiletest-test-case",)
    release_label_prefixes: tuple[str, ...] = ("release-",)
    sprint_label_prefixes: tuple[str, ...] = ("mvp-sprint-", "sprint-ring-")
    regression_labels: tuple[str, ...] = (
        "regression-candidate",
        "smoke-regression",
        "release-regression",
    )
    manual_labels: tuple[str, ...] = ("manual-test", "manual-only")
    automated_labels: tuple[str, ...] = ("automated-candidate", "automated-covered")


@dataclass(frozen=True)
class AgileTestTestCaseSnapshot:
    """Normalized reusable Test Case metadata inspected before regression planning."""

    test_issue_key: str
    project_key: str
    issue_type: str
    summary: str
    labels: tuple[str, ...]
    execution_mode: TestCaseExecutionMode
    scenario: str = ""
    preconditions: tuple[str, ...] = ()
    steps: tuple[ManualTestStep, ...] = ()
    evidence_references: tuple[str, ...] = ()
    command_references: tuple[AutomatedCoverageReference, ...] = ()
    covered_issue_key: str = ""
    reusable: bool = True


@dataclass(frozen=True)
class TestCaseConsistencyFinding:
    """One validation finding for a reusable Test Case."""

    finding_type: TestCaseConsistencyFindingType
    field: str
    message: str


@dataclass(frozen=True)
class AgileTestTestCaseConsistencyResult:
    """Validation result for one reusable Test Case."""

    test_issue_key: str
    findings: tuple[TestCaseConsistencyFinding, ...]
    matched_release_labels: tuple[str, ...] = ()
    matched_sprint_labels: tuple[str, ...] = ()
    matched_regression_labels: tuple[str, ...] = ()

    @property
    def ready_for_regression(self) -> bool:
        return not self.findings


@dataclass(frozen=True)
class AgileTestTestCaseConsistencyBatchResult:
    """Readiness view across multiple reusable Test Cases."""

    results: tuple[AgileTestTestCaseConsistencyResult, ...]

    @property
    def ready_for_regression(self) -> bool:
        return all(result.ready_for_regression for result in self.results)

    @property
    def blocked_test_case_keys(self) -> tuple[str, ...]:
        return tuple(result.test_issue_key for result in self.results if not result.ready_for_regression)


class AgileTestTestCaseConsistencyError(ValueError):
    """Raised when validator input or configuration is invalid."""


def default_agiletest_test_case_consistency_config(
    *,
    project_key: str,
    test_issue_type: str = "Test",
) -> AgileTestTestCaseConsistencyConfig:
    """Build the default reusable Test Case consistency configuration."""

    regression_labels = tuple(
        DEFAULT_REGRESSION_CLASSIFICATION_LABELS[classification]
        for classification in (
            RegressionClassification.REGRESSION_CANDIDATE,
            RegressionClassification.SMOKE_REGRESSION,
            RegressionClassification.RELEASE_REGRESSION,
        )
    )
    return require_valid_agiletest_test_case_consistency_config(
        AgileTestTestCaseConsistencyConfig(
            project_key=project_key,
            test_issue_type=test_issue_type,
            regression_labels=regression_labels,
        )
    )


def require_valid_agiletest_test_case_consistency_config(
    config: AgileTestTestCaseConsistencyConfig,
) -> AgileTestTestCaseConsistencyConfig:
    """Validate reusable Test Case consistency configuration."""

    _require_text("project_key", config.project_key)
    _require_text("test_issue_type", config.test_issue_type)
    _require_non_empty_texts("agiletest_labels", config.agiletest_labels)
    _require_non_empty_texts("release_label_prefixes", config.release_label_prefixes)
    _require_non_empty_texts("sprint_label_prefixes", config.sprint_label_prefixes)
    _require_non_empty_texts("regression_labels", config.regression_labels)
    _require_non_empty_texts("manual_labels", config.manual_labels)
    _require_non_empty_texts("automated_labels", config.automated_labels)
    return config


def require_valid_agiletest_test_case_snapshot(
    test_case: AgileTestTestCaseSnapshot,
) -> AgileTestTestCaseSnapshot:
    """Validate reusable Test Case snapshot input."""

    _require_text("test_issue_key", test_case.test_issue_key)
    _require_text("project_key", test_case.project_key)
    _require_text("issue_type", test_case.issue_type)
    _require_text("summary", test_case.summary)
    if not isinstance(test_case.execution_mode, TestCaseExecutionMode):
        raise AgileTestTestCaseConsistencyError(
            "execution_mode must be TestCaseExecutionMode"
        )
    for index, label in enumerate(test_case.labels):
        _require_text(f"labels[{index}]", label)
    for index, precondition in enumerate(test_case.preconditions):
        _require_text(f"preconditions[{index}]", precondition)
    for index, step in enumerate(test_case.steps):
        if step.index <= 0:
            raise AgileTestTestCaseConsistencyError(
                f"steps[{index}].index must be positive"
            )
        _require_text(f"steps[{index}].action", step.action)
    for index, evidence in enumerate(test_case.evidence_references):
        _require_text(f"evidence_references[{index}]", evidence)
    for index, reference in enumerate(test_case.command_references):
        _require_text(f"command_references[{index}].command", reference.command)
        _require_text(f"command_references[{index}].test_file", reference.test_file)
        if reference.test_function:
            _require_text(
                f"command_references[{index}].test_function",
                reference.test_function,
            )
    return test_case


def assess_agiletest_test_case_consistency(
    *,
    test_case: AgileTestTestCaseSnapshot,
    config: AgileTestTestCaseConsistencyConfig,
) -> AgileTestTestCaseConsistencyResult:
    """Assess one reusable Test Case before release regression planning."""

    test_case = require_valid_agiletest_test_case_snapshot(test_case)
    config = require_valid_agiletest_test_case_consistency_config(config)
    labels = {label.strip() for label in test_case.labels}
    findings: list[TestCaseConsistencyFinding] = []

    if test_case.project_key != config.project_key:
        findings.append(
            TestCaseConsistencyFinding(
                finding_type=TestCaseConsistencyFindingType.WRONG_PROJECT_KEY,
                field="project_key",
                message=(
                    f"{test_case.test_issue_key} belongs to project "
                    f"{test_case.project_key}, expected {config.project_key}."
                ),
            )
        )
    if test_case.issue_type != config.test_issue_type:
        findings.append(
            TestCaseConsistencyFinding(
                finding_type=TestCaseConsistencyFindingType.WRONG_ISSUE_TYPE,
                field="issue_type",
                message=(
                    f"{test_case.test_issue_key} uses issue type "
                    f"{test_case.issue_type}, expected {config.test_issue_type}."
                ),
            )
        )

    matched_release_labels = _matching_prefixed_labels(
        labels,
        config.release_label_prefixes,
        excluded=config.regression_labels,
    )
    matched_sprint_labels = _matching_prefixed_labels(
        labels, config.sprint_label_prefixes
    )
    matched_regression_labels = tuple(
        sorted(label for label in labels if label in config.regression_labels)
    )

    if not _contains_any(labels, config.agiletest_labels):
        findings.append(
            TestCaseConsistencyFinding(
                finding_type=TestCaseConsistencyFindingType.MISSING_AGILETEST_LABEL,
                field="labels",
                message=(
                    f"{test_case.test_issue_key} is missing an AgileTest Test Case "
                    "label."
                ),
            )
        )

    if test_case.reusable and not matched_release_labels:
        findings.append(
            TestCaseConsistencyFinding(
                finding_type=TestCaseConsistencyFindingType.MISSING_RELEASE_LABEL,
                field="labels",
                message=(
                    f"{test_case.test_issue_key} is missing a release label with one "
                    f"of the configured prefixes: {', '.join(config.release_label_prefixes)}."
                ),
            )
        )
    if test_case.reusable and not matched_sprint_labels:
        findings.append(
            TestCaseConsistencyFinding(
                finding_type=TestCaseConsistencyFindingType.MISSING_SPRINT_LABEL,
                field="labels",
                message=(
                    f"{test_case.test_issue_key} is missing a sprint label with one "
                    f"of the configured prefixes: {', '.join(config.sprint_label_prefixes)}."
                ),
            )
        )
    if test_case.reusable and not matched_regression_labels:
        findings.append(
            TestCaseConsistencyFinding(
                finding_type=TestCaseConsistencyFindingType.MISSING_REGRESSION_LABEL,
                field="labels",
                message=(
                    f"{test_case.test_issue_key} is missing a reusable regression "
                    "classification label."
                ),
            )
        )

    if test_case.execution_mode is TestCaseExecutionMode.MANUAL:
        if not _contains_any(labels, config.manual_labels):
            findings.append(
                TestCaseConsistencyFinding(
                    finding_type=TestCaseConsistencyFindingType.MISSING_MANUAL_LABEL,
                    field="labels",
                    message=(
                        f"{test_case.test_issue_key} is marked manual but lacks a "
                        "manual coverage label."
                    ),
                )
            )
        if not test_case.evidence_references:
            findings.append(
                TestCaseConsistencyFinding(
                    finding_type=TestCaseConsistencyFindingType.MISSING_EVIDENCE_REFERENCE,
                    field="evidence_references",
                    message=(
                        f"{test_case.test_issue_key} is missing a manual evidence "
                        "reference."
                    ),
                )
            )
    if test_case.execution_mode is TestCaseExecutionMode.AUTOMATED:
        if not _contains_any(labels, config.automated_labels):
            findings.append(
                TestCaseConsistencyFinding(
                    finding_type=TestCaseConsistencyFindingType.MISSING_AUTOMATED_LABEL,
                    field="labels",
                    message=(
                        f"{test_case.test_issue_key} is marked automated but lacks an "
                        "automated coverage label."
                    ),
                )
            )
        if not test_case.command_references:
            findings.append(
                TestCaseConsistencyFinding(
                    finding_type=TestCaseConsistencyFindingType.MISSING_COMMAND_REFERENCE,
                    field="command_references",
                    message=(
                        f"{test_case.test_issue_key} is missing an automated command "
                        "or test-file reference."
                    ),
                )
            )

    if not test_case.scenario.strip():
        findings.append(
            TestCaseConsistencyFinding(
                finding_type=TestCaseConsistencyFindingType.MISSING_SCENARIO,
                field="scenario",
                message=f"{test_case.test_issue_key} is missing a scenario summary.",
            )
        )
    if not test_case.preconditions:
        findings.append(
            TestCaseConsistencyFinding(
                finding_type=TestCaseConsistencyFindingType.MISSING_PRECONDITIONS,
                field="preconditions",
                message=f"{test_case.test_issue_key} is missing preconditions.",
            )
        )
    if not test_case.steps:
        findings.append(
            TestCaseConsistencyFinding(
                finding_type=TestCaseConsistencyFindingType.MISSING_STEPS,
                field="steps",
                message=f"{test_case.test_issue_key} is missing test steps.",
            )
        )
    for step in test_case.steps:
        if not step.expected_result.strip():
            findings.append(
                TestCaseConsistencyFinding(
                    finding_type=TestCaseConsistencyFindingType.MISSING_EXPECTED_RESULT,
                    field=f"steps[{step.index}]",
                    message=(
                        f"{test_case.test_issue_key} step {step.index} is missing an "
                        "expected result."
                    ),
                )
            )
            break

    return AgileTestTestCaseConsistencyResult(
        test_issue_key=test_case.test_issue_key,
        findings=tuple(findings),
        matched_release_labels=matched_release_labels,
        matched_sprint_labels=matched_sprint_labels,
        matched_regression_labels=matched_regression_labels,
    )


def assess_release_regression_test_case_consistency(
    *,
    test_cases: tuple[AgileTestTestCaseSnapshot, ...],
    config: AgileTestTestCaseConsistencyConfig,
) -> AgileTestTestCaseConsistencyBatchResult:
    """Assess multiple reusable Test Cases before suite preparation."""

    config = require_valid_agiletest_test_case_consistency_config(config)
    if not test_cases:
        raise AgileTestTestCaseConsistencyError("test_cases is required")
    return AgileTestTestCaseConsistencyBatchResult(
        results=tuple(
            assess_agiletest_test_case_consistency(test_case=test_case, config=config)
            for test_case in test_cases
        )
    )


def render_agiletest_test_case_consistency_result(
    result: AgileTestTestCaseConsistencyResult,
) -> str:
    """Render one reusable Test Case consistency result."""

    lines = [
        f"# AgileTest Test Case Consistency - {result.test_issue_key}",
        "",
        f"- Ready for regression: {'yes' if result.ready_for_regression else 'no'}",
        f"- Release labels: {', '.join(result.matched_release_labels) or 'missing'}",
        f"- Sprint labels: {', '.join(result.matched_sprint_labels) or 'missing'}",
        f"- Regression labels: {', '.join(result.matched_regression_labels) or 'missing'}",
        "",
        "## Findings",
    ]
    if not result.findings:
        lines.append("- None")
    else:
        lines.extend(f"- {finding.message}" for finding in result.findings)
    return "\n".join(lines)


def render_agiletest_test_case_consistency_batch_result(
    result: AgileTestTestCaseConsistencyBatchResult,
) -> str:
    """Render multi-Test Case consistency readiness for release preparation."""

    if not result.results:
        raise AgileTestTestCaseConsistencyError("result.results is required")
    lines = [
        "# AgileTest Test Case Consistency Summary",
        "",
        f"- Ready for regression: {'yes' if result.ready_for_regression else 'no'}",
        f"- Blocked Test Cases: {', '.join(result.blocked_test_case_keys) or 'none'}",
        "",
        "## Test Cases",
    ]
    for case_result in result.results:
        lines.append(
            f"- {case_result.test_issue_key}: "
            f"{'ready' if case_result.ready_for_regression else 'blocked'}"
        )
    return "\n".join(lines)


def _contains_any(labels: set[str], expected: tuple[str, ...]) -> bool:
    return any(label in labels for label in expected)


def _matching_prefixed_labels(
    labels: set[str],
    prefixes: tuple[str, ...],
    *,
    excluded: tuple[str, ...] = (),
) -> tuple[str, ...]:
    excluded_labels = set(excluded)
    return tuple(
        sorted(
            label
            for label in labels
            if label not in excluded_labels
            if any(label.startswith(prefix) for prefix in prefixes)
        )
    )


def _require_non_empty_texts(name: str, values: Sequence[str]) -> None:
    if not values:
        raise AgileTestTestCaseConsistencyError(f"{name} is required")
    for index, value in enumerate(values):
        _require_text(f"{name}[{index}]", value)


def _require_text(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AgileTestTestCaseConsistencyError(f"{name} is required")
    return value.strip()
