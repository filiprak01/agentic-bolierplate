"""Recursive sprint dependency co-scheduling guard."""

from __future__ import annotations

from dataclasses import dataclass


class SprintDependencyCoSchedulingError(ValueError):
    """Raised when dependency co-scheduling input is invalid."""


@dataclass(frozen=True)
class SprintDependencyIssue:
    """Issue snapshot used by sprint dependency planning."""

    issue_key: str
    status: str
    sprint_labels: tuple[str, ...] = ()
    merged_to_main: bool = False


@dataclass(frozen=True)
class SprintDependencyLink:
    """Dependency link where blocker_key blocks dependent_key."""

    blocker_key: str
    dependent_key: str


@dataclass(frozen=True)
class SprintDependencyPlanningError:
    """Blocking planning error for an unresolved blocker outside the sprint."""

    dependent_issue_key: str
    missing_blocker_key: str
    dependency_chain: tuple[str, ...]
    message: str


@dataclass(frozen=True)
class SprintDependencyCorrectionPlan:
    """Prerequisite issues that must be added before scope can remain valid."""

    sprint_label: str
    required_issue_keys: tuple[str, ...]


@dataclass(frozen=True)
class SprintDependencyCoSchedulingResult:
    """Recursive sprint dependency co-scheduling evaluation."""

    sprint_label: str
    planned_issue_keys: tuple[str, ...]
    execution_order: tuple[str, ...]
    errors: tuple[SprintDependencyPlanningError, ...]
    correction_plan: SprintDependencyCorrectionPlan

    @property
    def is_valid(self) -> bool:
        return not self.errors


DEFAULT_COMPLETED_DEPENDENCY_STATUSES = (
    "TEST COMPLETED",
    "ACCEPTED/DONE",
)


def evaluate_recursive_sprint_dependency_coscheduling(
    *,
    sprint_label: str,
    proposed_issue_keys: tuple[str, ...],
    issues: tuple[SprintDependencyIssue, ...],
    links: tuple[SprintDependencyLink, ...],
    completed_statuses: tuple[str, ...] = DEFAULT_COMPLETED_DEPENDENCY_STATUSES,
) -> SprintDependencyCoSchedulingResult:
    """Evaluate whether unresolved blocker chains are co-scheduled."""

    sprint_label = _require_text("sprint_label", sprint_label)
    proposed_keys = tuple(_require_text("proposed_issue_keys[]", key) for key in proposed_issue_keys)
    if not proposed_keys:
        raise SprintDependencyCoSchedulingError("proposed_issue_keys is required")
    issue_by_key = {_require_text("issue.issue_key", issue.issue_key): issue for issue in issues}
    blockers_by_dependent: dict[str, list[str]] = {}
    for link in links:
        blocker = _require_text("link.blocker_key", link.blocker_key)
        dependent = _require_text("link.dependent_key", link.dependent_key)
        blockers_by_dependent.setdefault(dependent, []).append(blocker)
    completed = {_normalize_status(status) for status in completed_statuses}
    planned = _planned_issue_keys(sprint_label, proposed_keys, issue_by_key)
    errors: list[SprintDependencyPlanningError] = []
    missing: set[str] = set()
    for key in proposed_keys:
        _walk_blockers(
            dependent_key=key,
            current_key=key,
            chain=(key,),
            blockers_by_dependent=blockers_by_dependent,
            issue_by_key=issue_by_key,
            planned=planned,
            completed=completed,
            errors=errors,
            missing=missing,
            visiting=set(),
        )
    return SprintDependencyCoSchedulingResult(
        sprint_label=sprint_label,
        planned_issue_keys=tuple(sorted(planned)),
        execution_order=_dependency_execution_order(planned, blockers_by_dependent),
        errors=tuple(errors),
        correction_plan=SprintDependencyCorrectionPlan(
            sprint_label=sprint_label,
            required_issue_keys=tuple(sorted(missing)),
        ),
    )


def render_sprint_dependency_coscheduling_result(
    result: SprintDependencyCoSchedulingResult,
) -> str:
    """Render a scheduler-readable co-scheduling decision note."""

    _require_text("result.sprint_label", result.sprint_label)
    lines = [
        f"# Sprint Dependency Co-Scheduling - {result.sprint_label}",
        "",
        f"Result: {'valid' if result.is_valid else 'blocked'}",
        "",
        "## Planned Issues",
    ]
    for key in result.planned_issue_keys:
        lines.append(f"- {key}")
    lines.extend(["", "## Execution Order"])
    if result.execution_order:
        for index, key in enumerate(result.execution_order, start=1):
            lines.append(f"{index}. {key}")
    else:
        lines.append("- None")
    lines.extend(["", "## Blocking Errors"])
    if result.errors:
        for error in result.errors:
            chain = " -> ".join(error.dependency_chain)
            lines.append(f"- {error.message}")
            lines.append(f"  - Chain: {chain}")
    else:
        lines.append("- None")
    lines.extend(["", "## Correction Plan"])
    if result.correction_plan.required_issue_keys:
        lines.append("Add or complete these prerequisite issues before keeping the dependent scope:")
        for key in result.correction_plan.required_issue_keys:
            lines.append(f"- {key}")
    else:
        lines.append("- No correction required")
    return "\n".join(lines)


def _walk_blockers(
    *,
    dependent_key: str,
    current_key: str,
    chain: tuple[str, ...],
    blockers_by_dependent: dict[str, list[str]],
    issue_by_key: dict[str, SprintDependencyIssue],
    planned: set[str],
    completed: set[str],
    errors: list[SprintDependencyPlanningError],
    missing: set[str],
    visiting: set[str],
) -> None:
    if current_key in visiting:
        return
    visiting.add(current_key)
    for blocker_key in sorted(blockers_by_dependent.get(current_key, ())):
        blocker = issue_by_key.get(blocker_key)
        blocker_chain = (*chain, blocker_key)
        if blocker is None:
            missing.add(blocker_key)
            errors.append(_planning_error(dependent_key, blocker_key, blocker_chain))
            continue
        if blocker.merged_to_main or _normalize_status(blocker.status) in completed:
            continue
        if blocker_key not in planned:
            missing.add(blocker_key)
            errors.append(_planning_error(dependent_key, blocker_key, blocker_chain))
        _walk_blockers(
            dependent_key=dependent_key,
            current_key=blocker_key,
            chain=blocker_chain,
            blockers_by_dependent=blockers_by_dependent,
            issue_by_key=issue_by_key,
            planned=planned,
            completed=completed,
            errors=errors,
            missing=missing,
            visiting=set(visiting),
        )


def _planning_error(
    dependent_key: str,
    blocker_key: str,
    chain: tuple[str, ...],
) -> SprintDependencyPlanningError:
    return SprintDependencyPlanningError(
        dependent_issue_key=dependent_key,
        missing_blocker_key=blocker_key,
        dependency_chain=chain,
        message=(
            f"{dependent_key} cannot remain in sprint scope until unresolved "
            f"blocker {blocker_key} is completed or co-scheduled."
        ),
    )


def _planned_issue_keys(
    sprint_label: str,
    proposed_keys: tuple[str, ...],
    issue_by_key: dict[str, SprintDependencyIssue],
) -> set[str]:
    planned = set(proposed_keys)
    for key, issue in issue_by_key.items():
        if sprint_label in issue.sprint_labels:
            planned.add(key)
    return planned


def _dependency_execution_order(
    planned: set[str],
    blockers_by_dependent: dict[str, list[str]],
) -> tuple[str, ...]:
    ordered: list[str] = []
    visited: set[str] = set()

    def visit(key: str) -> None:
        if key in visited:
            return
        visited.add(key)
        for blocker_key in sorted(blockers_by_dependent.get(key, ())):
            if blocker_key in planned:
                visit(blocker_key)
        ordered.append(key)

    for key in sorted(planned):
        visit(key)
    return tuple(ordered)


def _normalize_status(status: str) -> str:
    return str(status or "").strip().casefold()


def _require_text(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SprintDependencyCoSchedulingError(f"{name} is required")
    return value.strip()
