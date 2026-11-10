from pathlib import Path

import pytest

from agentic_boilerplate.domain import (
    ROLE_SPECIFIC_DOCUMENTATION_RULES,
    SHARED_DOCUMENTATION_RULES,
    TERMINAL_DOCUMENTATION_STATUSES,
    DocumentationProposal,
    DocumentationProposalStatus,
    DocumentationScope,
    RoleSpecificNoteCategory,
    SharedDocumentationCategory,
    build_approved_shared_content,
    build_documentation_sync_decision,
    can_transition_documentation_status,
    documentation_rule_for_category,
    is_approved_shared_documentation,
)


def test_shared_documentation_categories_allow_confluence_sync() -> None:
    rule = documentation_rule_for_category(SharedDocumentationCategory.ARCHITECTURE.value)

    assert rule == SHARED_DOCUMENTATION_RULES[SharedDocumentationCategory.ARCHITECTURE]
    assert rule.scope == DocumentationScope.SHARED
    assert rule.confluence_sync_allowed is True
    assert rule.durable_subpath == Path("shared/architecture")


def test_role_specific_notes_do_not_allow_confluence_sync() -> None:
    rule = documentation_rule_for_category(RoleSpecificNoteCategory.DEVELOPER.value)

    assert rule == ROLE_SPECIFIC_DOCUMENTATION_RULES[RoleSpecificNoteCategory.DEVELOPER]
    assert rule.scope == DocumentationScope.ROLE_SPECIFIC
    assert rule.confluence_sync_allowed is False
    assert rule.durable_subpath == Path("role-notes/developer")


def test_unknown_documentation_category_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown documentation category"):
        documentation_rule_for_category("temporary-scratchpad")


def test_documentation_proposal_status_flow() -> None:
    assert can_transition_documentation_status(
        DocumentationProposalStatus.DRAFT,
        DocumentationProposalStatus.PROPOSED,
    )
    assert can_transition_documentation_status(
        DocumentationProposalStatus.PROPOSED,
        DocumentationProposalStatus.PO_REVIEW,
    )
    assert can_transition_documentation_status(
        DocumentationProposalStatus.PO_REVIEW,
        DocumentationProposalStatus.APPROVED,
    )
    assert can_transition_documentation_status(
        DocumentationProposalStatus.APPROVED,
        DocumentationProposalStatus.SUPERSEDED,
    )
    assert not can_transition_documentation_status(
        DocumentationProposalStatus.APPROVED,
        DocumentationProposalStatus.DRAFT,
    )
    assert DocumentationProposalStatus.APPROVED not in TERMINAL_DOCUMENTATION_STATUSES
    assert DocumentationProposalStatus.REJECTED in TERMINAL_DOCUMENTATION_STATUSES
    assert DocumentationProposalStatus.SUPERSEDED in TERMINAL_DOCUMENTATION_STATUSES


def test_only_approved_shared_documentation_is_truth() -> None:
    shared = DocumentationProposal(
        key="DOC-1",
        title="Architecture Overview",
        category=SharedDocumentationCategory.ARCHITECTURE.value,
        status=DocumentationProposalStatus.APPROVED,
        content_path=Path("docs/architecture-overview.md"),
        scope=DocumentationScope.SHARED,
    )
    role_note = DocumentationProposal(
        key="DOC-2",
        title="Developer working note",
        category=RoleSpecificNoteCategory.DEVELOPER.value,
        status=DocumentationProposalStatus.APPROVED,
        content_path=Path("data/role-notes/developer/note.md"),
        scope=DocumentationScope.ROLE_SPECIFIC,
        role="developer",
    )
    draft_shared = DocumentationProposal(
        key="DOC-3",
        title="Draft process",
        category=SharedDocumentationCategory.PROCESS.value,
        status=DocumentationProposalStatus.DRAFT,
        content_path=Path("docs/process.md"),
        scope=DocumentationScope.SHARED,
    )

    assert is_approved_shared_documentation(shared) is True
    assert is_approved_shared_documentation(role_note) is False
    assert is_approved_shared_documentation(draft_shared) is False


def test_approved_shared_documentation_builds_sync_decision() -> None:
    proposal = DocumentationProposal(
        key="DOC-4",
        title="Release Process",
        category=SharedDocumentationCategory.PROCESS.value,
        status=DocumentationProposalStatus.APPROVED,
        content_path=Path("docs/release-and-sprint-planning.md"),
        scope=DocumentationScope.SHARED,
    )

    decision = build_documentation_sync_decision(proposal)

    assert decision.eligible is True
    assert decision.confluence_sync_allowed is True
    assert decision.durable_subpath == Path("shared/process")
    assert decision.reason == "approved shared documentation can sync"


def test_role_specific_or_draft_documentation_is_not_sync_eligible() -> None:
    role_note = DocumentationProposal(
        key="DOC-5",
        title="Reviewer thought process",
        category=RoleSpecificNoteCategory.REVIEW.value,
        status=DocumentationProposalStatus.APPROVED,
        content_path=Path("data/role-notes/review/note.md"),
        scope=DocumentationScope.ROLE_SPECIFIC,
        role="review",
    )
    draft_shared = DocumentationProposal(
        key="DOC-6",
        title="Draft requirements",
        category=SharedDocumentationCategory.REQUIREMENTS.value,
        status=DocumentationProposalStatus.DRAFT,
        content_path=Path("docs/requirements.md"),
        scope=DocumentationScope.SHARED,
    )

    role_decision = build_documentation_sync_decision(role_note)
    draft_decision = build_documentation_sync_decision(draft_shared)

    assert role_decision.eligible is False
    assert role_decision.reason == "only approved shared documentation can sync"
    assert role_decision.confluence_sync_allowed is False
    assert draft_decision.eligible is False
    assert draft_decision.reason == "only approved shared documentation can sync"


def test_approved_shared_content_requires_sync_eligible_nonempty_body() -> None:
    proposal = DocumentationProposal(
        key="DOC-7",
        title="Architecture",
        category=SharedDocumentationCategory.ARCHITECTURE.value,
        status=DocumentationProposalStatus.APPROVED,
        content_path=Path("docs/architecture.md"),
        scope=DocumentationScope.SHARED,
        confluence_page_id="123",
    )

    content = build_approved_shared_content(proposal, body_storage="<p>Architecture</p>")

    assert content.proposal_key == "DOC-7"
    assert content.title == "Architecture"
    assert content.body_storage == "<p>Architecture</p>"
    assert content.durable_subpath == Path("shared/architecture")
    assert content.confluence_page_id == "123"

    with pytest.raises(ValueError, match="cannot be empty"):
        build_approved_shared_content(proposal, body_storage=" ")
