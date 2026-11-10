"""MVP release E2E scenario map and release gate planning."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from enum import Enum


class ReleaseE2EError(ValueError):
    """Raised when release E2E scenario map input is incomplete."""


class ReleaseE2EOwnerRole(str, Enum):
    """Role that owns a release E2E scenario."""

    PRODUCT_OWNER = "product-owner"
    RELEASE_MANAGER = "release-manager"
    TESTER = "tester"
    DEVELOPER = "developer"
    REVIEW = "review"
    ORCHESTRATOR = "orchestrator"


class ReleaseE2EEvidenceType(str, Enum):
    """Evidence expected from a release E2E scenario."""

    JIRA_COMMENT = "jira-comment"
    LOCAL_MARKDOWN = "local-markdown"
    AGILETEST_EXECUTION = "agiletest-execution"
    COMMAND_OUTPUT = "command-output"
    CONFLUENCE_PAGE = "confluence-page"


class ReleaseE2EFailureSeverity(str, Enum):
    """Release impact when an E2E scenario fails."""

    BLOCKS_RELEASE = "blocks-release"
    REQUIRES_PO_WAIVER = "requires-po-waiver"
    NON_BLOCKING = "non-blocking"


class ReleaseE2ECheckType(str, Enum):
    """Distinguish release E2E checks from lower-level validation."""

    RELEASE_E2E = "release-e2e"
    SPRINT_REGRESSION = "sprint-regression"
    UNIT_INTEGRATION = "unit-integration"


@dataclass(frozen=True)
class ReleaseE2EScenarioStep:
    """One executable step in a release E2E scenario."""

    action: str
    expected_result: str


@dataclass(frozen=True)
class ReleaseE2EScenario:
    """One release-wide E2E scenario planned before release execution."""

    scenario_id: str
    title: str
    check_type: ReleaseE2ECheckType
    owner_role: ReleaseE2EOwnerRole
    preconditions: tuple[str, ...]
    steps: tuple[ReleaseE2EScenarioStep, ...]
    expected_result: str
    evidence_type: ReleaseE2EEvidenceType
    agiletest_test_case_expectation: str
    mapped_jira_issue_keys: tuple[str, ...] = ()
    failure_severity: ReleaseE2EFailureSeverity = ReleaseE2EFailureSeverity.BLOCKS_RELEASE
    excluded_from_release_gate: bool = False


@dataclass(frozen=True)
class ReleaseE2EFailureRule:
    """How failed release E2E scenarios affect release readiness."""

    severity: ReleaseE2EFailureSeverity
    blocks_release: bool
    bug_link_rule: str
    required_action: str


@dataclass(frozen=True)
class ReleaseE2EGate:
    """Release gate for the full MVP E2E scenario map."""

    release_key: str
    release_version: str
    gate_issue_key: str
    required_status: str
    failure_rules: tuple[ReleaseE2EFailureRule, ...]


@dataclass(frozen=True)
class ReleaseE2EScenarioMap:
    """PO-visible scenario map for release E2E validation."""

    release_key: str
    release_version: str
    generated_at: str
    implementation_scope_status: str
    scenarios: tuple[ReleaseE2EScenario, ...]
    release_gate: ReleaseE2EGate
    excluded_checks: tuple[str, ...] = ()

    @property
    def release_e2e_scenarios(self) -> tuple[ReleaseE2EScenario, ...]:
        return tuple(s for s in self.scenarios if s.check_type is ReleaseE2ECheckType.RELEASE_E2E)


def build_default_mvp_release_e2e_scenarios() -> tuple[ReleaseE2EScenario, ...]:
    """Return the default MVP release E2E scenario set from backlog to release readiness."""

    return (
        ReleaseE2EScenario(
            scenario_id="REL-E2E-001",
            title="Approved backlog and sprint scope become eligible worker assignments",
            check_type=ReleaseE2ECheckType.RELEASE_E2E,
            owner_role=ReleaseE2EOwnerRole.RELEASE_MANAGER,
            preconditions=(
                "PO-approved stories exist in READY TO START.",
                "Dependency links are represented in Jira.",
            ),
            steps=(
                ReleaseE2EScenarioStep(
                    action="Build or inspect release-manager scope selection for the approved sprint.",
                    expected_result="Only dependency-eligible issues are selected for worker assignment.",
                ),
                ReleaseE2EScenarioStep(
                    action="Confirm blocked stories remain excluded until prerequisites are complete.",
                    expected_result="Blocked stories are visible with a blocker reason.",
                ),
            ),
            expected_result="Release scope can move from PO-approved backlog to eligible worker assignments.",
            evidence_type=ReleaseE2EEvidenceType.LOCAL_MARKDOWN,
            agiletest_test_case_expectation="Reusable AgileTest Test Case covers release scope eligibility.",
            mapped_jira_issue_keys=("AGENT-354",),
        ),
        ReleaseE2EScenario(
            scenario_id="REL-E2E-002",
            title="Developer implementation, review, merge, and PR visibility complete as one flow",
            check_type=ReleaseE2ECheckType.RELEASE_E2E,
            owner_role=ReleaseE2EOwnerRole.REVIEW,
            preconditions=(
                "A developer story has subtasks and a feature branch.",
                "PR checks are available.",
            ),
            steps=(
                ReleaseE2EScenarioStep(
                    action="Inspect developer subtask, branch, PR, and review artifacts.",
                    expected_result="The story has traceable subtasks, PR link, review result, and merge reference.",
                ),
                ReleaseE2EScenarioStep(
                    action="Confirm conflict handling is reported to the developer instead of treated as a product bug.",
                    expected_result="Review findings distinguish conflict rework from behavioral bugs.",
                ),
            ),
            expected_result="Implementation can be traced from Jira story through merged PR.",
            evidence_type=ReleaseE2EEvidenceType.JIRA_COMMENT,
            agiletest_test_case_expectation="Reusable AgileTest Test Case covers PR visibility and review gate.",
            mapped_jira_issue_keys=("AGENT-138",),
        ),
        ReleaseE2EScenario(
            scenario_id="REL-E2E-003",
            title="Tester failure creates linked bug and routes story back to development",
            check_type=ReleaseE2ECheckType.RELEASE_E2E,
            owner_role=ReleaseE2EOwnerRole.TESTER,
            preconditions=(
                "A merged story is in DEV COMPLETED or IN TESTING.",
                "Manual test criteria exist for the story.",
            ),
            steps=(
                ReleaseE2EScenarioStep(
                    action="Run or inspect a failed manual test workflow.",
                    expected_result="A Bug is created and linked to the story.",
                ),
                ReleaseE2EScenarioStep(
                    action="Confirm the original story returns to DEV COMPLETED with bug-related marking.",
                    expected_result="Developer rework is visible and not stuck in testing.",
                ),
            ),
            expected_result="Failed testing creates actionable developer rework with linked bug evidence.",
            evidence_type=ReleaseE2EEvidenceType.LOCAL_MARKDOWN,
            agiletest_test_case_expectation="Reusable AgileTest Test Case covers failed manual QA routing.",
            mapped_jira_issue_keys=("AGENT-49",),
        ),
        ReleaseE2EScenario(
            scenario_id="REL-E2E-004",
            title="Sprint regression evidence, retro, and closure publish before release readiness",
            check_type=ReleaseE2ECheckType.RELEASE_E2E,
            owner_role=ReleaseE2EOwnerRole.RELEASE_MANAGER,
            preconditions=(
                "All sprint stories are accepted or explicitly waived by PO.",
                "Regression overview task exists for the sprint.",
            ),
            steps=(
                ReleaseE2EScenarioStep(
                    action="Inspect regression evidence, retro note, closure note, and performance record.",
                    expected_result="All sprint-end artifacts are present and linked from Jira.",
                ),
                ReleaseE2EScenarioStep(
                    action="Confirm sprint closure happens only after PO acceptance and regression.",
                    expected_result="Sprint closure gate blocks premature retro/closure completion.",
                ),
            ),
            expected_result="Release readiness includes visible regression and sprint-end ceremony artifacts.",
            evidence_type=ReleaseE2EEvidenceType.CONFLUENCE_PAGE,
            agiletest_test_case_expectation="Reusable AgileTest Test Case covers sprint-end release readiness.",
            mapped_jira_issue_keys=("AGENT-244", "AGENT-245"),
        ),
    )


def build_default_mvp_release_e2e_gate(
    *,
    release_key: str,
    release_version: str,
    gate_issue_key: str,
) -> ReleaseE2EGate:
    """Build the default MVP release E2E gate."""

    return ReleaseE2EGate(
        release_key=_require_text("release_key", release_key),
        release_version=_require_text("release_version", release_version),
        gate_issue_key=_require_text("gate_issue_key", gate_issue_key),
        required_status="PO approved release E2E execution",
        failure_rules=(
            ReleaseE2EFailureRule(
                severity=ReleaseE2EFailureSeverity.BLOCKS_RELEASE,
                blocks_release=True,
                bug_link_rule="Create or link a Bug to the failed scenario and release execution overview.",
                required_action="Fix, retest, and rerun the failed E2E scenario before release.",
            ),
            ReleaseE2EFailureRule(
                severity=ReleaseE2EFailureSeverity.REQUIRES_PO_WAIVER,
                blocks_release=True,
                bug_link_rule="Create or link a known limitation and require explicit PO waiver.",
                required_action="PO documents release waiver before release can proceed.",
            ),
            ReleaseE2EFailureRule(
                severity=ReleaseE2EFailureSeverity.NON_BLOCKING,
                blocks_release=False,
                bug_link_rule="Create follow-up story or bug when useful for visibility.",
                required_action="Record non-blocking evidence in release execution overview.",
            ),
        ),
    )


def build_release_e2e_scenario_map(
    *,
    release_key: str,
    release_version: str,
    generated_at: str,
    implementation_scope_status: str,
    scenarios: tuple[ReleaseE2EScenario, ...],
    release_gate: ReleaseE2EGate,
    excluded_checks: tuple[str, ...] = (),
) -> ReleaseE2EScenarioMap:
    """Build a validated release E2E scenario map."""

    _require_text("release_key", release_key)
    _require_text("release_version", release_version)
    _require_text("generated_at", generated_at)
    _require_text("implementation_scope_status", implementation_scope_status)
    if not scenarios:
        raise ReleaseE2EError("scenarios is required")
    for scenario in scenarios:
        _validate_scenario(scenario)
    _validate_release_gate(release_gate)
    if release_gate.release_key.strip() != release_key.strip():
        raise ReleaseE2EError("release_gate.release_key must match release_key")
    if release_gate.release_version.strip() != release_version.strip():
        raise ReleaseE2EError("release_gate.release_version must match release_version")
    if not any(s.check_type is ReleaseE2ECheckType.RELEASE_E2E for s in scenarios):
        raise ReleaseE2EError("at least one release-e2e scenario is required")
    return ReleaseE2EScenarioMap(
        release_key=release_key.strip(),
        release_version=release_version.strip(),
        generated_at=generated_at.strip(),
        implementation_scope_status=implementation_scope_status.strip(),
        scenarios=scenarios,
        release_gate=release_gate,
        excluded_checks=_unique_texts("excluded_checks", excluded_checks),
    )


def approve_release_e2e_scenario_map(
    scenario_map: ReleaseE2EScenarioMap,
    *,
    approved_by: str,
) -> ReleaseE2EScenarioMap:
    """Mark scenario map as PO-approved for release E2E execution."""

    _validate_scenario_map(scenario_map)
    approver = _require_text("approved_by", approved_by)
    return replace(
        scenario_map,
        implementation_scope_status=f"approved for release E2E by {approver}",
    )


def render_release_e2e_scenario_map_markdown(scenario_map: ReleaseE2EScenarioMap) -> str:
    """Render the release E2E scenario map for PO review or Confluence."""

    _validate_scenario_map(scenario_map)
    lines = [
        f"# Release E2E Scenario Map - {scenario_map.release_key}",
        "",
        f"- Version: {scenario_map.release_version}",
        f"- Generated at: {scenario_map.generated_at}",
        f"- Implementation scope status: {scenario_map.implementation_scope_status}",
        f"- Gate issue: {scenario_map.release_gate.gate_issue_key}",
        f"- Required status: {scenario_map.release_gate.required_status}",
        "",
        "## Scenarios",
    ]
    for scenario in scenario_map.scenarios:
        lines.extend(
            [
                f"### {scenario.scenario_id}: {scenario.title}",
                f"- Check type: {scenario.check_type.value}",
                f"- Owner: {scenario.owner_role.value}",
                f"- Evidence: {scenario.evidence_type.value}",
                f"- Failure severity: {scenario.failure_severity.value}",
                f"- AgileTest expectation: {scenario.agiletest_test_case_expectation}",
                f"- Mapped Jira: {', '.join(scenario.mapped_jira_issue_keys) or 'not set'}",
                "- Preconditions:",
            ]
        )
        lines.extend(f"  - {precondition}" for precondition in scenario.preconditions)
        lines.append("- Steps:")
        for index, step in enumerate(scenario.steps, start=1):
            lines.append(f"  {index}. {step.action}")
            lines.append(f"     Expected: {step.expected_result}")
        lines.append(f"- Expected result: {scenario.expected_result}")
        lines.append("")
    lines.extend(["## Release Gate Failure Rules"])
    for rule in scenario_map.release_gate.failure_rules:
        lines.extend(
            [
                f"- {rule.severity.value}",
                f"  - Blocks release: {'yes' if rule.blocks_release else 'no'}",
                f"  - Bug link rule: {rule.bug_link_rule}",
                f"  - Required action: {rule.required_action}",
            ]
        )
    lines.extend(["", "## Excluded Checks"])
    if scenario_map.excluded_checks:
        lines.extend(f"- {check}" for check in scenario_map.excluded_checks)
    else:
        lines.append("- None")
    return "\n".join(lines).strip()


def release_blocking_failure_rules(gate: ReleaseE2EGate) -> tuple[ReleaseE2EFailureRule, ...]:
    """Return failure rules that block release readiness."""

    _validate_release_gate(gate)
    return tuple(rule for rule in gate.failure_rules if rule.blocks_release)


def _validate_scenario_map(scenario_map: ReleaseE2EScenarioMap) -> None:
    build_release_e2e_scenario_map(
        release_key=scenario_map.release_key,
        release_version=scenario_map.release_version,
        generated_at=scenario_map.generated_at,
        implementation_scope_status=scenario_map.implementation_scope_status,
        scenarios=scenario_map.scenarios,
        release_gate=scenario_map.release_gate,
        excluded_checks=scenario_map.excluded_checks,
    )


def _validate_scenario(scenario: ReleaseE2EScenario) -> None:
    _require_text("scenario.scenario_id", scenario.scenario_id)
    _require_text("scenario.title", scenario.title)
    _require_text("scenario.expected_result", scenario.expected_result)
    _require_text("scenario.agiletest_test_case_expectation", scenario.agiletest_test_case_expectation)
    if not isinstance(scenario.check_type, ReleaseE2ECheckType):
        raise ReleaseE2EError("scenario.check_type must be ReleaseE2ECheckType")
    if not isinstance(scenario.owner_role, ReleaseE2EOwnerRole):
        raise ReleaseE2EError("scenario.owner_role must be ReleaseE2EOwnerRole")
    if not isinstance(scenario.evidence_type, ReleaseE2EEvidenceType):
        raise ReleaseE2EError("scenario.evidence_type must be ReleaseE2EEvidenceType")
    if not isinstance(scenario.failure_severity, ReleaseE2EFailureSeverity):
        raise ReleaseE2EError("scenario.failure_severity must be ReleaseE2EFailureSeverity")
    _unique_texts("scenario.preconditions", scenario.preconditions)
    if not scenario.steps:
        raise ReleaseE2EError("scenario.steps is required")
    for step in scenario.steps:
        _require_text("scenario.steps.action", step.action)
        _require_text("scenario.steps.expected_result", step.expected_result)
    _unique_texts("scenario.mapped_jira_issue_keys", scenario.mapped_jira_issue_keys)


def _validate_release_gate(gate: ReleaseE2EGate) -> None:
    _require_text("gate.release_key", gate.release_key)
    _require_text("gate.release_version", gate.release_version)
    _require_text("gate.gate_issue_key", gate.gate_issue_key)
    _require_text("gate.required_status", gate.required_status)
    if not gate.failure_rules:
        raise ReleaseE2EError("gate.failure_rules is required")
    for rule in gate.failure_rules:
        if not isinstance(rule.severity, ReleaseE2EFailureSeverity):
            raise ReleaseE2EError("rule.severity must be ReleaseE2EFailureSeverity")
        _require_text("rule.bug_link_rule", rule.bug_link_rule)
        _require_text("rule.required_action", rule.required_action)


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
        raise ReleaseE2EError(f"{name} is required")
    return value.strip()
