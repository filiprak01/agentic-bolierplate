"""Configurable MVP release E2E runner and environment checklist."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from agentic_boilerplate.domain.release_e2e_scenario_map import (
    ReleaseE2ECheckType,
    ReleaseE2EScenario,
    ReleaseE2EScenarioMap,
)


class ReleaseE2ERunnerError(ValueError):
    """Raised when release E2E runner input is incomplete."""


class ReleaseE2EEnvironmentCheckStatus(str, Enum):
    """Environment checklist result."""

    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    NOT_CHECKED = "not-checked"


class ReleaseE2EScenarioExecutionMode(str, Enum):
    """How a release E2E scenario is executed."""

    AUTOMATED = "automated"
    MANUAL_ONLY = "manual-only"
    SUPPORTING_VALIDATION = "supporting-validation"


class ReleaseE2EScenarioResult(str, Enum):
    """Scenario-level release E2E execution result."""

    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"
    NOT_RUN = "not-run"


@dataclass(frozen=True)
class ReleaseE2EEnvironmentCheck:
    """One local environment readiness check before release E2E execution."""

    check_id: str
    name: str
    category: str
    status: ReleaseE2EEnvironmentCheckStatus
    required: bool = True
    details: str = ""
    remediation: str = ""


@dataclass(frozen=True)
class ReleaseE2EEnvironmentChecklist:
    """Project-configurable release E2E environment checklist."""

    project_key: str
    target_project_path: str
    checks: tuple[ReleaseE2EEnvironmentCheck, ...]

    @property
    def ready(self) -> bool:
        return not any(check.required and check.status is ReleaseE2EEnvironmentCheckStatus.FAILED for check in self.checks)


@dataclass(frozen=True)
class ReleaseE2EScenarioExecution:
    """Recorded output for one release E2E scenario."""

    scenario_id: str
    title: str
    mode: ReleaseE2EScenarioExecutionMode
    result: ReleaseE2EScenarioResult
    evidence_path: str
    notes: str = ""
    bug_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReleaseE2EExecutionReport:
    """Durable release E2E runner output."""

    release_key: str
    release_version: str
    generated_at: str
    target_project_key: str
    checklist: ReleaseE2EEnvironmentChecklist
    executions: tuple[ReleaseE2EScenarioExecution, ...]
    production_data_required: bool = False

    @property
    def passed(self) -> bool:
        if not self.checklist.ready:
            return False
        return all(execution.result is ReleaseE2EScenarioResult.PASSED for execution in self.executions)


def build_default_release_e2e_environment_checklist(
    *,
    project_key: str,
    target_project_path: str,
    jira_configured: bool,
    github_configured: bool,
    confluence_configured: bool,
    agiletest_configured: bool,
    durable_storage_configured: bool,
    local_services_ready: bool,
    sample_target_ready: bool,
) -> ReleaseE2EEnvironmentChecklist:
    """Build the default MVP release E2E environment checklist."""

    checks = (
        _check("ENV-001", "Local services", "local-services", local_services_ready, "Required local services are reachable."),
        _check("ENV-002", "Durable storage", "durable-volumes", durable_storage_configured, "Durable local paths are configured."),
        _check("ENV-003", "Jira configuration", "credentials", jira_configured, "Jira base URL, project, board, email, and token are configured."),
        _check("ENV-004", "GitHub configuration", "credentials", github_configured, "GitHub repository and token are configured."),
        _check("ENV-005", "Confluence configuration", "credentials", confluence_configured, "Confluence space and token are configured."),
        _check("ENV-006", "AgileTest configuration", "credentials", agiletest_configured, "AgileTest client and token are configured."),
        _check("ENV-007", "Sample target project", "target-project", sample_target_ready, "Sample target project is available for E2E validation."),
    )
    return ReleaseE2EEnvironmentChecklist(
        project_key=_require_text("project_key", project_key),
        target_project_path=_require_text("target_project_path", target_project_path),
        checks=checks,
    )


def build_release_e2e_execution_report(
    *,
    scenario_map: ReleaseE2EScenarioMap,
    generated_at: str,
    target_project_key: str,
    checklist: ReleaseE2EEnvironmentChecklist,
    execution_overrides: tuple[ReleaseE2EScenarioExecution, ...] = (),
) -> ReleaseE2EExecutionReport:
    """Build scenario-level E2E runner output from a scenario map."""

    _require_text("generated_at", generated_at)
    _require_text("target_project_key", target_project_key)
    _validate_checklist(checklist)
    overrides = {execution.scenario_id: execution for execution in execution_overrides}
    executions = tuple(
        overrides.get(scenario.scenario_id, _default_execution_for_scenario(scenario, checklist))
        for scenario in scenario_map.scenarios
        if scenario.check_type is ReleaseE2ECheckType.RELEASE_E2E
    )
    if not executions:
        raise ReleaseE2ERunnerError("at least one release E2E execution is required")
    for execution in executions:
        _validate_execution(execution)
    return ReleaseE2EExecutionReport(
        release_key=scenario_map.release_key,
        release_version=scenario_map.release_version,
        generated_at=generated_at.strip(),
        target_project_key=target_project_key.strip(),
        checklist=checklist,
        executions=executions,
        production_data_required=False,
    )


def render_release_e2e_execution_report(report: ReleaseE2EExecutionReport) -> str:
    """Render release E2E execution output for durable storage and Jira comments."""

    _validate_report(report)
    lines = [
        f"# Release E2E Execution - {report.release_key}",
        "",
        f"- Version: {report.release_version}",
        f"- Generated at: {report.generated_at}",
        f"- Target project: {report.target_project_key}",
        f"- Production data required: {'yes' if report.production_data_required else 'no'}",
        f"- Checklist ready: {'yes' if report.checklist.ready else 'no'}",
        f"- Passed: {'yes' if report.passed else 'no'}",
        "",
        "## Environment Checklist",
    ]
    for check in report.checklist.checks:
        required = "required" if check.required else "optional"
        lines.append(f"- {check.check_id}: {check.name} [{check.category}, {required}] -> {check.status.value}")
        if check.details:
            lines.append(f"  - Details: {check.details}")
        if check.remediation:
            lines.append(f"  - Remediation: {check.remediation}")
    lines.extend(["", "## Scenario Results"])
    for execution in report.executions:
        lines.append(f"- {execution.scenario_id}: {execution.title}")
        lines.append(f"  - Mode: {execution.mode.value}")
        lines.append(f"  - Result: {execution.result.value}")
        lines.append(f"  - Evidence: {execution.evidence_path}")
        if execution.bug_keys:
            lines.append(f"  - Bugs: {', '.join(execution.bug_keys)}")
        if execution.notes:
            lines.append(f"  - Notes: {execution.notes}")
    return "\n".join(lines).strip()


def failed_release_e2e_scenarios(report: ReleaseE2EExecutionReport) -> tuple[ReleaseE2EScenarioExecution, ...]:
    """Return failed or blocked release E2E scenarios."""

    _validate_report(report)
    return tuple(
        execution
        for execution in report.executions
        if execution.result in {ReleaseE2EScenarioResult.FAILED, ReleaseE2EScenarioResult.BLOCKED}
    )


def _check(
    check_id: str,
    name: str,
    category: str,
    passed: bool,
    details: str,
) -> ReleaseE2EEnvironmentCheck:
    return ReleaseE2EEnvironmentCheck(
        check_id=check_id,
        name=name,
        category=category,
        status=ReleaseE2EEnvironmentCheckStatus.PASSED if passed else ReleaseE2EEnvironmentCheckStatus.FAILED,
        required=True,
        details=details,
        remediation="" if passed else f"Configure {name.lower()} before release E2E execution.",
    )


def _default_execution_for_scenario(
    scenario: ReleaseE2EScenario,
    checklist: ReleaseE2EEnvironmentChecklist,
) -> ReleaseE2EScenarioExecution:
    result = ReleaseE2EScenarioResult.NOT_RUN if checklist.ready else ReleaseE2EScenarioResult.BLOCKED
    notes = "Manual-only scenario awaiting tester execution." if checklist.ready else "Environment checklist is not ready."
    return ReleaseE2EScenarioExecution(
        scenario_id=scenario.scenario_id,
        title=scenario.title,
        mode=ReleaseE2EScenarioExecutionMode.MANUAL_ONLY,
        result=result,
        evidence_path="manual-execution-pending",
        notes=notes,
    )


def _validate_report(report: ReleaseE2EExecutionReport) -> None:
    _require_text("release_key", report.release_key)
    _require_text("release_version", report.release_version)
    _require_text("generated_at", report.generated_at)
    _require_text("target_project_key", report.target_project_key)
    _validate_checklist(report.checklist)
    if not report.executions:
        raise ReleaseE2ERunnerError("executions is required")
    for execution in report.executions:
        _validate_execution(execution)


def _validate_checklist(checklist: ReleaseE2EEnvironmentChecklist) -> None:
    _require_text("checklist.project_key", checklist.project_key)
    _require_text("checklist.target_project_path", checklist.target_project_path)
    if not checklist.checks:
        raise ReleaseE2ERunnerError("checklist.checks is required")
    for check in checklist.checks:
        _require_text("check.check_id", check.check_id)
        _require_text("check.name", check.name)
        _require_text("check.category", check.category)
        if not isinstance(check.status, ReleaseE2EEnvironmentCheckStatus):
            raise ReleaseE2ERunnerError("check.status must be ReleaseE2EEnvironmentCheckStatus")


def _validate_execution(execution: ReleaseE2EScenarioExecution) -> None:
    _require_text("execution.scenario_id", execution.scenario_id)
    _require_text("execution.title", execution.title)
    _require_text("execution.evidence_path", execution.evidence_path)
    if not isinstance(execution.mode, ReleaseE2EScenarioExecutionMode):
        raise ReleaseE2ERunnerError("execution.mode must be ReleaseE2EScenarioExecutionMode")
    if not isinstance(execution.result, ReleaseE2EScenarioResult):
        raise ReleaseE2ERunnerError("execution.result must be ReleaseE2EScenarioResult")


def _require_text(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReleaseE2ERunnerError(f"{name} is required")
    return value.strip()
