"""Tester Agent manual Test issue workflow."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum


TESTER_PASSED_STORY_STATUS = "TEST COMPLETED"
DEFAULT_TEST_CASE_STATUS = "FUNNEL"
AGILETEST_LINK_TYPE = "AgileTest"
AGILETEST_LINK_OUTWARD = "tests"


class ManualTestResultStatus(str, Enum):
    """Manual test execution result statuses."""

    NOT_RUN = "not-run"
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"


class RegressionClassification(str, Enum):
    """Labels used for regression planning."""

    ONE_TIME_VALIDATION = "one-time-validation"
    REGRESSION_CANDIDATE = "regression-candidate"
    SMOKE_REGRESSION = "smoke-regression"
    RELEASE_REGRESSION = "release-regression"
    AUTOMATED_CANDIDATE = "automated-candidate"
    AUTOMATED_COVERED = "automated-covered"
    MANUAL_ONLY = "manual-only"


@dataclass(frozen=True)
class ManualTestStep:
    """One manual test step."""

    index: int
    action: str
    expected_result: str


@dataclass(frozen=True)
class ManualTestCasePlan:
    """Plan for creating or updating a Jira Test issue."""

    story_key: str
    summary: str
    manual_steps: tuple[ManualTestStep, ...]
    regression_labels: tuple[RegressionClassification, ...]
    test_issue_key: str = ""
    covered_issue_key: str = ""
    issue_type: str = "Test"
    status: str = DEFAULT_TEST_CASE_STATUS
    agiletest_case_type: str = "Manual"
    evidence_required: bool = True


@dataclass(frozen=True)
class ManualTestExecutionResult:
    """Manual execution result for a Test Case in a Test Execution/Cycle context."""

    story_key: str
    test_issue_key: str
    status: ManualTestResultStatus
    tester_role: str
    executed_at: str
    evidence_path: str = ""
    test_execution_key: str = ""
    test_cycle_key: str = ""
    failed_acceptance_criteria: tuple[str, ...] = ()
    notes: str = ""


@dataclass(frozen=True)
class ManualTestWorkflowIssue:
    """Validation issue for manual test workflow plans/results."""

    field: str
    message: str


@dataclass(frozen=True)
class ManualTestIssueFields:
    """Jira fields for creating or updating a Test issue."""

    summary: str
    description: str
    issue_type: str
    labels: tuple[str, ...]
    status: str


@dataclass(frozen=True)
class TestCaseCoverageEvidence:
    """Inspectable coverage evidence attached to one Jira Test Case."""

    __test__ = False

    test_issue_key: str
    covered_issue_key: str
    has_manual_steps: bool = False
    has_automated_coverage: bool = False


@dataclass(frozen=True)
class TestCaseCoverageDecision:
    """Decision for whether tested work has enough Test Case coverage."""

    __test__ = False

    covered_issue_key: str
    allowed: bool
    reusable_test_case_required: bool
    blockers: tuple[str, ...] = ()
    reusable_test_case_keys: tuple[str, ...] = ()
    one_time_validation_exempt: bool = False


@dataclass(frozen=True)
class AgileTestLinkPlan:
    """Plan for linking a Test Case to the covered Story/Bug."""

    link_type: str
    outward_relationship: str
    test_issue_key: str
    covered_issue_key: str


@dataclass(frozen=True)
class ManualTestBugPlan:
    """Bug creation plan emitted when failed testing is configured to create bugs."""

    summary: str
    description: str
    story_key: str
    test_issue_key: str
    failed_acceptance_criteria: tuple[str, ...]


class ManualTestWorkflowError(ValueError):
    """Raised when manual test workflow input is invalid."""

    def __init__(self, issues: Sequence[ManualTestWorkflowIssue]) -> None:
        self.issues = tuple(issues)
        super().__init__(format_manual_test_workflow_issues(self.issues))


def validate_manual_test_case_plan(plan: ManualTestCasePlan) -> list[ManualTestWorkflowIssue]:
    """Validate a manual Test Case plan."""

    issues: list[ManualTestWorkflowIssue] = []
    _require_text(issues, "story_key", plan.story_key)
    _require_text(issues, "summary", plan.summary)
    _require_text(issues, "issue_type", plan.issue_type)
    _require_text(issues, "status", plan.status)
    _require_text(issues, "agiletest_case_type", plan.agiletest_case_type)
    if not plan.manual_steps:
        issues.append(ManualTestWorkflowIssue("manual_steps", "At least one manual test step is required."))
    for index, step in enumerate(plan.manual_steps):
        if step.index <= 0:
            issues.append(ManualTestWorkflowIssue(f"manual_steps[{index}].index", "Step index must be positive."))
        _require_text(issues, f"manual_steps[{index}].action", step.action)
        _require_text(issues, f"manual_steps[{index}].expected_result", step.expected_result)
    if not plan.regression_labels:
        issues.append(
            ManualTestWorkflowIssue(
                "regression_labels",
                "At least one regression classification label is required.",
            )
        )
    return issues


def require_valid_manual_test_case_plan(plan: ManualTestCasePlan) -> ManualTestCasePlan:
    """Raise when a manual Test Case plan is invalid."""

    issues = validate_manual_test_case_plan(plan)
    if issues:
        raise ManualTestWorkflowError(issues)
    return plan


def validate_test_case_coverage_evidence(
    evidence: TestCaseCoverageEvidence,
) -> list[ManualTestWorkflowIssue]:
    """Validate reusable Test Case coverage evidence."""

    issues: list[ManualTestWorkflowIssue] = []
    _require_text(issues, "test_issue_key", evidence.test_issue_key)
    _require_text(issues, "covered_issue_key", evidence.covered_issue_key)
    if not evidence.has_manual_steps and not evidence.has_automated_coverage:
        issues.append(
            ManualTestWorkflowIssue(
                "coverage",
                "Coverage evidence must include manual steps or automated coverage.",
            )
        )
    return issues


def require_valid_test_case_coverage_evidence(
    evidence: TestCaseCoverageEvidence,
) -> TestCaseCoverageEvidence:
    """Raise when Test Case coverage evidence is invalid."""

    issues = validate_test_case_coverage_evidence(evidence)
    if issues:
        raise ManualTestWorkflowError(issues)
    return evidence


def validate_manual_test_execution_result(result: ManualTestExecutionResult) -> list[ManualTestWorkflowIssue]:
    """Validate a manual Test execution result."""

    issues: list[ManualTestWorkflowIssue] = []
    _require_text(issues, "story_key", result.story_key)
    _require_text(issues, "test_issue_key", result.test_issue_key)
    _require_text(issues, "tester_role", result.tester_role)
    _require_text(issues, "executed_at", result.executed_at)
    if result.status != ManualTestResultStatus.NOT_RUN and not result.test_execution_key:
        issues.append(
            ManualTestWorkflowIssue(
                "test_execution_key",
                "Executed manual test results must reference a Test Execution context.",
            )
        )
    if result.status == ManualTestResultStatus.FAILED and not result.failed_acceptance_criteria:
        issues.append(
            ManualTestWorkflowIssue(
                "failed_acceptance_criteria",
                "Failed manual tests must list failed acceptance criteria.",
            )
        )
    return issues


def require_valid_manual_test_execution_result(
    result: ManualTestExecutionResult,
) -> ManualTestExecutionResult:
    """Raise when a manual Test execution result is invalid."""

    issues = validate_manual_test_execution_result(result)
    if issues:
        raise ManualTestWorkflowError(issues)
    return result


def manual_test_case_labels(plan: ManualTestCasePlan) -> tuple[str, ...]:
    """Return Jira labels for a manual Test issue."""

    require_valid_manual_test_case_plan(plan)
    labels = {label.value for label in plan.regression_labels}
    labels.add("agiletest-test-case")
    labels.add("manual-test")
    return tuple(sorted(labels))


def manual_test_case_description(plan: ManualTestCasePlan) -> str:
    """Render manual Test issue description."""

    require_valid_manual_test_case_plan(plan)
    covered_key = plan.covered_issue_key or plan.story_key
    lines = [
        f"Covers: {covered_key}",
        f"AgileTest Test Case Type: {plan.agiletest_case_type}",
        "",
        "Manual steps:",
    ]
    for step in plan.manual_steps:
        lines.append(f"{step.index}. {step.action}")
        lines.append(f"   Expected: {step.expected_result}")
    lines.extend(
        [
            "",
            "Regression classifications:",
            ", ".join(label.value for label in plan.regression_labels),
        ]
    )
    return "\n".join(lines).strip()


def coverage_evidence_from_manual_test_case_plan(
    plan: ManualTestCasePlan,
) -> TestCaseCoverageEvidence:
    """Convert a manual Test Case plan into inspectable coverage evidence."""

    require_valid_manual_test_case_plan(plan)
    if not plan.test_issue_key:
        raise ManualTestWorkflowError(
            [ManualTestWorkflowIssue("test_issue_key", "Linked Test Case key is required for coverage evidence.")]
        )
    covered_key = plan.covered_issue_key or plan.story_key
    return TestCaseCoverageEvidence(
        test_issue_key=plan.test_issue_key,
        covered_issue_key=covered_key,
        has_manual_steps=bool(plan.manual_steps),
        has_automated_coverage=False,
    )


def jira_test_issue_fields_for_plan(plan: ManualTestCasePlan) -> ManualTestIssueFields:
    """Build Jira Test issue fields from a manual Test Case plan."""

    require_valid_manual_test_case_plan(plan)
    return ManualTestIssueFields(
        summary=plan.summary,
        description=manual_test_case_description(plan),
        issue_type=plan.issue_type,
        labels=manual_test_case_labels(plan),
        status=plan.status,
    )


def evaluate_test_case_coverage(
    *,
    covered_issue_key: str,
    linked_test_case_keys: tuple[str, ...],
    coverage_evidence: tuple[TestCaseCoverageEvidence, ...] = (),
    one_time_validation_labeled: bool = False,
    one_time_validation_explained: bool = False,
) -> TestCaseCoverageDecision:
    """Evaluate whether work is ready for TEST COMPLETED coverage requirements."""

    issues: list[ManualTestWorkflowIssue] = []
    _require_text(issues, "covered_issue_key", covered_issue_key)
    if issues:
        raise ManualTestWorkflowError(issues)

    normalized_linked_keys = tuple(sorted({key.strip() for key in linked_test_case_keys if key.strip()}))

    if one_time_validation_labeled:
        blockers: list[str] = []
        if not one_time_validation_explained:
            blockers.append(
                "One-time-validation stories may skip reusable Test Case creation only when evidence explains why."
            )
        return TestCaseCoverageDecision(
            covered_issue_key=covered_issue_key.strip(),
            allowed=not blockers,
            reusable_test_case_required=False,
            blockers=tuple(blockers),
            one_time_validation_exempt=not blockers,
        )

    blockers = []
    if not normalized_linked_keys:
        blockers.append("At least one linked AgileTest-style Test Case is required before TEST COMPLETED.")

    valid_evidence: list[TestCaseCoverageEvidence] = []
    for item in coverage_evidence:
        require_valid_test_case_coverage_evidence(item)
        if item.covered_issue_key != covered_issue_key.strip():
            continue
        if item.test_issue_key not in normalized_linked_keys:
            continue
        valid_evidence.append(item)

    if normalized_linked_keys and not valid_evidence:
        blockers.append(
            "Linked Test Case coverage must include scenario steps or automated coverage mapping before TEST COMPLETED."
        )

    return TestCaseCoverageDecision(
        covered_issue_key=covered_issue_key.strip(),
        allowed=not blockers,
        reusable_test_case_required=True,
        blockers=tuple(blockers),
        reusable_test_case_keys=tuple(item.test_issue_key for item in valid_evidence),
    )


def agiletest_link_plan_for_test_case(plan: ManualTestCasePlan) -> AgileTestLinkPlan:
    """Build AgileTest-style link plan for a Test Case and covered issue."""

    require_valid_manual_test_case_plan(plan)
    if not plan.test_issue_key:
        raise ManualTestWorkflowError(
            [ManualTestWorkflowIssue("test_issue_key", "Existing or created Test issue key is required for linking.")]
        )
    covered_key = plan.covered_issue_key or plan.story_key
    return AgileTestLinkPlan(
        link_type=AGILETEST_LINK_TYPE,
        outward_relationship=AGILETEST_LINK_OUTWARD,
        test_issue_key=plan.test_issue_key,
        covered_issue_key=covered_key,
    )


def render_manual_test_execution_comment(result: ManualTestExecutionResult) -> str:
    """Render Jira comment text for manual Test execution evidence."""

    require_valid_manual_test_execution_result(result)
    lines = [
        f"Manual test execution recorded for {result.story_key}.",
        "",
        f"Test Case: {result.test_issue_key}",
        f"Result: {result.status.value}",
        f"Tester role: {result.tester_role}",
        f"Executed at: {result.executed_at}",
    ]
    if result.test_execution_key:
        lines.append(f"Test Execution: {result.test_execution_key}")
    if result.test_cycle_key:
        lines.append(f"Test Cycle: {result.test_cycle_key}")
    if result.evidence_path:
        lines.append(f"Evidence: {result.evidence_path}")
    if result.failed_acceptance_criteria:
        lines.extend(["", "Failed acceptance criteria:"])
        lines.extend(f"- {criterion}" for criterion in result.failed_acceptance_criteria)
    if result.notes:
        lines.extend(["", result.notes])
    return "\n".join(lines).strip()


def bug_plan_for_failed_manual_test(
    result: ManualTestExecutionResult,
    *,
    create_bug: bool,
) -> ManualTestBugPlan | None:
    """Return a bug plan when failed manual tests should create a Jira Bug."""

    require_valid_manual_test_execution_result(result)
    if not create_bug or result.status != ManualTestResultStatus.FAILED:
        return None
    description = render_manual_test_execution_comment(result)
    return ManualTestBugPlan(
        summary=f"Failed manual test for {result.story_key}",
        description=description,
        story_key=result.story_key,
        test_issue_key=result.test_issue_key,
        failed_acceptance_criteria=result.failed_acceptance_criteria,
    )


def story_status_after_passed_manual_testing() -> str:
    """Return target Jira story status after passed manual testing."""

    return TESTER_PASSED_STORY_STATUS


def format_manual_test_workflow_issues(issues: Sequence[ManualTestWorkflowIssue]) -> str:
    """Format manual test workflow validation issues."""

    return "; ".join(f"{issue.field}: {issue.message}" for issue in issues)


def _require_text(issues: list[ManualTestWorkflowIssue], field: str, value: str) -> None:
    if not value.strip():
        issues.append(ManualTestWorkflowIssue(field, "Value is required."))
