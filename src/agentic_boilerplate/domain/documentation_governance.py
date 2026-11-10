"""Documentation governance policy for shared and role-specific content."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class DocumentationScope(str, Enum):
    """Supported documentation visibility scopes."""

    SHARED = "shared"
    ROLE_SPECIFIC = "role_specific"


class SharedDocumentationCategory(str, Enum):
    """Documentation categories that can become shared approved truth."""

    PRODUCT_VISION = "product_vision"
    REQUIREMENTS = "requirements"
    ARCHITECTURE = "architecture"
    ADR = "adr"
    PROCESS = "process"
    RELEASE = "release"


class RoleSpecificNoteCategory(str, Enum):
    """Role-specific note categories that must not be treated as approved truth."""

    PRODUCT_PLANNING = "product_planning"
    ARCHITECTURE = "architecture"
    DEVELOPER = "developer"
    REVIEW = "review"
    TESTER = "tester"
    RELEASE_MANAGER = "release_manager"


class DocumentationProposalStatus(str, Enum):
    """Approval flow for documentation proposals."""

    DRAFT = "draft"
    PROPOSED = "proposed"
    PO_REVIEW = "po_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


TERMINAL_DOCUMENTATION_STATUSES = frozenset(
    {
        DocumentationProposalStatus.REJECTED,
        DocumentationProposalStatus.SUPERSEDED,
    }
)


ALLOWED_DOCUMENTATION_STATUS_TRANSITIONS: dict[
    DocumentationProposalStatus,
    frozenset[DocumentationProposalStatus],
] = {
    DocumentationProposalStatus.DRAFT: frozenset(
        {
            DocumentationProposalStatus.PROPOSED,
            DocumentationProposalStatus.REJECTED,
        }
    ),
    DocumentationProposalStatus.PROPOSED: frozenset(
        {
            DocumentationProposalStatus.PO_REVIEW,
            DocumentationProposalStatus.DRAFT,
            DocumentationProposalStatus.REJECTED,
        }
    ),
    DocumentationProposalStatus.PO_REVIEW: frozenset(
        {
            DocumentationProposalStatus.APPROVED,
            DocumentationProposalStatus.PROPOSED,
            DocumentationProposalStatus.REJECTED,
        }
    ),
    DocumentationProposalStatus.APPROVED: frozenset(
        {
            DocumentationProposalStatus.SUPERSEDED,
        }
    ),
    DocumentationProposalStatus.REJECTED: frozenset(),
    DocumentationProposalStatus.SUPERSEDED: frozenset(),
}


@dataclass(frozen=True)
class DocumentationCategoryRule:
    """Governance rule for one documentation category."""

    category: str
    scope: DocumentationScope
    durable_subpath: Path
    confluence_sync_allowed: bool


@dataclass(frozen=True)
class DocumentationProposal:
    """One documentation item proposed by an agent or the Product Owner."""

    key: str
    title: str
    category: str
    status: DocumentationProposalStatus
    content_path: Path
    scope: DocumentationScope
    role: str = ""
    confluence_page_id: str = ""


@dataclass(frozen=True)
class DocumentationSyncDecision:
    """Decision explaining whether documentation can sync to shared stores."""

    proposal_key: str
    eligible: bool
    reason: str
    durable_subpath: Path
    confluence_sync_allowed: bool


@dataclass(frozen=True)
class ApprovedSharedDocumentationContent:
    """Approved shared content ready for adapter-level Confluence/local sync."""

    proposal_key: str
    title: str
    body_storage: str
    durable_subpath: Path
    confluence_page_id: str = ""


SHARED_DOCUMENTATION_RULES: dict[SharedDocumentationCategory, DocumentationCategoryRule] = {
    SharedDocumentationCategory.PRODUCT_VISION: DocumentationCategoryRule(
        category=SharedDocumentationCategory.PRODUCT_VISION.value,
        scope=DocumentationScope.SHARED,
        durable_subpath=Path("shared/product"),
        confluence_sync_allowed=True,
    ),
    SharedDocumentationCategory.REQUIREMENTS: DocumentationCategoryRule(
        category=SharedDocumentationCategory.REQUIREMENTS.value,
        scope=DocumentationScope.SHARED,
        durable_subpath=Path("shared/requirements"),
        confluence_sync_allowed=True,
    ),
    SharedDocumentationCategory.ARCHITECTURE: DocumentationCategoryRule(
        category=SharedDocumentationCategory.ARCHITECTURE.value,
        scope=DocumentationScope.SHARED,
        durable_subpath=Path("shared/architecture"),
        confluence_sync_allowed=True,
    ),
    SharedDocumentationCategory.ADR: DocumentationCategoryRule(
        category=SharedDocumentationCategory.ADR.value,
        scope=DocumentationScope.SHARED,
        durable_subpath=Path("shared/adrs"),
        confluence_sync_allowed=True,
    ),
    SharedDocumentationCategory.PROCESS: DocumentationCategoryRule(
        category=SharedDocumentationCategory.PROCESS.value,
        scope=DocumentationScope.SHARED,
        durable_subpath=Path("shared/process"),
        confluence_sync_allowed=True,
    ),
    SharedDocumentationCategory.RELEASE: DocumentationCategoryRule(
        category=SharedDocumentationCategory.RELEASE.value,
        scope=DocumentationScope.SHARED,
        durable_subpath=Path("shared/release"),
        confluence_sync_allowed=True,
    ),
}


ROLE_SPECIFIC_DOCUMENTATION_RULES: dict[RoleSpecificNoteCategory, DocumentationCategoryRule] = {
    category: DocumentationCategoryRule(
        category=category.value,
        scope=DocumentationScope.ROLE_SPECIFIC,
        durable_subpath=Path("role-notes") / category.value,
        confluence_sync_allowed=False,
    )
    for category in RoleSpecificNoteCategory
}


def documentation_rule_for_category(category: str) -> DocumentationCategoryRule:
    """Return the governance rule for a shared or role-specific category."""

    normalized = category.strip().lower()
    for shared_category, rule in SHARED_DOCUMENTATION_RULES.items():
        if shared_category.value == normalized:
            return rule
    for role_category, rule in ROLE_SPECIFIC_DOCUMENTATION_RULES.items():
        if role_category.value == normalized:
            return rule
    raise ValueError(f"Unknown documentation category: {category}")


def can_transition_documentation_status(
    current: DocumentationProposalStatus,
    target: DocumentationProposalStatus,
) -> bool:
    """Return whether a documentation proposal can move to target status."""

    return target in ALLOWED_DOCUMENTATION_STATUS_TRANSITIONS[current]


def is_approved_shared_documentation(proposal: DocumentationProposal) -> bool:
    """Return whether a proposal can be treated as approved shared truth."""

    return (
        proposal.scope == DocumentationScope.SHARED
        and proposal.status == DocumentationProposalStatus.APPROVED
    )


def build_documentation_sync_decision(proposal: DocumentationProposal) -> DocumentationSyncDecision:
    """Build a local sync decision for Confluence and durable mirror workflows."""

    rule = documentation_rule_for_category(proposal.category)
    if proposal.scope != rule.scope:
        return DocumentationSyncDecision(
            proposal_key=proposal.key,
            eligible=False,
            reason="proposal scope does not match category governance rule",
            durable_subpath=rule.durable_subpath,
            confluence_sync_allowed=False,
        )
    if not is_approved_shared_documentation(proposal):
        return DocumentationSyncDecision(
            proposal_key=proposal.key,
            eligible=False,
            reason="only approved shared documentation can sync",
            durable_subpath=rule.durable_subpath,
            confluence_sync_allowed=False,
        )
    if not rule.confluence_sync_allowed:
        return DocumentationSyncDecision(
            proposal_key=proposal.key,
            eligible=False,
            reason="category is not allowed to sync to Confluence",
            durable_subpath=rule.durable_subpath,
            confluence_sync_allowed=False,
        )
    return DocumentationSyncDecision(
        proposal_key=proposal.key,
        eligible=True,
        reason="approved shared documentation can sync",
        durable_subpath=rule.durable_subpath,
        confluence_sync_allowed=True,
    )


def build_approved_shared_content(
    proposal: DocumentationProposal,
    *,
    body_storage: str,
) -> ApprovedSharedDocumentationContent:
    """Build sync-ready shared content or reject ineligible proposals."""

    decision = build_documentation_sync_decision(proposal)
    if not decision.eligible:
        raise ValueError(f"Documentation proposal is not sync eligible: {decision.reason}")
    if not body_storage.strip():
        raise ValueError("Approved shared documentation content cannot be empty.")
    return ApprovedSharedDocumentationContent(
        proposal_key=proposal.key,
        title=proposal.title,
        body_storage=body_storage,
        durable_subpath=decision.durable_subpath,
        confluence_page_id=proposal.confluence_page_id,
    )
