"""Sprint dependency and Product Owner acceptance gate rules."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


DEFAULT_TECHNICAL_UNBLOCK_STATUSES = ("TEST COMPLETED", "ACCEPTED/DONE")
DEFAULT_PO_ACCEPTED_STATUSES = ("ACCEPTED/DONE",)


class GateDecisionType(str, Enum):
    """Supported scheduler and release gate decisions."""

    DEPENDENCY_UNBLOCK = "dependency_unblock"
    SCHEDULER_ASSIGNMENT = "scheduler_assignment"
    REGRESSION_OR_RELEASE_PREPARATION = "regression_or_release_preparation"


class GateBlockerKind(str, Enum):
    """Reasons a gate is blocked."""

    NOT_MERGED_TO_MAIN = "not_merged_to_main"
    TESTER_NOT_VALIDATED = "tester_not_validated"
    STATUS_NOT_TECHNICALLY_COMPLETE = "status_not_technically_complete"
    UNRESOLVED_BLOCKING_BUG = "unresolved_blocking_bug"
    PO_ACCEPTANCE_REQUIRED = "po_acceptance_required"
    PO_SCOPE_NOT_ACCEPTED = "po_scope_not_accepted"


@dataclass(frozen=True)
class GateBlocker:
    """One reason a gate cannot pass."""

    kind: GateBlockerKind
    issue_key: str = ""
    message: str = ""


@dataclass(frozen=True)
class PrerequisiteGateInput:
    """Technical validation state for one prerequisite story."""

    issue_key: str
    status: str
    merged_to_main: bool
    tester_validated: bool
    unresolved_bug_keys: tuple[str, ...] = ()
    po_acceptance_required: bool = False


@dataclass(frozen=True)
class GateDecision:
    """Inspectable result for scheduler or release-manager gate decisions."""

    decision_type: GateDecisionType
    issue_key: str
    passed: bool
    blockers: tuple[GateBlocker, ...]
    reasons: tuple[str, ...]


def evaluate_dependency_unblock(
    prerequisite: PrerequisiteGateInput,
    *,
    technical_unblock_statuses: tuple[str, ...] = DEFAULT_TECHNICAL_UNBLOCK_STATUSES,
    po_accepted_statuses: tuple[str, ...] = DEFAULT_PO_ACCEPTED_STATUSES,
) -> GateDecision:
    """Evaluate whether one prerequisite can unblock dependent development."""

    _require_text("prerequisite.issue_key", prerequisite.issue_key)
    blockers = _technical_prerequisite_blockers(prerequisite, technical_unblock_statuses)
    if prerequisite.po_acceptance_required and _normalize_status(prerequisite.status) not in _status_set(
        po_accepted_statuses
    ):
        blockers.append(
            GateBlocker(
                kind=GateBlockerKind.PO_ACCEPTANCE_REQUIRED,
                issue_key=prerequisite.issue_key,
                message="This prerequisite explicitly requires Product Owner acceptance.",
            )
        )
    return _decision(
        GateDecisionType.DEPENDENCY_UNBLOCK,
        prerequisite.issue_key,
        blockers,
        passed_reason=f"{prerequisite.issue_key} can unblock dependent development.",
    )


def evaluate_scheduler_assignment_gate(
    *,
    issue_key: str,
    prerequisites: tuple[PrerequisiteGateInput, ...],
    po_acceptance_required: bool = False,
    dependent_status: str = "",
    technical_unblock_statuses: tuple[str, ...] = DEFAULT_TECHNICAL_UNBLOCK_STATUSES,
    po_accepted_statuses: tuple[str, ...] = DEFAULT_PO_ACCEPTED_STATUSES,
) -> GateDecision:
    """Evaluate whether the scheduler may assign a dependent story."""

    _require_text("issue_key", issue_key)
    blockers: list[GateBlocker] = []
    for prerequisite in prerequisites:
        blockers.extend(_technical_prerequisite_blockers(prerequisite, technical_unblock_statuses))
        if prerequisite.po_acceptance_required and _normalize_status(prerequisite.status) not in _status_set(
            po_accepted_statuses
        ):
            blockers.append(
                GateBlocker(
                    kind=GateBlockerKind.PO_ACCEPTANCE_REQUIRED,
                    issue_key=prerequisite.issue_key,
                    message="Prerequisite requires Product Owner acceptance before dependent development.",
                )
            )
    if po_acceptance_required and _normalize_status(dependent_status) not in _status_set(po_accepted_statuses):
        blockers.append(
            GateBlocker(
                kind=GateBlockerKind.PO_ACCEPTANCE_REQUIRED,
                issue_key=issue_key,
                message="Dependent story explicitly requires Product Owner acceptance before assignment.",
            )
        )
    return _decision(
        GateDecisionType.SCHEDULER_ASSIGNMENT,
        issue_key,
        blockers,
        passed_reason=f"{issue_key} can be assigned without waiting for sprint-level PO acceptance.",
    )


def evaluate_regression_or_release_preparation_gate(
    *,
    scope_key: str,
    po_scope_accepted: bool,
) -> GateDecision:
    """Evaluate whether regression or release preparation may start."""

    _require_text("scope_key", scope_key)
    blockers: list[GateBlocker] = []
    if not po_scope_accepted:
        blockers.append(
            GateBlocker(
                kind=GateBlockerKind.PO_SCOPE_NOT_ACCEPTED,
                issue_key=scope_key,
                message="Regression and release preparation require Product Owner scope acceptance.",
            )
        )
    return _decision(
        GateDecisionType.REGRESSION_OR_RELEASE_PREPARATION,
        scope_key,
        blockers,
        passed_reason=f"{scope_key} is Product Owner accepted for regression or release preparation.",
    )


def render_gate_decision_log(decision: GateDecision) -> str:
    """Render a durable Markdown log for a gate decision."""

    lines = [
        f"# Gate Decision - {decision.issue_key}",
        "",
        f"- Type: {decision.decision_type.value}",
        f"- Passed: {'yes' if decision.passed else 'no'}",
        "",
        "## Reasons",
    ]
    lines.extend(f"- {reason}" for reason in decision.reasons)
    lines.extend(["", "## Blockers"])
    if decision.blockers:
        for blocker in decision.blockers:
            target = f" {blocker.issue_key}" if blocker.issue_key else ""
            message = f": {blocker.message}" if blocker.message else ""
            lines.append(f"- {blocker.kind.value}{target}{message}")
    else:
        lines.append("- None")
    return "\n".join(lines) + "\n"


def _technical_prerequisite_blockers(
    prerequisite: PrerequisiteGateInput,
    technical_unblock_statuses: tuple[str, ...],
) -> list[GateBlocker]:
    _require_text("prerequisite.issue_key", prerequisite.issue_key)
    blockers: list[GateBlocker] = []
    if not prerequisite.merged_to_main:
        blockers.append(
            GateBlocker(
                kind=GateBlockerKind.NOT_MERGED_TO_MAIN,
                issue_key=prerequisite.issue_key,
                message="Prerequisite has not been merged to main.",
            )
        )
    if not prerequisite.tester_validated:
        blockers.append(
            GateBlocker(
                kind=GateBlockerKind.TESTER_NOT_VALIDATED,
                issue_key=prerequisite.issue_key,
                message="Tester Agent validation is not complete.",
            )
        )
    if _normalize_status(prerequisite.status) not in _status_set(technical_unblock_statuses):
        blockers.append(
            GateBlocker(
                kind=GateBlockerKind.STATUS_NOT_TECHNICALLY_COMPLETE,
                issue_key=prerequisite.issue_key,
                message="Prerequisite status is not technically complete.",
            )
        )
    blockers.extend(
        GateBlocker(
            kind=GateBlockerKind.UNRESOLVED_BLOCKING_BUG,
            issue_key=bug_key,
            message=f"Prerequisite {prerequisite.issue_key} has an unresolved blocking bug.",
        )
        for bug_key in prerequisite.unresolved_bug_keys
    )
    return blockers


def _decision(
    decision_type: GateDecisionType,
    issue_key: str,
    blockers: list[GateBlocker],
    *,
    passed_reason: str,
) -> GateDecision:
    passed = not blockers
    return GateDecision(
        decision_type=decision_type,
        issue_key=issue_key,
        passed=passed,
        blockers=tuple(blockers),
        reasons=(passed_reason,) if passed else tuple(_blocker_reason(blocker) for blocker in blockers),
    )


def _blocker_reason(blocker: GateBlocker) -> str:
    target = f"{blocker.issue_key}: " if blocker.issue_key else ""
    return f"{target}{blocker.message or blocker.kind.value}"


def _status_set(statuses: tuple[str, ...]) -> frozenset[str]:
    return frozenset(_normalize_status(status) for status in statuses if _normalize_status(status))


def _normalize_status(status: str) -> str:
    return " ".join(status.replace("/", " / ").split()).casefold()


def _require_text(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    return value.strip()
