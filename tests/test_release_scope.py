import pytest

from agentic_boilerplate import domain, storage
from agentic_boilerplate.domain.release_scope import (
    ReleaseScopeError,
    ScopeProposalStatus,
    approve_sprint_scope_selection,
    create_release_scope,
    create_sprint_ring,
    propose_sprint_scope_selection,
    release_scope_from_dict,
    release_scope_to_dict,
)
from agentic_boilerplate.storage.release_scope import FileReleaseScopeStore


def sprint_6_issue() -> domain.ScopeIssue:
    return domain.ScopeIssue(
        key="AGENT-37",
        title="Implement Release And Sprint Scope Model",
        issue_type="Story",
        complexity_points=3,
        status="READY TO START",
    )


def sprint_7_issue() -> domain.ScopeIssue:
    return domain.ScopeIssue(
        key="AGENT-42",
        title="Implement Worker Assignment Handoff",
        issue_type="Story",
        complexity_points=3,
        status="FUNNEL",
    )


def sample_release_scope() -> domain.ReleaseScope:
    sprint_6 = create_sprint_ring(
        number=6,
        name="MVP S6 Scheduling",
        capacity_target="one Codex Plus working window",
        goal="Deliver scheduler scope and assignment foundations.",
        included_issues=(sprint_6_issue(),),
    )
    sprint_7 = create_sprint_ring(
        number=7,
        name="MVP S7 Developer",
        capacity_target="one Codex Plus working window",
        goal="Deliver developer worker workflow.",
        included_issues=(sprint_7_issue(),),
    )
    return create_release_scope(
        key="MVP-REL-1",
        name="MVP Release 1",
        release_version="1.0.0",
        description="MVP Release 1 spans multiple sprint rings.",
        created_at="2026-06-21T20:30:00Z",
        sprint_rings=(sprint_6, sprint_7),
    )


def test_release_scope_contains_multiple_sprint_rings_with_metadata() -> None:
    scope = sample_release_scope()

    assert scope.release_version == "1.0.0"
    assert len(scope.sprint_rings) == 2
    assert scope.sprint_rings[0].number == 6
    assert scope.sprint_rings[0].capacity_target == "one Codex Plus working window"
    assert scope.sprint_rings[0].complexity_total == 3
    assert scope.sprint_rings[0].included_issues[0].key == "AGENT-37"


def test_release_scope_rejects_invalid_hand_constructed_sprint_ring() -> None:
    ring = domain.SprintRing(
        number=6,
        name=" ",
        capacity_target="one Codex Plus working window",
        complexity_total=3,
        included_issues=(sprint_6_issue(),),
    )

    with pytest.raises(ReleaseScopeError, match="name is required"):
        create_release_scope(
            key="MVP-REL-1",
            name="MVP Release 1",
            release_version="1.0.0",
            description="MVP Release 1 spans multiple sprint rings.",
            created_at="2026-06-21T20:30:00Z",
            sprint_rings=(ring,),
        )


def test_sprint_ring_rejects_complexity_total_that_does_not_match_issues() -> None:
    with pytest.raises(ReleaseScopeError, match="complexity_total must match"):
        create_sprint_ring(
            number=6,
            name="Invalid sprint",
            capacity_target="one Codex Plus working window",
            complexity_total=2,
            included_issues=(sprint_6_issue(),),
        )


def test_release_manager_can_propose_story_selection_before_po_approval() -> None:
    scope = sample_release_scope()

    proposal = propose_sprint_scope_selection(
        scope,
        sprint_ring_number=6,
        selected_issue_keys=("AGENT-37",),
        proposed_by="release-manager",
        rationale="Start with scope model because later planner stories depend on it.",
        created_at="2026-06-21T20:35:00Z",
    )

    assert proposal.release_scope_key == "MVP-REL-1"
    assert proposal.status == ScopeProposalStatus.PROPOSED
    assert proposal.selected_issue_keys == ("AGENT-37",)


def test_scope_proposal_rejects_issues_outside_selected_sprint_ring() -> None:
    scope = sample_release_scope()

    with pytest.raises(ReleaseScopeError, match="selected sprint ring"):
        propose_sprint_scope_selection(
            scope,
            sprint_ring_number=6,
            selected_issue_keys=("AGENT-42",),
            proposed_by="release-manager",
            rationale="Wrong ring selection.",
            created_at="2026-06-21T20:35:00Z",
        )


def test_scope_proposal_can_be_marked_po_approved() -> None:
    scope = sample_release_scope()
    proposal = propose_sprint_scope_selection(
        scope,
        sprint_ring_number=6,
        selected_issue_keys=("AGENT-37",),
        proposed_by="release-manager",
        rationale="Start with scope model.",
        created_at="2026-06-21T20:35:00Z",
    )

    approved = approve_sprint_scope_selection(proposal)

    assert approved.status == ScopeProposalStatus.PO_APPROVED


def test_release_scope_serializes_for_durable_local_files() -> None:
    scope = sample_release_scope()

    restored = release_scope_from_dict(release_scope_to_dict(scope))

    assert restored == scope


def test_file_release_scope_store_roundtrip(tmp_path) -> None:
    scope = sample_release_scope()
    proposal = propose_sprint_scope_selection(
        scope,
        sprint_ring_number=6,
        selected_issue_keys=("AGENT-37",),
        proposed_by="release-manager",
        rationale="Start with scope model.",
        created_at="2026-06-21T20:35:00Z",
    )
    store = FileReleaseScopeStore(tmp_path / "scope-store")

    scope_location = store.create_scope(scope)
    proposal_location = store.create_proposal(proposal)

    assert scope_location.path.name == "MVP-REL-1.json"
    assert proposal_location.path.name == "MVP-REL-1-S06-proposal.json"
    assert store.read_scope("MVP-REL-1") == scope
    assert store.read_proposal("MVP-REL-1-S06-proposal") == proposal
    assert store.list_scopes() == (scope,)
    assert store.list_proposals() == (proposal,)


def test_release_scope_public_api_exports_are_available() -> None:
    assert domain.ReleaseScopeError is ReleaseScopeError
    assert domain.create_release_scope is create_release_scope
    assert domain.create_sprint_ring is create_sprint_ring
    assert domain.propose_sprint_scope_selection is propose_sprint_scope_selection
    assert domain.release_scope_to_dict is release_scope_to_dict
    assert storage.FileReleaseScopeStore is FileReleaseScopeStore
