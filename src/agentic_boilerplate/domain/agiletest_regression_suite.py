"""AgileTest regression suite planning for release readiness."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from agentic_boilerplate.domain.regression_classification import ClassifiedTestIssue
from agentic_boilerplate.domain.release_notes_regression_scope import RegressionScopeDraft
from agentic_boilerplate.domain.tester_manual_test_workflow import RegressionClassification


class AgileTestSuiteError(ValueError):
    """Raised when AgileTest suite planning input is invalid."""


class AgileTestManualSyncMode(str, Enum):
    """How MVP synchronizes AgileTest execution status."""

    DOCUMENTED_MANUAL = "documented-manual"
    COMMENT_ONLY = "comment-only"
    DISABLED = "disabled"


class AgileTestAutomationHookStatus(str, Enum):
    """Future automation hook status for a Test Case."""

    NOT_CONFIGURED = "not-configured"
    PLANNED = "planned"
    AUTOMATED_CANDIDATE = "automated-candidate"
    AUTOMATED_COVERED = "automated-covered"


@dataclass(frozen=True)
class AgileTestRegressionSuiteConfig:
    """Project-specific AgileTest regression suite settings."""

    enabled: bool
    jira_project_key: str
    agiletest_project_key: str
    client_id_env_var: str = "AGILETEST_CLIENT_ID"
    token_env_var: str = "AGILETEST_TOKEN"
    test_case_issue_type: str = "Test"
    test_cycle_issue_type: str = "Test cycle"
    test_execution_issue_type: str = "Test execution"
    manual_sync_mode: AgileTestManualSyncMode = AgileTestManualSyncMode.DOCUMENTED_MANUAL


@dataclass(frozen=True)
class AgileTestRegressionCasePlan:
    """One Test Case included in an AgileTest regression suite."""

    test_issue_key: str
    covered_issue_key: str
    summary: str
    classifications: tuple[RegressionClassification, ...]
    execution_links: tuple[str, ...]
    automation_hook_status: AgileTestAutomationHookStatus
    automation_reference: str = ""


@dataclass(frozen=True)
class AgileTestRegressionSuitePlan:
    """Release regression suite or cycle plan that adapters can execute."""

    release_key: str
    release_version: str
    cycle_name: str
    suite_name: str
    config: AgileTestRegressionSuiteConfig
    cases: tuple[AgileTestRegressionCasePlan, ...]
    release_links: tuple[str, ...]
    manual_sync_steps: tuple[str, ...]
    warnings: tuple[str, ...] = ()


def build_agiletest_regression_suite_plan(
    *,
    regression_scope: RegressionScopeDraft,
    config: AgileTestRegressionSuiteConfig,
    cycle_name: str,
    suite_name: str,
    release_links: tuple[str, ...] = (),
) -> AgileTestRegressionSuitePlan:
    """Build an AgileTest regression suite plan without live API calls."""

    _validate_config(config)
    _validate_regression_scope(regression_scope)
    cycle_name = _require_text("cycle_name", cycle_name)
    suite_name = _require_text("suite_name", suite_name)
    release_links = _unique_texts("release_links", release_links)

    cases = tuple(
        _case_plan_from_classified_test(test)
        for test in regression_scope.classified_tests
        if RegressionClassification.ONE_TIME_VALIDATION not in test.classifications
    )
    if not cases:
        raise AgileTestSuiteError("at least one reusable regression Test issue is required")

    warnings: list[str] = []
    if not config.enabled:
        warnings.append("AgileTest integration is disabled; plan can be used as Jira-only regression guidance.")
    skipped_one_time = tuple(
        test.test_issue_key
        for test in regression_scope.classified_tests
        if RegressionClassification.ONE_TIME_VALIDATION in test.classifications
    )
    for test_key in skipped_one_time:
        warnings.append(f"{test_key} is one-time validation and is excluded from the default regression suite.")

    return AgileTestRegressionSuitePlan(
        release_key=regression_scope.release_key,
        release_version=regression_scope.release_version,
        cycle_name=cycle_name,
        suite_name=suite_name,
        config=config,
        cases=cases,
        release_links=release_links,
        manual_sync_steps=manual_execution_sync_steps(config),
        warnings=tuple(warnings),
    )


def manual_execution_sync_steps(config: AgileTestRegressionSuiteConfig) -> tuple[str, ...]:
    """Return MVP manual execution sync instructions."""

    _validate_config(config)
    if config.manual_sync_mode is AgileTestManualSyncMode.DISABLED:
        return ()
    if config.manual_sync_mode is AgileTestManualSyncMode.COMMENT_ONLY:
        return (
            "Record AgileTest execution status in the Jira story or regression overview Task comment.",
            "Link evidence files and failed Bug issues from the comment.",
        )
    return (
        "Create or update the AgileTest Test Execution for the release cycle.",
        "Set each Test Case execution result manually in AgileTest.",
        "Mirror the final execution summary to the Jira regression overview Task.",
        "Create or link Jira Bugs for failed Test Case executions.",
    )


def render_agiletest_regression_suite_plan(plan: AgileTestRegressionSuitePlan) -> str:
    """Render AgileTest suite plan for Jira comments, local files, or Confluence."""

    _validate_plan(plan)
    lines = [
        f"# AgileTest Regression Suite - {plan.release_key}",
        "",
        f"- Version: {plan.release_version}",
        f"- Cycle: {plan.cycle_name}",
        f"- Suite: {plan.suite_name}",
        f"- Jira project: {plan.config.jira_project_key}",
        f"- AgileTest project: {plan.config.agiletest_project_key}",
        f"- Enabled: {'yes' if plan.config.enabled else 'no'}",
        f"- Manual sync mode: {plan.config.manual_sync_mode.value}",
        "",
        "## Release Links",
    ]
    lines.extend(f"- {link}" for link in plan.release_links) if plan.release_links else lines.append("- None")
    lines.extend(["", "## Test Cases"])
    for case in plan.cases:
        labels = ", ".join(classification.value for classification in case.classifications)
        lines.append(f"- {case.test_issue_key}: {case.summary}")
        lines.append(f"  - Covers: {case.covered_issue_key}")
        lines.append(f"  - Classifications: {labels}")
        lines.append(f"  - Automation hook: {case.automation_hook_status.value}")
        if case.automation_reference:
            lines.append(f"  - Automation reference: {case.automation_reference}")
    lines.extend(["", "## Manual Execution Sync"])
    lines.extend(f"- {step}" for step in plan.manual_sync_steps) if plan.manual_sync_steps else lines.append("- Disabled")
    if plan.warnings:
        lines.extend(["", "## Warnings"])
        lines.extend(f"- {warning}" for warning in plan.warnings)
    return "\n".join(lines)


def _case_plan_from_classified_test(test: ClassifiedTestIssue) -> AgileTestRegressionCasePlan:
    _validate_classified_test(test)
    return AgileTestRegressionCasePlan(
        test_issue_key=test.test_issue_key,
        covered_issue_key=test.covered_issue_key,
        summary=test.summary,
        classifications=test.classifications,
        execution_links=tuple(key for key in (test.agiletest_case_key,) if key),
        automation_hook_status=_automation_hook_status(test.classifications),
    )


def _automation_hook_status(
    classifications: tuple[RegressionClassification, ...],
) -> AgileTestAutomationHookStatus:
    if RegressionClassification.AUTOMATED_COVERED in classifications:
        return AgileTestAutomationHookStatus.AUTOMATED_COVERED
    if RegressionClassification.AUTOMATED_CANDIDATE in classifications:
        return AgileTestAutomationHookStatus.AUTOMATED_CANDIDATE
    return AgileTestAutomationHookStatus.NOT_CONFIGURED


def _validate_plan(plan: AgileTestRegressionSuitePlan) -> None:
    _require_text("release_key", plan.release_key)
    _require_text("release_version", plan.release_version)
    _require_text("cycle_name", plan.cycle_name)
    _require_text("suite_name", plan.suite_name)
    _validate_config(plan.config)
    if not plan.cases:
        raise AgileTestSuiteError("cases is required")
    for case in plan.cases:
        _validate_case(case)


def _validate_config(config: AgileTestRegressionSuiteConfig) -> None:
    _require_text("jira_project_key", config.jira_project_key)
    _require_text("agiletest_project_key", config.agiletest_project_key)
    _require_text("client_id_env_var", config.client_id_env_var)
    _require_text("token_env_var", config.token_env_var)
    _require_text("test_case_issue_type", config.test_case_issue_type)
    _require_text("test_cycle_issue_type", config.test_cycle_issue_type)
    _require_text("test_execution_issue_type", config.test_execution_issue_type)
    if not isinstance(config.manual_sync_mode, AgileTestManualSyncMode):
        raise AgileTestSuiteError("manual_sync_mode must be AgileTestManualSyncMode")


def _validate_regression_scope(regression_scope: RegressionScopeDraft) -> None:
    _require_text("regression_scope.release_key", regression_scope.release_key)
    _require_text("regression_scope.release_version", regression_scope.release_version)
    if not regression_scope.classified_tests:
        raise AgileTestSuiteError("regression_scope.classified_tests is required")


def _validate_case(case: AgileTestRegressionCasePlan) -> None:
    _require_text("case.test_issue_key", case.test_issue_key)
    _require_text("case.covered_issue_key", case.covered_issue_key)
    _require_text("case.summary", case.summary)
    if not case.classifications:
        raise AgileTestSuiteError("case.classifications is required")
    if not isinstance(case.automation_hook_status, AgileTestAutomationHookStatus):
        raise AgileTestSuiteError("case.automation_hook_status must be AgileTestAutomationHookStatus")


def _validate_classified_test(test: ClassifiedTestIssue) -> None:
    _require_text("test.test_issue_key", test.test_issue_key)
    _require_text("test.covered_issue_key", test.covered_issue_key)
    _require_text("test.summary", test.summary)
    if not test.classifications:
        raise AgileTestSuiteError("test.classifications is required")


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
        raise AgileTestSuiteError(f"{name} is required")
    return value.strip()
