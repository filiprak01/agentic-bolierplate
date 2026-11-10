import pytest

from agentic_boilerplate.domain.story_complexity import (
    DEFAULT_ROLE_ROUTING,
    ManualSwitchPromptDecision,
    ComplexityLevel,
    DEFAULT_COMPLEXITY_ROUTING,
    RoutingSource,
    ReasoningLevel,
    build_manual_switch_prompt,
    build_story_routing_metadata,
)
from agentic_boilerplate.domain.po_inbox import AgentRole


def test_default_complexity_routing() -> None:
    assert DEFAULT_COMPLEXITY_ROUTING[ComplexityLevel.C1].points == 1
    assert DEFAULT_COMPLEXITY_ROUTING[ComplexityLevel.C1].default_model == "gpt-5.4-mini"
    assert DEFAULT_COMPLEXITY_ROUTING[ComplexityLevel.C1].reasoning == ReasoningLevel.MEDIUM

    assert DEFAULT_COMPLEXITY_ROUTING[ComplexityLevel.C2].points == 2
    assert DEFAULT_COMPLEXITY_ROUTING[ComplexityLevel.C2].default_model == "gpt-5.5"
    assert DEFAULT_COMPLEXITY_ROUTING[ComplexityLevel.C2].reasoning == ReasoningLevel.MEDIUM

    assert DEFAULT_COMPLEXITY_ROUTING[ComplexityLevel.C3].points == 3
    assert DEFAULT_COMPLEXITY_ROUTING[ComplexityLevel.C3].default_model == "gpt-5.5"
    assert DEFAULT_COMPLEXITY_ROUTING[ComplexityLevel.C3].reasoning == ReasoningLevel.HIGH

    assert DEFAULT_COMPLEXITY_ROUTING[ComplexityLevel.C4].points == 5
    assert DEFAULT_COMPLEXITY_ROUTING[ComplexityLevel.C4].default_model == "gpt-5.5"
    assert DEFAULT_COMPLEXITY_ROUTING[ComplexityLevel.C4].reasoning == ReasoningLevel.XHIGH
    assert DEFAULT_COMPLEXITY_ROUTING[ComplexityLevel.C4].c4_justification_required
    assert DEFAULT_ROLE_ROUTING[AgentRole.DEVELOPER].default_model == "gpt-5.4"
    assert DEFAULT_ROLE_ROUTING[AgentRole.TESTER].default_model == "gpt-5.4-mini"
    assert DEFAULT_ROLE_ROUTING[AgentRole.SCHEDULER].reasoning == ReasoningLevel.HIGH
    assert DEFAULT_ROLE_ROUTING[AgentRole.PRODUCT_PLANNING].reasoning == ReasoningLevel.XHIGH
    assert DEFAULT_ROLE_ROUTING[AgentRole.ARCHITECTURE].reasoning == ReasoningLevel.XHIGH
    assert DEFAULT_ROLE_ROUTING[AgentRole.SECURITY].default_model == "gpt-5.5"
    assert DEFAULT_ROLE_ROUTING[AgentRole.SECURITY].reasoning == ReasoningLevel.XHIGH


def test_release_11_role_routing_covers_expanded_roles_without_medium_defaults() -> None:
    expected_roles = {
        AgentRole.FRONTEND,
        AgentRole.UI_UX,
        AgentRole.SECURITY,
        AgentRole.DOCS_CONFLUENCE,
        AgentRole.DEVOPS_PLATFORM,
        AgentRole.DATA_PERSISTENCE,
    }

    assert expected_roles.issubset(DEFAULT_ROLE_ROUTING)
    assert all(routing.reasoning != ReasoningLevel.MEDIUM for routing in DEFAULT_ROLE_ROUTING.values())


def test_story_routing_metadata_uses_defaults() -> None:
    metadata = build_story_routing_metadata(
        ComplexityLevel.C3,
        "External integration behavior crosses module boundaries.",
    )

    assert metadata.complexity == ComplexityLevel.C3
    assert metadata.complexity_name == "Complex"
    assert metadata.complexity_points == 3
    assert metadata.model == "gpt-5.5"
    assert metadata.reasoning == ReasoningLevel.HIGH
    assert metadata.speed == "normal"
    assert metadata.c4_justification is None
    assert metadata.routing_source == RoutingSource.COMPLEXITY_FALLBACK
    assert metadata.role == ""


def test_story_routing_metadata_uses_role_matrix_before_complexity_fallback() -> None:
    metadata = build_story_routing_metadata(
        ComplexityLevel.C1,
        "Simple implementation story.",
        role=AgentRole.DEVELOPER,
    )

    assert metadata.model == "gpt-5.4"
    assert metadata.reasoning == ReasoningLevel.HIGH
    assert metadata.speed == "normal"
    assert metadata.routing_source == RoutingSource.ROLE
    assert metadata.role == "developer"
    assert "Complexity fallback remains C1" in metadata.rationale


def test_c4_requires_explicit_justification() -> None:
    with pytest.raises(ValueError, match="C4 routing requires"):
        build_story_routing_metadata(ComplexityLevel.C4, "Broad audit")

    metadata = build_story_routing_metadata(
        ComplexityLevel.C4,
        "Security-sensitive broad architecture review.",
        c4_justification="One-time pre-approval audit before release scope starts.",
    )

    assert metadata.reasoning == ReasoningLevel.XHIGH
    assert metadata.c4_justification == "One-time pre-approval audit before release scope starts."


def test_manual_switch_prompt_is_created_when_session_settings_differ() -> None:
    target = build_story_routing_metadata(
        ComplexityLevel.C3,
        "Scheduler handoff to developer.",
        role=AgentRole.DEVELOPER,
    )

    decision = build_manual_switch_prompt(
        issue_key="AGENT-337",
        role=AgentRole.DEVELOPER,
        target=target,
        current_model="gpt-5.5",
        current_reasoning=ReasoningLevel.XHIGH,
        current_speed="normal",
    )

    assert isinstance(decision, ManualSwitchPromptDecision)
    assert decision.switch_required is True
    assert "switch Codex to gpt-5.4 with high reasoning" in decision.prompt


def test_manual_switch_prompt_is_not_required_when_settings_already_match() -> None:
    target = build_story_routing_metadata(
        ComplexityLevel.C3,
        "Review handoff stays on same routing.",
        role=AgentRole.REVIEW,
    )

    decision = build_manual_switch_prompt(
        issue_key="AGENT-337",
        role=AgentRole.REVIEW,
        target=target,
        current_model="gpt-5.4",
        current_reasoning=ReasoningLevel.HIGH,
        current_speed="normal",
    )

    assert decision.switch_required is False
    assert decision.prompt == ""
