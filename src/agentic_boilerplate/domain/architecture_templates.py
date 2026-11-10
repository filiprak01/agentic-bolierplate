"""Architecture document and ADR template models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from agentic_boilerplate.domain.documentation_governance import (
    DocumentationProposal,
    DocumentationProposalStatus,
    DocumentationScope,
    SharedDocumentationCategory,
)


class ArchitectureTemplateError(ValueError):
    """Raised when architecture template data is incomplete."""


class ArchitectureDocumentStatus(str, Enum):
    """Architecture document lifecycle status."""

    DRAFT = "draft"
    PROPOSED = "proposed"
    APPROVED = "approved"
    SUPERSEDED = "superseded"


class ADRStatus(str, Enum):
    """Architecture Decision Record lifecycle status."""

    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


@dataclass(frozen=True)
class ArchitectureDecisionSummary:
    """Decision summary embedded in architecture documents."""

    decision: str
    rationale: str
    alternatives: tuple[str, ...]
    affected_stories: tuple[str, ...]


@dataclass(frozen=True)
class ArchitectureDocumentTemplate:
    """Architecture document template data."""

    title: str
    owner: str
    status: ArchitectureDocumentStatus
    context: str
    goals: tuple[str, ...]
    non_goals: tuple[str, ...]
    decisions: tuple[ArchitectureDecisionSummary, ...]
    affected_stories: tuple[str, ...]
    content_path: Path


@dataclass(frozen=True)
class ADRTemplate:
    """Architecture Decision Record template data."""

    title: str
    owner: str
    status: ADRStatus
    decision: str
    rationale: str
    alternatives: tuple[str, ...]
    affected_stories: tuple[str, ...]
    consequences: tuple[str, ...]
    content_path: Path


def require_valid_architecture_document(template: ArchitectureDocumentTemplate) -> None:
    """Raise when an architecture document template is missing required data."""

    _require_text("title", template.title)
    _require_text("owner", template.owner)
    _require_text("context", template.context)
    _require_items("goals", template.goals)
    _require_items("affected_stories", template.affected_stories)
    if not template.decisions:
        raise ArchitectureTemplateError("architecture document requires at least one decision summary")
    for index, decision in enumerate(template.decisions, start=1):
        require_valid_decision_summary(decision, label=f"decisions[{index}]")


def require_valid_adr(template: ADRTemplate) -> None:
    """Raise when an ADR template is missing required data."""

    _require_text("title", template.title)
    _require_text("owner", template.owner)
    _require_text("decision", template.decision)
    _require_text("rationale", template.rationale)
    _require_items("alternatives", template.alternatives)
    _require_items("affected_stories", template.affected_stories)


def require_valid_decision_summary(
    decision: ArchitectureDecisionSummary,
    *,
    label: str = "decision",
) -> None:
    """Raise when a decision summary is missing required data."""

    _require_text(f"{label}.decision", decision.decision)
    _require_text(f"{label}.rationale", decision.rationale)
    _require_items(f"{label}.alternatives", decision.alternatives)
    _require_items(f"{label}.affected_stories", decision.affected_stories)


def architecture_document_to_proposal(
    template: ArchitectureDocumentTemplate,
    *,
    proposal_key: str,
    proposal_status: DocumentationProposalStatus = DocumentationProposalStatus.DRAFT,
) -> DocumentationProposal:
    """Create a governance proposal for an architecture document template."""

    require_valid_architecture_document(template)
    return DocumentationProposal(
        key=proposal_key,
        title=template.title,
        category=SharedDocumentationCategory.ARCHITECTURE.value,
        status=proposal_status,
        content_path=template.content_path,
        scope=DocumentationScope.SHARED,
    )


def adr_to_proposal(
    template: ADRTemplate,
    *,
    proposal_key: str,
    proposal_status: DocumentationProposalStatus = DocumentationProposalStatus.DRAFT,
) -> DocumentationProposal:
    """Create a governance proposal for an ADR template."""

    require_valid_adr(template)
    return DocumentationProposal(
        key=proposal_key,
        title=template.title,
        category=SharedDocumentationCategory.ADR.value,
        status=proposal_status,
        content_path=template.content_path,
        scope=DocumentationScope.SHARED,
    )


def render_architecture_document_markdown(template: ArchitectureDocumentTemplate) -> str:
    """Render an architecture document template to Markdown."""

    require_valid_architecture_document(template)
    lines: list[str] = [
        f"# {template.title}",
        "",
        f"owner: {template.owner}",
        f"status: {template.status.value}",
        "category: architecture",
        "scope: shared",
        "",
        "## Context",
        "",
        template.context,
        "",
        "## Goals",
        "",
        *_bullet_lines(template.goals),
    ]
    if template.non_goals:
        lines.extend(
            [
                "",
                "## Non-Goals",
                "",
                *_bullet_lines(template.non_goals),
            ]
        )
    lines.extend(
        [
            "",
            "## Decisions",
            "",
        ]
    )
    for index, decision in enumerate(template.decisions, start=1):
        lines.extend(
            [
                f"### Decision {index}",
                "",
                f"Decision: {decision.decision}",
                "",
                f"Rationale: {decision.rationale}",
                "",
                "Alternatives:",
                *_bullet_lines(decision.alternatives),
                "",
                "Affected stories:",
                *_bullet_lines(decision.affected_stories),
                "",
            ]
        )
    lines.extend(
        [
            "## Affected Stories",
            "",
            *_bullet_lines(template.affected_stories),
            "",
        ]
    )
    return "\n".join(lines)


def render_adr_markdown(template: ADRTemplate) -> str:
    """Render an Architecture Decision Record template to Markdown."""

    require_valid_adr(template)
    lines: list[str] = [
        f"# {template.title}",
        "",
        f"owner: {template.owner}",
        f"status: {template.status.value}",
        "category: adr",
        "scope: shared",
        "",
        "## Decision",
        "",
        template.decision,
        "",
        "## Rationale",
        "",
        template.rationale,
        "",
        "## Alternatives",
        "",
        *_bullet_lines(template.alternatives),
        "",
        "## Consequences",
        "",
        *_bullet_lines(template.consequences or ("Not documented yet.",)),
        "",
        "## Affected Stories",
        "",
        *_bullet_lines(template.affected_stories),
        "",
    ]
    return "\n".join(lines)


def _require_text(field_name: str, value: str) -> None:
    if not value.strip():
        raise ArchitectureTemplateError(f"{field_name} is required")


def _require_items(field_name: str, value: tuple[str, ...]) -> None:
    if not value:
        raise ArchitectureTemplateError(f"{field_name} requires at least one item")
    for index, item in enumerate(value, start=1):
        if not item.strip():
            raise ArchitectureTemplateError(f"{field_name}[{index}] is required")


def _bullet_lines(items: tuple[str, ...]) -> list[str]:
    return [f"- {item}" for item in items]
