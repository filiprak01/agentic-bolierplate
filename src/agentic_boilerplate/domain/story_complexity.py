"""Story complexity and Codex routing policy."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from agentic_boilerplate.domain.po_inbox import AgentRole


class ComplexityLevel(str, Enum):
    """Supported story complexity levels."""

    C1 = "C1"
    C2 = "C2"
    C3 = "C3"
    C4 = "C4"


class ReasoningLevel(str, Enum):
    """Supported Codex reasoning levels for story routing."""

    NONE = "none"
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"
    MAX = "max"
    ULTRA = "ultra"


class RoutingSource(str, Enum):
    """Whether routing came from the role matrix or complexity fallback."""

    ROLE = "role"
    COMPLEXITY_FALLBACK = "complexity_fallback"


@dataclass(frozen=True)
class ComplexityRouting:
    """Default routing for a story complexity level."""

    level: ComplexityLevel
    name: str
    points: int
    default_model: str
    reasoning: ReasoningLevel
    speed: str
    c4_justification_required: bool = False


@dataclass(frozen=True)
class RoleRouting:
    """Default routing for one worker role."""

    role: AgentRole
    default_model: str
    reasoning: ReasoningLevel
    speed: str
    rationale: str


@dataclass(frozen=True)
class ManualSwitchPromptDecision:
    """Whether the Product Owner must switch Codex settings before work starts."""

    switch_required: bool
    current_model: str
    current_reasoning: ReasoningLevel | None
    current_speed: str
    target_model: str
    target_reasoning: ReasoningLevel
    target_speed: str
    prompt: str = ""
    rationale: str = ""


DEFAULT_COMPLEXITY_ROUTING: dict[ComplexityLevel, ComplexityRouting] = {
    ComplexityLevel.C1: ComplexityRouting(
        level=ComplexityLevel.C1,
        name="Simple",
        points=1,
        default_model="gpt-5.4-mini",
        reasoning=ReasoningLevel.MEDIUM,
        speed="normal",
    ),
    ComplexityLevel.C2: ComplexityRouting(
        level=ComplexityLevel.C2,
        name="Standard",
        points=2,
        default_model="gpt-5.5",
        reasoning=ReasoningLevel.MEDIUM,
        speed="normal",
    ),
    ComplexityLevel.C3: ComplexityRouting(
        level=ComplexityLevel.C3,
        name="Complex",
        points=3,
        default_model="gpt-5.5",
        reasoning=ReasoningLevel.HIGH,
        speed="normal",
    ),
    ComplexityLevel.C4: ComplexityRouting(
        level=ComplexityLevel.C4,
        name="Critical Audit",
        points=5,
        default_model="gpt-5.5",
        reasoning=ReasoningLevel.XHIGH,
        speed="normal",
        c4_justification_required=True,
    ),
}


DEFAULT_ROLE_ROUTING: dict[AgentRole, RoleRouting] = {
    AgentRole.SCHEDULER: RoleRouting(
        role=AgentRole.SCHEDULER,
        default_model="gpt-5.5",
        reasoning=ReasoningLevel.HIGH,
        speed="normal",
        rationale="Scheduler aligns with orchestrator routing and avoids medium defaults in Release 1.1.",
    ),
    AgentRole.PRODUCT_PLANNING: RoleRouting(
        role=AgentRole.PRODUCT_PLANNING,
        default_model="gpt-5.5",
        reasoning=ReasoningLevel.XHIGH,
        speed="normal",
        rationale="Product planning uses extra-high reasoning for release scope, story shaping, and backlog decisions.",
    ),
    AgentRole.ARCHITECTURE: RoleRouting(
        role=AgentRole.ARCHITECTURE,
        default_model="gpt-5.5",
        reasoning=ReasoningLevel.XHIGH,
        speed="normal",
        rationale="Architecture work needs extra-high reasoning for cross-system decisions and tradeoffs.",
    ),
    AgentRole.DEVELOPER: RoleRouting(
        role=AgentRole.DEVELOPER,
        default_model="gpt-5.4",
        reasoning=ReasoningLevel.HIGH,
        speed="normal",
        rationale="Development defaults to gpt-5.4 high for cost-effective implementation quality.",
    ),
    AgentRole.REVIEW: RoleRouting(
        role=AgentRole.REVIEW,
        default_model="gpt-5.4",
        reasoning=ReasoningLevel.HIGH,
        speed="normal",
        rationale="Review uses gpt-5.4 high to catch correctness, security, and test risks.",
    ),
    AgentRole.TESTER: RoleRouting(
        role=AgentRole.TESTER,
        default_model="gpt-5.4-mini",
        reasoning=ReasoningLevel.HIGH,
        speed="normal",
        rationale="Testing and manual QA use high reasoning in Release 1.1 unless the PO approves a limit-saving override.",
    ),
    AgentRole.RELEASE_MANAGER: RoleRouting(
        role=AgentRole.RELEASE_MANAGER,
        default_model="gpt-5.4-mini",
        reasoning=ReasoningLevel.HIGH,
        speed="normal",
        rationale="Release manager work uses the mini model with high reasoning for reliable closure checks.",
    ),
    AgentRole.PLATFORM: RoleRouting(
        role=AgentRole.PLATFORM,
        default_model="gpt-5.4",
        reasoning=ReasoningLevel.HIGH,
        speed="normal",
        rationale="Platform work is treated like implementation-heavy infrastructure hardening.",
    ),
    AgentRole.FRONTEND: RoleRouting(
        role=AgentRole.FRONTEND,
        default_model="gpt-5.4",
        reasoning=ReasoningLevel.HIGH,
        speed="normal",
        rationale="Frontend implementation uses gpt-5.4 high for component, state, API, and accessibility work.",
    ),
    AgentRole.UI_UX: RoleRouting(
        role=AgentRole.UI_UX,
        default_model="gpt-5.4",
        reasoning=ReasoningLevel.HIGH,
        speed="normal",
        rationale="UI/UX work uses high reasoning for flows, accessibility, Figma handoff, and design tradeoffs.",
    ),
    AgentRole.SECURITY: RoleRouting(
        role=AgentRole.SECURITY,
        default_model="gpt-5.5",
        reasoning=ReasoningLevel.XHIGH,
        speed="normal",
        rationale="Security defaults to extra-high reasoning for threat models and risk-sensitive decisions.",
    ),
    AgentRole.DOCS_CONFLUENCE: RoleRouting(
        role=AgentRole.DOCS_CONFLUENCE,
        default_model="gpt-5.4-mini",
        reasoning=ReasoningLevel.HIGH,
        speed="normal",
        rationale="Docs/Confluence uses the mini model with high reasoning for publication-ready shared docs.",
    ),
    AgentRole.DEVOPS_PLATFORM: RoleRouting(
        role=AgentRole.DEVOPS_PLATFORM,
        default_model="gpt-5.4",
        reasoning=ReasoningLevel.HIGH,
        speed="normal",
        rationale="DevOps/Platform uses high reasoning for runtime, Docker, and operational safety work.",
    ),
    AgentRole.DATA_PERSISTENCE: RoleRouting(
        role=AgentRole.DATA_PERSISTENCE,
        default_model="gpt-5.4",
        reasoning=ReasoningLevel.HIGH,
        speed="normal",
        rationale="Data/Persistence uses high reasoning for storage contracts, migrations, and retention risk.",
    ),
}


@dataclass(frozen=True)
class StoryRoutingMetadata:
    """Routing metadata copied into Jira, sprint plans, and context packs."""

    complexity: ComplexityLevel
    complexity_name: str
    complexity_points: int
    model: str
    reasoning: ReasoningLevel
    speed: str
    rationale: str
    routing_source: RoutingSource = RoutingSource.COMPLEXITY_FALLBACK
    role: str = ""
    c4_justification: str | None = None


def build_story_routing_metadata(
    complexity: ComplexityLevel,
    rationale: str,
    *,
    role: AgentRole | None = None,
    c4_justification: str | None = None,
) -> StoryRoutingMetadata:
    """Build routing metadata with role-first selection and complexity fallback."""

    routing = DEFAULT_COMPLEXITY_ROUTING[complexity]
    if routing.c4_justification_required and not c4_justification:
        raise ValueError("C4 routing requires an explicit justification.")
    selected_model = routing.default_model
    selected_reasoning = routing.reasoning
    selected_speed = routing.speed
    selected_rationale = rationale
    routing_source = RoutingSource.COMPLEXITY_FALLBACK
    routing_role = ""
    role_routing = DEFAULT_ROLE_ROUTING.get(role) if role is not None else None
    if role_routing is not None:
        selected_model = role_routing.default_model
        selected_reasoning = role_routing.reasoning
        selected_speed = role_routing.speed
        selected_rationale = f"{role_routing.rationale} Complexity fallback remains {routing.level.value}."
        routing_source = RoutingSource.ROLE
        routing_role = role.value

    return StoryRoutingMetadata(
        complexity=routing.level,
        complexity_name=routing.name,
        complexity_points=routing.points,
        model=selected_model,
        reasoning=selected_reasoning,
        speed=selected_speed,
        rationale=selected_rationale,
        routing_source=routing_source,
        role=routing_role,
        c4_justification=c4_justification,
    )


def build_manual_switch_prompt(
    *,
    issue_key: str,
    role: AgentRole,
    target: StoryRoutingMetadata,
    current_model: str = "",
    current_reasoning: ReasoningLevel | None = None,
    current_speed: str = "",
) -> ManualSwitchPromptDecision:
    """Return the manual Codex settings switch checkpoint for the next task."""

    model_changed = bool(current_model.strip()) and current_model.strip() != target.model
    reasoning_changed = current_reasoning is not None and current_reasoning != target.reasoning
    speed_changed = bool(current_speed.strip()) and current_speed.strip() != target.speed
    switch_required = model_changed or reasoning_changed or speed_changed
    if not switch_required:
        return ManualSwitchPromptDecision(
            switch_required=False,
            current_model=current_model.strip(),
            current_reasoning=current_reasoning,
            current_speed=current_speed.strip(),
            target_model=target.model,
            target_reasoning=target.reasoning,
            target_speed=target.speed,
            rationale="Current Codex settings already match the selected routing.",
        )
    prompt = (
        f"Before starting {issue_key}, switch Codex to {target.model} with {target.reasoning.value} reasoning "
        f"and {target.speed} speed for the {role.value} role."
    )
    if target.reasoning == ReasoningLevel.XHIGH and not target.c4_justification:
        raise ValueError("Extra-high reasoning requires explicit justification before prompting for a switch.")
    return ManualSwitchPromptDecision(
        switch_required=True,
        current_model=current_model.strip(),
        current_reasoning=current_reasoning,
        current_speed=current_speed.strip(),
        target_model=target.model,
        target_reasoning=target.reasoning,
        target_speed=target.speed,
        prompt=prompt,
        rationale=f"Current Codex settings differ from the selected {target.routing_source.value} routing.",
    )
