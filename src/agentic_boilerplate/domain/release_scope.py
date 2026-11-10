"""Release and sprint scope planning model."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Any


class ReleaseScopeError(ValueError):
    """Raised when release scope input is incomplete or inconsistent."""


class ScopeProposalStatus(str, Enum):
    """Release Manager proposal status before Product Owner approval."""

    DRAFT = "draft"
    PROPOSED = "proposed"
    PO_APPROVED = "po_approved"
    REJECTED = "rejected"


@dataclass(frozen=True)
class ScopeIssue:
    """Issue included in a release scope sprint ring."""

    key: str
    title: str
    issue_type: str
    complexity_points: int
    status: str = ""


@dataclass(frozen=True)
class SprintRing:
    """A coherent sprint slice within a larger release scope."""

    number: int
    name: str
    capacity_target: str
    complexity_total: int
    included_issues: tuple[ScopeIssue, ...]
    goal: str = ""


@dataclass(frozen=True)
class ReleaseScope:
    """Release scope that may span multiple sprint rings."""

    key: str
    name: str
    release_version: str
    description: str
    created_at: str
    sprint_rings: tuple[SprintRing, ...]


@dataclass(frozen=True)
class SprintScopeSelectionProposal:
    """Release Manager proposal for stories before Product Owner approval."""

    id: str
    release_scope_key: str
    sprint_ring_number: int
    selected_issue_keys: tuple[str, ...]
    proposed_by: str
    rationale: str
    created_at: str
    status: ScopeProposalStatus = ScopeProposalStatus.PROPOSED


def create_sprint_ring(
    *,
    number: int,
    name: str,
    capacity_target: str,
    included_issues: tuple[ScopeIssue, ...],
    goal: str = "",
    complexity_total: int | None = None,
) -> SprintRing:
    """Create a sprint ring and compute complexity when not supplied."""

    _require_positive_int("number", number)
    _require_text("name", name)
    _require_text("capacity_target", capacity_target)
    if not included_issues:
        raise ReleaseScopeError("included_issues is required")
    for issue in included_issues:
        _validate_scope_issue(issue)

    computed_total = sum(issue.complexity_points for issue in included_issues)
    if complexity_total is None:
        complexity_total = computed_total
    _require_non_negative_int("complexity_total", complexity_total)
    if complexity_total != computed_total:
        raise ReleaseScopeError("complexity_total must match included issue complexity")

    return SprintRing(
        number=number,
        name=name,
        capacity_target=capacity_target,
        complexity_total=complexity_total,
        included_issues=included_issues,
        goal=goal.strip(),
    )


def create_release_scope(
    *,
    key: str,
    name: str,
    release_version: str,
    description: str,
    created_at: str,
    sprint_rings: tuple[SprintRing, ...],
) -> ReleaseScope:
    """Create a release scope with one or more sprint rings."""

    _require_text("key", key)
    _require_text("name", name)
    _require_text("release_version", release_version)
    _require_text("description", description)
    _require_text("created_at", created_at)
    if not sprint_rings:
        raise ReleaseScopeError("at least one sprint ring is required")
    for ring in sprint_rings:
        create_sprint_ring(
            number=ring.number,
            name=ring.name,
            capacity_target=ring.capacity_target,
            complexity_total=ring.complexity_total,
            goal=ring.goal,
            included_issues=ring.included_issues,
        )
    _require_unique_ints("sprint ring numbers", tuple(ring.number for ring in sprint_rings))
    return ReleaseScope(
        key=key,
        name=name,
        release_version=release_version,
        description=description,
        created_at=created_at,
        sprint_rings=sprint_rings,
    )


def propose_sprint_scope_selection(
    release_scope: ReleaseScope,
    *,
    sprint_ring_number: int,
    selected_issue_keys: tuple[str, ...],
    proposed_by: str,
    rationale: str,
    created_at: str,
    proposal_id: str | None = None,
) -> SprintScopeSelectionProposal:
    """Build a Release Manager story selection proposal before PO approval."""

    _validate_release_scope(release_scope)
    _require_positive_int("sprint_ring_number", sprint_ring_number)
    _require_text("proposed_by", proposed_by)
    _require_text("rationale", rationale)
    _require_text("created_at", created_at)
    if not selected_issue_keys:
        raise ReleaseScopeError("selected_issue_keys is required")
    normalized_keys = tuple(_require_text("selected_issue_keys[]", key) for key in selected_issue_keys)
    _require_unique_texts("selected issue keys", normalized_keys)

    ring = sprint_ring_by_number(release_scope, sprint_ring_number)
    ring_issue_keys = {issue.key for issue in ring.included_issues}
    missing_keys = tuple(key for key in normalized_keys if key not in ring_issue_keys)
    if missing_keys:
        raise ReleaseScopeError(
            "selected_issue_keys must belong to the selected sprint ring: "
            + ", ".join(missing_keys)
        )

    return SprintScopeSelectionProposal(
        id=proposal_id or f"{release_scope.key}-S{str(sprint_ring_number).zfill(2)}-proposal",
        release_scope_key=release_scope.key,
        sprint_ring_number=sprint_ring_number,
        selected_issue_keys=normalized_keys,
        proposed_by=proposed_by.strip(),
        rationale=rationale.strip(),
        created_at=created_at.strip(),
    )


def approve_sprint_scope_selection(
    proposal: SprintScopeSelectionProposal,
) -> SprintScopeSelectionProposal:
    """Mark a sprint scope proposal as Product Owner approved."""

    _validate_proposal(proposal)
    if proposal.status == ScopeProposalStatus.REJECTED:
        raise ReleaseScopeError("rejected proposals cannot be approved")
    return replace(proposal, status=ScopeProposalStatus.PO_APPROVED)


def sprint_ring_by_number(release_scope: ReleaseScope, number: int) -> SprintRing:
    """Return a sprint ring by number."""

    _validate_release_scope(release_scope)
    for ring in release_scope.sprint_rings:
        if ring.number == number:
            return ring
    raise ReleaseScopeError(f"sprint ring {number} was not found")


def release_scope_to_dict(scope: ReleaseScope) -> dict[str, Any]:
    """Convert a release scope into JSON-compatible data."""

    _validate_release_scope(scope)
    return {
        "key": scope.key,
        "name": scope.name,
        "release_version": scope.release_version,
        "description": scope.description,
        "created_at": scope.created_at,
        "sprint_rings": [
            {
                "number": ring.number,
                "name": ring.name,
                "capacity_target": ring.capacity_target,
                "complexity_total": ring.complexity_total,
                "goal": ring.goal,
                "included_issues": [
                    {
                        "key": issue.key,
                        "title": issue.title,
                        "issue_type": issue.issue_type,
                        "complexity_points": issue.complexity_points,
                        "status": issue.status,
                    }
                    for issue in ring.included_issues
                ],
            }
            for ring in scope.sprint_rings
        ],
    }


def release_scope_from_dict(data: dict[str, Any]) -> ReleaseScope:
    """Build a release scope from JSON-compatible data."""

    rings = tuple(
        create_sprint_ring(
            number=_int_value(ring_data.get("number")),
            name=_optional_text(ring_data.get("name")),
            capacity_target=_optional_text(ring_data.get("capacity_target")),
            complexity_total=_int_value(ring_data.get("complexity_total")),
            goal=_optional_text(ring_data.get("goal")),
            included_issues=tuple(
                ScopeIssue(
                    key=_optional_text(issue_data.get("key")),
                    title=_optional_text(issue_data.get("title")),
                    issue_type=_optional_text(issue_data.get("issue_type")),
                    complexity_points=_int_value(issue_data.get("complexity_points")),
                    status=_optional_text(issue_data.get("status")),
                )
                for issue_data in ring_data.get("included_issues", ())
            ),
        )
        for ring_data in data.get("sprint_rings", ())
    )
    return create_release_scope(
        key=_optional_text(data.get("key")),
        name=_optional_text(data.get("name")),
        release_version=_optional_text(data.get("release_version")),
        description=_optional_text(data.get("description")),
        created_at=_optional_text(data.get("created_at")),
        sprint_rings=rings,
    )


def sprint_scope_selection_proposal_to_dict(
    proposal: SprintScopeSelectionProposal,
) -> dict[str, Any]:
    """Convert a sprint selection proposal into JSON-compatible data."""

    _validate_proposal(proposal)
    return {
        "id": proposal.id,
        "release_scope_key": proposal.release_scope_key,
        "sprint_ring_number": proposal.sprint_ring_number,
        "selected_issue_keys": list(proposal.selected_issue_keys),
        "proposed_by": proposal.proposed_by,
        "rationale": proposal.rationale,
        "created_at": proposal.created_at,
        "status": proposal.status.value,
    }


def sprint_scope_selection_proposal_from_dict(
    data: dict[str, Any],
) -> SprintScopeSelectionProposal:
    """Build a sprint selection proposal from JSON-compatible data."""

    proposal = SprintScopeSelectionProposal(
        id=_optional_text(data.get("id")),
        release_scope_key=_optional_text(data.get("release_scope_key")),
        sprint_ring_number=_int_value(data.get("sprint_ring_number")),
        selected_issue_keys=tuple(
            _optional_text(key) for key in data.get("selected_issue_keys", ())
        ),
        proposed_by=_optional_text(data.get("proposed_by")),
        rationale=_optional_text(data.get("rationale")),
        created_at=_optional_text(data.get("created_at")),
        status=ScopeProposalStatus(data.get("status", ScopeProposalStatus.PROPOSED.value)),
    )
    _validate_proposal(proposal)
    return proposal


def _validate_release_scope(scope: ReleaseScope) -> None:
    create_release_scope(
        key=scope.key,
        name=scope.name,
        release_version=scope.release_version,
        description=scope.description,
        created_at=scope.created_at,
        sprint_rings=scope.sprint_rings,
    )


def _validate_scope_issue(issue: ScopeIssue) -> None:
    _require_text("issue.key", issue.key)
    _require_text("issue.title", issue.title)
    _require_text("issue.issue_type", issue.issue_type)
    _require_non_negative_int("issue.complexity_points", issue.complexity_points)


def _validate_proposal(proposal: SprintScopeSelectionProposal) -> None:
    _require_text("proposal.id", proposal.id)
    _require_text("proposal.release_scope_key", proposal.release_scope_key)
    _require_positive_int("proposal.sprint_ring_number", proposal.sprint_ring_number)
    if not proposal.selected_issue_keys:
        raise ReleaseScopeError("proposal.selected_issue_keys is required")
    _require_unique_texts("proposal.selected_issue_keys", proposal.selected_issue_keys)
    _require_text("proposal.proposed_by", proposal.proposed_by)
    _require_text("proposal.rationale", proposal.rationale)
    _require_text("proposal.created_at", proposal.created_at)


def _require_text(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReleaseScopeError(f"{name} is required")
    return value.strip()


def _optional_text(value: Any) -> str:
    return "" if value is None else str(value)


def _int_value(value: Any) -> int:
    if isinstance(value, bool):
        raise ReleaseScopeError("integer values cannot be booleans")
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise ReleaseScopeError("integer value is required") from error


def _require_positive_int(name: str, value: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ReleaseScopeError(f"{name} must be a positive integer")


def _require_non_negative_int(name: str, value: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ReleaseScopeError(f"{name} must be a non-negative integer")


def _require_unique_ints(name: str, values: tuple[int, ...]) -> None:
    if len(set(values)) != len(values):
        raise ReleaseScopeError(f"{name} must be unique")


def _require_unique_texts(name: str, values: tuple[str, ...]) -> None:
    normalized = tuple(_require_text(f"{name}[]", value) for value in values)
    if len(set(normalized)) != len(normalized):
        raise ReleaseScopeError(f"{name} must be unique")
