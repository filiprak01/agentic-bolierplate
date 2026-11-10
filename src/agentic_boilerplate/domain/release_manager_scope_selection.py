"""Release Manager scope selection workflow."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from agentic_boilerplate.domain.po_inbox import AgentRole


READY_TO_START_STATUS = "READY TO START"


class PreviousTestOutcome(str, Enum):
    """Previous test outcome signal used before assigning release scope."""

    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"
    NO_PREVIOUS_TEST = "no-previous-test"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ReleaseManagerIssueCandidate:
    """Jira issue considered by Release Manager for release/sprint scope."""

    issue_key: str
    title: str
    issue_type: str
    status: str
    complexity_points: int
    worker_role: AgentRole
    dependency_eligible: bool
    worker_available: bool
    previous_test_outcome: PreviousTestOutcome = PreviousTestOutcome.NO_PREVIOUS_TEST
    dependency_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReleaseManagerRejectedIssue:
    """Issue skipped by Release Manager during scope selection."""

    issue_key: str
    reason: str


@dataclass(frozen=True)
class ReleaseMetadataPlan:
    """Labels/version metadata that should be applied to selected Jira issues."""

    issue_key: str
    release_label: str
    release_version: str
    sprint_label: str
    sprint_ring_label: str


@dataclass(frozen=True)
class ReleaseAssignmentDecision:
    """Worker assignment decision for a selected release scope issue."""

    issue_key: str
    worker_role: AgentRole
    assignable: bool
    reason: str


@dataclass(frozen=True)
class ReleaseManagerScopeSelection:
    """Release Manager selection result before scheduler assignment."""

    release_scope_key: str
    sprint_ring_number: int
    selected_issue_keys: tuple[str, ...]
    rejected: tuple[ReleaseManagerRejectedIssue, ...]
    metadata_plans: tuple[ReleaseMetadataPlan, ...]
    assignment_decisions: tuple[ReleaseAssignmentDecision, ...]
    complexity_total: int
    story_count: int
    po_approval_required: bool = True
    rationale: str = ""


class ReleaseManagerScopeSelectionError(ValueError):
    """Raised when release manager scope input is invalid."""


def build_release_manager_scope_selection(
    *,
    release_scope_key: str,
    sprint_ring_number: int,
    candidates: tuple[ReleaseManagerIssueCandidate, ...],
    release_label: str,
    release_version: str,
    sprint_label: str,
    sprint_ring_label: str,
    max_complexity_points: int,
    max_story_count: int,
    rationale: str,
) -> ReleaseManagerScopeSelection:
    """Select eligible release/sprint issues and produce assignment metadata."""

    _require_text("release_scope_key", release_scope_key)
    _require_positive_int("sprint_ring_number", sprint_ring_number)
    _require_text("release_label", release_label)
    _require_text("release_version", release_version)
    _require_text("sprint_label", sprint_label)
    _require_text("sprint_ring_label", sprint_ring_label)
    _require_positive_int("max_complexity_points", max_complexity_points)
    _require_positive_int("max_story_count", max_story_count)
    _require_text("rationale", rationale)

    selected: list[ReleaseManagerIssueCandidate] = []
    rejected: list[ReleaseManagerRejectedIssue] = []
    complexity_total = 0

    for candidate in candidates:
        _validate_candidate(candidate)
        reason = _candidate_rejection_reason(candidate)
        if reason:
            rejected.append(ReleaseManagerRejectedIssue(candidate.issue_key, reason))
            continue
        if len(selected) + 1 > max_story_count:
            rejected.append(ReleaseManagerRejectedIssue(candidate.issue_key, "Story count would exceed capacity."))
            continue
        if complexity_total + candidate.complexity_points > max_complexity_points:
            rejected.append(ReleaseManagerRejectedIssue(candidate.issue_key, "Complexity total would exceed capacity."))
            continue
        selected.append(candidate)
        complexity_total += candidate.complexity_points

    metadata_plans = tuple(
        ReleaseMetadataPlan(
            issue_key=candidate.issue_key,
            release_label=release_label.strip(),
            release_version=release_version.strip(),
            sprint_label=sprint_label.strip(),
            sprint_ring_label=sprint_ring_label.strip(),
        )
        for candidate in selected
    )
    assignment_decisions = tuple(
        ReleaseAssignmentDecision(
            issue_key=candidate.issue_key,
            worker_role=candidate.worker_role,
            assignable=True,
            reason="Selected issue is ready, unblocked, within capacity, and has an available worker.",
        )
        for candidate in selected
    )

    return ReleaseManagerScopeSelection(
        release_scope_key=release_scope_key.strip(),
        sprint_ring_number=sprint_ring_number,
        selected_issue_keys=tuple(candidate.issue_key for candidate in selected),
        rejected=tuple(rejected),
        metadata_plans=metadata_plans,
        assignment_decisions=assignment_decisions,
        complexity_total=complexity_total,
        story_count=len(selected),
        rationale=rationale.strip(),
    )


def release_manager_scope_selection_to_dict(selection: ReleaseManagerScopeSelection) -> dict[str, Any]:
    """Convert a selection result to JSON-compatible data."""

    _validate_selection(selection)
    return {
        "release_scope_key": selection.release_scope_key,
        "sprint_ring_number": selection.sprint_ring_number,
        "selected_issue_keys": list(selection.selected_issue_keys),
        "rejected": [
            {
                "issue_key": rejected.issue_key,
                "reason": rejected.reason,
            }
            for rejected in selection.rejected
        ],
        "metadata_plans": [
            {
                "issue_key": plan.issue_key,
                "release_label": plan.release_label,
                "release_version": plan.release_version,
                "sprint_label": plan.sprint_label,
                "sprint_ring_label": plan.sprint_ring_label,
            }
            for plan in selection.metadata_plans
        ],
        "assignment_decisions": [
            {
                "issue_key": decision.issue_key,
                "worker_role": decision.worker_role.value,
                "assignable": decision.assignable,
                "reason": decision.reason,
            }
            for decision in selection.assignment_decisions
        ],
        "complexity_total": selection.complexity_total,
        "story_count": selection.story_count,
        "po_approval_required": selection.po_approval_required,
        "rationale": selection.rationale,
    }


def release_manager_scope_selection_from_dict(data: dict[str, Any]) -> ReleaseManagerScopeSelection:
    """Build a selection result from JSON-compatible data."""

    selection = ReleaseManagerScopeSelection(
        release_scope_key=_optional_text(data.get("release_scope_key")),
        sprint_ring_number=_int_value(data.get("sprint_ring_number")),
        selected_issue_keys=tuple(_optional_text(key) for key in data.get("selected_issue_keys", ())),
        rejected=tuple(
            ReleaseManagerRejectedIssue(
                issue_key=_optional_text(item.get("issue_key")),
                reason=_optional_text(item.get("reason")),
            )
            for item in data.get("rejected", ())
        ),
        metadata_plans=tuple(
            ReleaseMetadataPlan(
                issue_key=_optional_text(item.get("issue_key")),
                release_label=_optional_text(item.get("release_label")),
                release_version=_optional_text(item.get("release_version")),
                sprint_label=_optional_text(item.get("sprint_label")),
                sprint_ring_label=_optional_text(item.get("sprint_ring_label")),
            )
            for item in data.get("metadata_plans", ())
        ),
        assignment_decisions=tuple(
            ReleaseAssignmentDecision(
                issue_key=_optional_text(item.get("issue_key")),
                worker_role=AgentRole(_optional_text(item.get("worker_role"))),
                assignable=bool(item.get("assignable")),
                reason=_optional_text(item.get("reason")),
            )
            for item in data.get("assignment_decisions", ())
        ),
        complexity_total=_int_value(data.get("complexity_total")),
        story_count=_int_value(data.get("story_count")),
        po_approval_required=bool(data.get("po_approval_required", True)),
        rationale=_optional_text(data.get("rationale")),
    )
    _validate_selection(selection)
    return selection


def render_release_manager_scope_selection(selection: ReleaseManagerScopeSelection) -> str:
    """Render selection decisions for durable evidence or Jira comments."""

    _validate_selection(selection)
    lines = [
        f"# Release Manager Scope Selection - {selection.release_scope_key}",
        "",
        f"- Sprint ring: {selection.sprint_ring_number}",
        f"- PO approval required: {'yes' if selection.po_approval_required else 'no'}",
        f"- Selected story count: {selection.story_count}",
        f"- Selected complexity total: {selection.complexity_total}",
        f"- Rationale: {selection.rationale}",
        "",
        "## Selected Issues",
    ]
    if selection.selected_issue_keys:
        lines.extend(f"- {issue_key}" for issue_key in selection.selected_issue_keys)
    else:
        lines.append("- None")
    lines.extend(["", "## Rejected Issues"])
    if selection.rejected:
        lines.extend(f"- {item.issue_key}: {item.reason}" for item in selection.rejected)
    else:
        lines.append("- None")
    return "\n".join(lines).strip() + "\n"


def _candidate_rejection_reason(candidate: ReleaseManagerIssueCandidate) -> str:
    if _normalize_status(candidate.status) != _normalize_status(READY_TO_START_STATUS):
        return "Issue is not READY TO START."
    if not candidate.dependency_eligible:
        suffix = f" {'; '.join(candidate.dependency_reasons)}" if candidate.dependency_reasons else ""
        return f"Issue has unresolved prerequisites.{suffix}".strip()
    if candidate.previous_test_outcome in {PreviousTestOutcome.FAILED, PreviousTestOutcome.BLOCKED}:
        return f"Previous test outcome blocks release scope: {candidate.previous_test_outcome.value}."
    if not candidate.worker_available:
        return "No available worker for required role."
    return ""


def _validate_candidate(candidate: ReleaseManagerIssueCandidate) -> None:
    _require_text("candidate.issue_key", candidate.issue_key)
    _require_text("candidate.title", candidate.title)
    _require_text("candidate.issue_type", candidate.issue_type)
    _require_text("candidate.status", candidate.status)
    _require_non_negative_int("candidate.complexity_points", candidate.complexity_points)


def _validate_selection(selection: ReleaseManagerScopeSelection) -> None:
    _require_text("selection.release_scope_key", selection.release_scope_key)
    _require_positive_int("selection.sprint_ring_number", selection.sprint_ring_number)
    _require_non_negative_int("selection.complexity_total", selection.complexity_total)
    _require_non_negative_int("selection.story_count", selection.story_count)
    _require_text("selection.rationale", selection.rationale)


def _normalize_status(status: str) -> str:
    return " ".join(status.replace("/", " / ").split()).casefold()


def _optional_text(value: object) -> str:
    return str(value or "").strip()


def _int_value(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ReleaseManagerScopeSelectionError("integer value is required")
    return value


def _require_text(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReleaseManagerScopeSelectionError(f"{name} is required")
    return value.strip()


def _require_positive_int(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ReleaseManagerScopeSelectionError(f"{name} must be a positive integer")


def _require_non_negative_int(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ReleaseManagerScopeSelectionError(f"{name} must be a non-negative integer")
