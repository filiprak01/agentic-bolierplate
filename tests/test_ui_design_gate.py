from agentic_boilerplate.domain import (
    UIDesignGateBlockerKind,
    UIDesignReference,
    evaluate_ui_design_gate,
    render_design_reference_section,
    render_ui_design_gate_decision,
)


def test_ui_design_gate_passes_with_accepted_design_reference() -> None:
    decision = evaluate_ui_design_gate(_accepted_reference())

    assert decision.passed is True
    assert decision.blockers == ()
    assert "AGENT-637 has an accepted design reference." in decision.reasons


def test_ui_design_gate_blocks_missing_reference_parts() -> None:
    decision = evaluate_ui_design_gate(
        UIDesignReference(
            implementation_issue_key="AGENT-637",
            design_status="DEV COMPLETED",
        )
    )

    blockers = {blocker.kind for blocker in decision.blockers}

    assert decision.passed is False
    assert UIDesignGateBlockerKind.MISSING_DESIGN_STORY in blockers
    assert UIDesignGateBlockerKind.MISSING_ARTIFACT in blockers
    assert UIDesignGateBlockerKind.MISSING_PO_ACCEPTANCE in blockers
    assert UIDesignGateBlockerKind.MISSING_BLOCKS_DEPENDENCY in blockers
    assert UIDesignGateBlockerKind.DESIGN_NOT_ACCEPTED in blockers


def test_ui_design_gate_allows_complete_product_owner_override() -> None:
    decision = evaluate_ui_design_gate(
        UIDesignReference(
            implementation_issue_key="AGENT-637",
            po_override_reference="PO inbox design-override-001",
            po_override_reason="Use existing accepted operator shell for this minor UI copy update.",
        )
    )

    assert decision.passed is True
    assert "explicit PO design override" in decision.reasons[0]


def test_ui_design_gate_rejects_partial_product_owner_override() -> None:
    decision = evaluate_ui_design_gate(
        UIDesignReference(
            implementation_issue_key="AGENT-637",
            po_override_reference="PO inbox design-override-001",
        )
    )

    assert decision.passed is False
    assert UIDesignGateBlockerKind.INCOMPLETE_PO_OVERRIDE in {blocker.kind for blocker in decision.blockers}


def test_ui_design_gate_renders_design_reference_and_decision() -> None:
    reference = _accepted_reference()

    section = render_design_reference_section(reference)
    decision = render_ui_design_gate_decision(evaluate_ui_design_gate(reference))

    assert "Design Reference:" in section
    assert "Design story: AGENT-667" in section
    assert "Product Owner acceptance: Jira comment 123" in section
    assert "# UI Design Gate - AGENT-637" in decision
    assert "- Passed: yes" in decision


def _accepted_reference() -> UIDesignReference:
    return UIDesignReference(
        implementation_issue_key="AGENT-637",
        design_issue_key="AGENT-667",
        artifact_reference="https://figma.example/file/frame",
        po_acceptance_reference="Jira comment 123",
        constraints="Use compact inbox list and accessible focus states.",
        design_status="TEST COMPLETED",
        blocks_dependency_linked=True,
    )
