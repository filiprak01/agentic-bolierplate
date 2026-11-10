"""AgileTest-style Test Case planning for MVP release E2E."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from agentic_boilerplate.domain.release_e2e_scenario_map import (
    ReleaseE2ECheckType,
    ReleaseE2EScenarioMap,
)


class ReleaseE2EAgileTestPlanError(ValueError):
    """Raised when release E2E AgileTest planning input is invalid."""


class ReleaseE2ETestStepMode(str, Enum):
    """Whether a release E2E step is manual-only or automation-capable."""

    MANUAL_ONLY = "manual-only"
    AUTOMATED_CAPABLE = "automated-capable"


@dataclass(frozen=True)
class ReleaseE2ETestStepPlan:
    """One AgileTest-style Test Case step."""

    action: str
    expected_result: str
    mode: ReleaseE2ETestStepMode


@dataclass(frozen=True)
class ReleaseE2ETestCasePlan:
    """Jira Test issue / AgileTest Test Case plan for one release E2E scenario."""

    scenario_id: str
    summary: str
    description: str
    labels: tuple[str, ...]
    preconditions: tuple[str, ...]
    steps: tuple[ReleaseE2ETestStepPlan, ...]
    expected_result: str
    owner_role: str
    evidence_expectation: str
    covered_issue_keys: tuple[str, ...]
    jira_test_issue_key: str = ""


@dataclass(frozen=True)
class ReleaseE2EExecutionPlan:
    """Release execution plan that groups E2E Test Cases for PO review."""

    release_key: str
    release_version: str
    execution_name: str
    test_cases: tuple[ReleaseE2ETestCasePlan, ...]
    overview_issue_key: str
    po_review_required: bool = True


def build_release_e2e_test_case_plans(
    scenario_map: ReleaseE2EScenarioMap,
    *,
    automated_capable_scenario_ids: tuple[str, ...] = (),
) -> tuple[ReleaseE2ETestCasePlan, ...]:
    """Build Test Case plans from the approved release E2E scenario map."""

    automated_capable = set(_unique_texts("automated_capable_scenario_ids", automated_capable_scenario_ids))
    plans: list[ReleaseE2ETestCasePlan] = []
    for scenario in scenario_map.scenarios:
        if scenario.check_type is not ReleaseE2ECheckType.RELEASE_E2E:
            continue
        step_mode = (
            ReleaseE2ETestStepMode.AUTOMATED_CAPABLE
            if scenario.scenario_id in automated_capable
            else ReleaseE2ETestStepMode.MANUAL_ONLY
        )
        plans.append(
            ReleaseE2ETestCasePlan(
                scenario_id=scenario.scenario_id,
                summary=f"{scenario.scenario_id}: {scenario.title}",
                description=(
                    f"Release E2E scenario owned by {scenario.owner_role.value}. "
                    f"Evidence expected as {scenario.evidence_type.value}."
                ),
                labels=("release-regression", "release-e2e", "manual-only" if step_mode is ReleaseE2ETestStepMode.MANUAL_ONLY else "automated-capable"),
                preconditions=scenario.preconditions,
                steps=tuple(
                    ReleaseE2ETestStepPlan(
                        action=step.action,
                        expected_result=step.expected_result,
                        mode=step_mode,
                    )
                    for step in scenario.steps
                ),
                expected_result=scenario.expected_result,
                owner_role=scenario.owner_role.value,
                evidence_expectation=scenario.agiletest_test_case_expectation,
                covered_issue_keys=scenario.mapped_jira_issue_keys,
            )
        )
    if not plans:
        raise ReleaseE2EAgileTestPlanError("at least one release E2E Test Case plan is required")
    return tuple(plans)


def build_release_e2e_execution_plan(
    *,
    release_key: str,
    release_version: str,
    execution_name: str,
    overview_issue_key: str,
    test_cases: tuple[ReleaseE2ETestCasePlan, ...],
) -> ReleaseE2EExecutionPlan:
    """Group release E2E Test Cases into an execution plan."""

    _require_text("release_key", release_key)
    _require_text("release_version", release_version)
    _require_text("execution_name", execution_name)
    _require_text("overview_issue_key", overview_issue_key)
    if not test_cases:
        raise ReleaseE2EAgileTestPlanError("test_cases is required")
    for test_case in test_cases:
        _validate_test_case_plan(test_case)
    return ReleaseE2EExecutionPlan(
        release_key=release_key.strip(),
        release_version=release_version.strip(),
        execution_name=execution_name.strip(),
        overview_issue_key=overview_issue_key.strip(),
        test_cases=test_cases,
    )


def release_e2e_test_case_description(test_case: ReleaseE2ETestCasePlan) -> str:
    """Render a Jira Test issue description for one release E2E Test Case."""

    _validate_test_case_plan(test_case)
    lines = [
        test_case.description,
        "",
        f"Scenario: {test_case.scenario_id}",
        f"Owner role: {test_case.owner_role}",
        f"Evidence expectation: {test_case.evidence_expectation}",
        f"Covers: {', '.join(test_case.covered_issue_keys) or 'release flow'}",
        "",
        "Preconditions:",
    ]
    lines.extend(f"- {precondition}" for precondition in test_case.preconditions)
    lines.extend(["", "Steps:"])
    for index, step in enumerate(test_case.steps, start=1):
        lines.append(f"{index}. [{step.mode.value}] {step.action}")
        lines.append(f"   Expected: {step.expected_result}")
    lines.extend(["", f"Expected result: {test_case.expected_result}"])
    return "\n".join(lines)


def render_release_e2e_execution_plan(plan: ReleaseE2EExecutionPlan) -> str:
    """Render release E2E execution plan for PO review."""

    _validate_execution_plan(plan)
    lines = [
        f"# Release E2E Execution Plan - {plan.release_key}",
        "",
        f"- Version: {plan.release_version}",
        f"- Execution: {plan.execution_name}",
        f"- Overview issue: {plan.overview_issue_key}",
        f"- PO review required: {'yes' if plan.po_review_required else 'no'}",
        "",
        "## Test Cases",
    ]
    for test_case in plan.test_cases:
        labels = ", ".join(test_case.labels)
        lines.append(f"- {test_case.summary}")
        lines.append(f"  - Labels: {labels}")
        lines.append(f"  - Jira Test: {test_case.jira_test_issue_key or 'to be created'}")
        lines.append(f"  - Step modes: {', '.join(sorted({step.mode.value for step in test_case.steps}))}")
    return "\n".join(lines).strip()


def _validate_execution_plan(plan: ReleaseE2EExecutionPlan) -> None:
    build_release_e2e_execution_plan(
        release_key=plan.release_key,
        release_version=plan.release_version,
        execution_name=plan.execution_name,
        overview_issue_key=plan.overview_issue_key,
        test_cases=plan.test_cases,
    )


def _validate_test_case_plan(test_case: ReleaseE2ETestCasePlan) -> None:
    _require_text("test_case.scenario_id", test_case.scenario_id)
    _require_text("test_case.summary", test_case.summary)
    _require_text("test_case.description", test_case.description)
    _require_text("test_case.expected_result", test_case.expected_result)
    _require_text("test_case.owner_role", test_case.owner_role)
    _require_text("test_case.evidence_expectation", test_case.evidence_expectation)
    labels = set(_unique_texts("test_case.labels", test_case.labels))
    if not {"release-regression", "release-e2e"}.issubset(labels):
        raise ReleaseE2EAgileTestPlanError("release E2E Test Cases require release-regression and release-e2e labels")
    _unique_texts("test_case.preconditions", test_case.preconditions)
    _unique_texts("test_case.covered_issue_keys", test_case.covered_issue_keys)
    if not test_case.steps:
        raise ReleaseE2EAgileTestPlanError("test_case.steps is required")
    for step in test_case.steps:
        _require_text("step.action", step.action)
        _require_text("step.expected_result", step.expected_result)
        if not isinstance(step.mode, ReleaseE2ETestStepMode):
            raise ReleaseE2EAgileTestPlanError("step.mode must be ReleaseE2ETestStepMode")


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
        raise ReleaseE2EAgileTestPlanError(f"{name} is required")
    return value.strip()
