from pathlib import Path

import pytest

from agentic_boilerplate.domain import (
    ADRStatus,
    ADRTemplate,
    ArchitectureDecisionSummary,
    ArchitectureDocumentStatus,
    ArchitectureDocumentTemplate,
    ArchitectureTemplateError,
    DocumentationProposalStatus,
    SharedDocumentationCategory,
    adr_to_proposal,
    architecture_document_to_proposal,
    render_adr_markdown,
    render_architecture_document_markdown,
    require_valid_adr,
    require_valid_architecture_document,
)


def sample_decision() -> ArchitectureDecisionSummary:
    return ArchitectureDecisionSummary(
        decision="Use local durable files as the first recovery source.",
        rationale="Workers must recover after container stops without requiring live APIs.",
        alternatives=("Only Jira comments", "Only Confluence pages"),
        affected_stories=("AGENT-17", "AGENT-32"),
    )


def sample_architecture_document() -> ArchitectureDocumentTemplate:
    return ArchitectureDocumentTemplate(
        title="Worker Recovery Architecture",
        owner="Architecture Agent",
        status=ArchitectureDocumentStatus.DRAFT,
        context="Workers need durable local state before remote sync.",
        goals=("Recover paused work", "Avoid losing PO questions"),
        non_goals=("Replace Jira",),
        decisions=(sample_decision(),),
        affected_stories=("AGENT-17", "AGENT-32"),
        content_path=Path("docs/architecture/worker-recovery.md"),
    )


def sample_adr() -> ADRTemplate:
    return ADRTemplate(
        title="ADR-0001 Durable Files Before Remote Sync",
        owner="Architecture Agent",
        status=ADRStatus.PROPOSED,
        decision="Persist local artifacts before remote sync attempts.",
        rationale="Local durability protects work when network or limits fail.",
        alternatives=("Remote-only sync", "In-memory state"),
        affected_stories=("AGENT-17", "AGENT-32"),
        consequences=("Workers need mounted durable volumes.",),
        content_path=Path("docs/adrs/0001-durable-files.md"),
    )


def test_architecture_document_requires_decision_fields() -> None:
    template = sample_architecture_document()

    require_valid_architecture_document(template)

    assert template.owner == "Architecture Agent"
    assert template.status == ArchitectureDocumentStatus.DRAFT
    assert template.decisions[0].decision.startswith("Use local durable files")
    assert template.decisions[0].rationale
    assert template.decisions[0].alternatives
    assert template.decisions[0].affected_stories == ("AGENT-17", "AGENT-32")


def test_adr_requires_owner_status_decision_rationale_alternatives_and_stories() -> None:
    template = sample_adr()

    require_valid_adr(template)

    assert template.owner == "Architecture Agent"
    assert template.status == ADRStatus.PROPOSED
    assert template.decision.startswith("Persist local artifacts")
    assert template.rationale
    assert template.alternatives == ("Remote-only sync", "In-memory state")
    assert template.affected_stories == ("AGENT-17", "AGENT-32")


def test_missing_required_template_fields_are_rejected() -> None:
    invalid_adr = ADRTemplate(
        title="Missing decision",
        owner="Architecture Agent",
        status=ADRStatus.PROPOSED,
        decision=" ",
        rationale="Needed for test",
        alternatives=("Keep existing",),
        affected_stories=("AGENT-33",),
        consequences=(),
        content_path=Path("docs/adrs/missing.md"),
    )

    with pytest.raises(ArchitectureTemplateError, match="decision is required"):
        require_valid_adr(invalid_adr)


def test_architecture_and_adr_templates_create_governance_proposals() -> None:
    architecture_proposal = architecture_document_to_proposal(
        sample_architecture_document(),
        proposal_key="DOC-ARCH-1",
        proposal_status=DocumentationProposalStatus.PROPOSED,
    )
    adr_proposal = adr_to_proposal(
        sample_adr(),
        proposal_key="DOC-ADR-1",
    )

    assert architecture_proposal.category == SharedDocumentationCategory.ARCHITECTURE.value
    assert architecture_proposal.status == DocumentationProposalStatus.PROPOSED
    assert architecture_proposal.content_path == Path("docs/architecture/worker-recovery.md")
    assert adr_proposal.category == SharedDocumentationCategory.ADR.value
    assert adr_proposal.status == DocumentationProposalStatus.DRAFT
    assert adr_proposal.content_path == Path("docs/adrs/0001-durable-files.md")


def test_architecture_document_renders_required_markdown_sections() -> None:
    markdown = render_architecture_document_markdown(sample_architecture_document())

    assert "# Worker Recovery Architecture" in markdown
    assert "owner: Architecture Agent" in markdown
    assert "status: draft" in markdown
    assert "## Context" in markdown
    assert "## Goals" in markdown
    assert "## Decisions" in markdown
    assert "Decision: Use local durable files as the first recovery source." in markdown
    assert "Rationale: Workers must recover after container stops" in markdown
    assert "- Only Jira comments" in markdown
    assert "- AGENT-17" in markdown


def test_adr_renders_required_markdown_sections() -> None:
    markdown = render_adr_markdown(sample_adr())

    assert "# ADR-0001 Durable Files Before Remote Sync" in markdown
    assert "owner: Architecture Agent" in markdown
    assert "status: proposed" in markdown
    assert "## Decision" in markdown
    assert "Persist local artifacts before remote sync attempts." in markdown
    assert "## Rationale" in markdown
    assert "Local durability protects work" in markdown
    assert "## Alternatives" in markdown
    assert "- Remote-only sync" in markdown
    assert "## Affected Stories" in markdown
    assert "- AGENT-32" in markdown
