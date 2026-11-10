"""Product Planning Agent backlog draft workflow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agentic_boilerplate.domain.po_inbox import (
    AgentRole,
    InboxMessageType,
    InboxOption,
    InboxStatus,
    POInboxItem,
    require_valid_inbox_item,
)
from agentic_boilerplate.domain.story_complexity import (
    ComplexityLevel,
    ReasoningLevel,
    RoutingSource,
    StoryRoutingMetadata,
    build_story_routing_metadata,
)


class BacklogDraftError(ValueError):
    """Raised when backlog draft input is incomplete."""


@dataclass(frozen=True)
class AcceptanceCriterionDraft:
    """Draft acceptance criterion for a local backlog story."""

    id: str
    description: str


@dataclass(frozen=True)
class BacklogDependencyDraft:
    """Draft dependency between local backlog stories."""

    prerequisite_story_id: str
    dependent_story_id: str
    link_type: str = "blocks"


@dataclass(frozen=True)
class RequirementStoryInput:
    """Structured story input extracted from requirements."""

    id: str
    title: str
    description: str
    acceptance_criteria: tuple[str, ...]
    prerequisite_story_ids: tuple[str, ...]
    complexity: ComplexityLevel
    complexity_rationale: str
    role: AgentRole | None = None


@dataclass(frozen=True)
class RequirementSprintInput:
    """Structured sprint slice proposed from release requirements."""

    id: str
    name: str
    goal: str
    story_ids: tuple[str, ...]
    capacity_note: str = ""


@dataclass(frozen=True)
class RequirementEpicInput:
    """Structured epic input extracted from requirements."""

    id: str
    title: str
    description: str
    stories: tuple[RequirementStoryInput, ...]


@dataclass(frozen=True)
class MissingBusinessDecision:
    """Business decision the Product Planning Agent must ask the PO to answer."""

    id: str
    title: str
    question: str
    business_impact: str
    recommendation: str
    affected_story_ids: tuple[str, ...]


@dataclass(frozen=True)
class RequirementInput:
    """Requirement input used to create a local backlog draft."""

    key: str
    title: str
    overview: str
    epics: tuple[RequirementEpicInput, ...]
    sprint_rings: tuple[RequirementSprintInput, ...] = ()
    missing_business_decisions: tuple[MissingBusinessDecision, ...] = ()


@dataclass(frozen=True)
class BacklogStoryDraft:
    """Local story draft awaiting Product Owner review."""

    id: str
    title: str
    description: str
    acceptance_criteria: tuple[AcceptanceCriterionDraft, ...]
    dependencies: tuple[BacklogDependencyDraft, ...]
    complexity: StoryRoutingMetadata


@dataclass(frozen=True)
class BacklogEpicDraft:
    """Local epic draft awaiting Product Owner review."""

    id: str
    title: str
    description: str
    stories: tuple[BacklogStoryDraft, ...]


@dataclass(frozen=True)
class BacklogSprintDraft:
    """Draft sprint slice for Product Owner review."""

    id: str
    name: str
    goal: str
    story_ids: tuple[str, ...]
    capacity_note: str = ""


@dataclass(frozen=True)
class BacklogDraft:
    """Local backlog draft created before Jira story creation."""

    key: str
    title: str
    overview: str
    created_at: str
    epics: tuple[BacklogEpicDraft, ...]
    sprint_rings: tuple[BacklogSprintDraft, ...] = ()
    missing_business_decisions: tuple[MissingBusinessDecision, ...] = ()


def create_backlog_draft(requirement: RequirementInput, *, created_at: str) -> BacklogDraft:
    """Convert structured requirements into a local backlog draft."""

    _require_text("key", requirement.key)
    _require_text("title", requirement.title)
    _require_text("overview", requirement.overview)
    _require_text("created_at", created_at)
    if not requirement.epics:
        raise BacklogDraftError("at least one epic is required")

    epics = tuple(_create_epic_draft(epic) for epic in requirement.epics)
    _require_unique_ids("epic ids", tuple(epic.id for epic in epics))
    story_ids = tuple(story.id for epic in epics for story in epic.stories)
    _require_unique_ids("story ids", story_ids)
    sprint_rings = tuple(_create_sprint_draft(sprint, story_ids=story_ids) for sprint in requirement.sprint_rings)
    _require_unique_ids("sprint ring ids", tuple(sprint.id for sprint in sprint_rings))
    _validate_missing_business_decisions(requirement.missing_business_decisions)
    return BacklogDraft(
        key=requirement.key,
        title=requirement.title,
        overview=requirement.overview,
        created_at=created_at,
        epics=epics,
        sprint_rings=sprint_rings,
        missing_business_decisions=requirement.missing_business_decisions,
    )


def build_missing_business_decision_questions(
    draft: BacklogDraft,
    *,
    created_at: str,
    jira_issue_key: str = "",
    agent_id: str = "product-planning-agent",
    context_pack_path: str = "",
) -> tuple[POInboxItem, ...]:
    """Build PO inbox questions for missing business decisions in a draft."""

    _require_text("created_at", created_at)
    questions: list[POInboxItem] = []
    for decision in draft.missing_business_decisions:
        item = POInboxItem(
            id=f"{draft.key}-decision-{decision.id}",
            message_type=InboxMessageType.BLOCKING_QUESTION,
            status=InboxStatus.OPEN,
            title=decision.title,
            message=(
                f"{decision.question}\n\n"
                f"Backlog draft: {draft.title}\n"
                f"Affected draft stories: {', '.join(decision.affected_story_ids)}"
            ),
            agent_role=AgentRole.PRODUCT_PLANNING,
            created_at=created_at,
            agent_id=agent_id,
            jira_issue_key=jira_issue_key,
            context_pack_path=context_pack_path,
            business_impact=decision.business_impact,
            recommendation=decision.recommendation,
            options=(
                InboxOption(
                    id="answer_now",
                    label="Answer now",
                    description="Product Owner provides the missing decision so drafts can proceed.",
                ),
                InboxOption(
                    id="split_follow_up",
                    label="Split follow-up",
                    description="Product Owner asks the planner to split the uncertain scope into later work.",
                ),
            ),
        )
        questions.append(require_valid_inbox_item(item))
    return tuple(questions)


def backlog_draft_to_dict(draft: BacklogDraft) -> dict[str, Any]:
    """Convert a backlog draft into JSON-compatible data."""

    _validate_backlog_draft(draft)
    return {
        "key": draft.key,
        "title": draft.title,
        "overview": draft.overview,
        "created_at": draft.created_at,
        "epics": [
            {
                "id": epic.id,
                "title": epic.title,
                "description": epic.description,
                "stories": [
                    {
                        "id": story.id,
                        "title": story.title,
                        "description": story.description,
                        "acceptance_criteria": [
                            {
                                "id": criterion.id,
                                "description": criterion.description,
                            }
                            for criterion in story.acceptance_criteria
                        ],
                        "dependencies": [
                            {
                                "prerequisite_story_id": dependency.prerequisite_story_id,
                                "dependent_story_id": dependency.dependent_story_id,
                                "link_type": dependency.link_type,
                            }
                            for dependency in story.dependencies
                        ],
                        "complexity": _complexity_to_dict(story.complexity),
                    }
                    for story in epic.stories
                ],
            }
            for epic in draft.epics
        ],
        "sprint_rings": [
            {
                "id": sprint.id,
                "name": sprint.name,
                "goal": sprint.goal,
                "story_ids": list(sprint.story_ids),
                "capacity_note": sprint.capacity_note,
            }
            for sprint in draft.sprint_rings
        ],
        "missing_business_decisions": [
            {
                "id": decision.id,
                "title": decision.title,
                "question": decision.question,
                "business_impact": decision.business_impact,
                "recommendation": decision.recommendation,
                "affected_story_ids": list(decision.affected_story_ids),
            }
            for decision in draft.missing_business_decisions
        ],
    }


def backlog_draft_from_dict(data: dict[str, Any]) -> BacklogDraft:
    """Build a backlog draft from JSON-compatible data."""

    draft = BacklogDraft(
        key=_optional_text(data.get("key")),
        title=_optional_text(data.get("title")),
        overview=_optional_text(data.get("overview")),
        created_at=_optional_text(data.get("created_at")),
        epics=tuple(_epic_draft_from_dict(epic) for epic in data.get("epics", ())),
        sprint_rings=tuple(_sprint_draft_from_dict(sprint) for sprint in data.get("sprint_rings", ())),
        missing_business_decisions=tuple(
            _missing_business_decision_from_dict(decision)
            for decision in data.get("missing_business_decisions", ())
        ),
    )
    _validate_backlog_draft(draft)
    return draft


def requirement_input_from_dict(data: dict[str, Any]) -> RequirementInput:
    """Build structured requirement input from approved source JSON."""

    return RequirementInput(
        key=_optional_text(data.get("key")),
        title=_optional_text(data.get("title")),
        overview=_optional_text(data.get("overview")),
        epics=tuple(_requirement_epic_from_dict(epic) for epic in data.get("epics", ())),
        sprint_rings=tuple(_requirement_sprint_from_dict(sprint) for sprint in data.get("sprint_rings", ())),
        missing_business_decisions=tuple(
            _missing_business_decision_from_dict(decision)
            for decision in data.get("missing_business_decisions", ())
        ),
    )


def _create_epic_draft(epic: RequirementEpicInput) -> BacklogEpicDraft:
    _require_text("epic.id", epic.id)
    _require_text("epic.title", epic.title)
    _require_text("epic.description", epic.description)
    if not epic.stories:
        raise BacklogDraftError(f"epic {epic.id} requires at least one story")
    return BacklogEpicDraft(
        id=epic.id,
        title=epic.title,
        description=epic.description,
        stories=tuple(_create_story_draft(story) for story in epic.stories),
    )


def _create_story_draft(story: RequirementStoryInput) -> BacklogStoryDraft:
    _require_text("story.id", story.id)
    _require_text("story.title", story.title)
    _require_text("story.description", story.description)
    _require_items("story.acceptance_criteria", story.acceptance_criteria)
    _require_text("story.complexity_rationale", story.complexity_rationale)
    for index, prerequisite_id in enumerate(story.prerequisite_story_ids):
        _require_text(f"story.prerequisite_story_ids[{index}]", prerequisite_id)
    acceptance_criteria = tuple(
        AcceptanceCriterionDraft(
            id=f"{story.id}-AC{index}",
            description=description,
        )
        for index, description in enumerate(story.acceptance_criteria, start=1)
    )
    dependencies = tuple(
        BacklogDependencyDraft(
            prerequisite_story_id=prerequisite_id,
            dependent_story_id=story.id,
        )
        for prerequisite_id in story.prerequisite_story_ids
    )
    return BacklogStoryDraft(
        id=story.id,
        title=story.title,
        description=story.description,
        acceptance_criteria=acceptance_criteria,
        dependencies=dependencies,
        complexity=build_story_routing_metadata(
            story.complexity,
            story.complexity_rationale,
            role=story.role,
        ),
    )


def _create_sprint_draft(sprint: RequirementSprintInput, *, story_ids: tuple[str, ...]) -> BacklogSprintDraft:
    _require_text("sprint.id", sprint.id)
    _require_text("sprint.name", sprint.name)
    _require_text("sprint.goal", sprint.goal)
    _require_items("sprint.story_ids", sprint.story_ids)
    missing_story_ids = tuple(story_id for story_id in sprint.story_ids if story_id not in story_ids)
    if missing_story_ids:
        raise BacklogDraftError(f"sprint {sprint.id} references unknown story ids: {', '.join(missing_story_ids)}")
    return BacklogSprintDraft(
        id=sprint.id,
        name=sprint.name,
        goal=sprint.goal,
        story_ids=sprint.story_ids,
        capacity_note=sprint.capacity_note,
    )


def _validate_missing_business_decisions(decisions: tuple[MissingBusinessDecision, ...]) -> None:
    _require_unique_ids("missing business decision ids", tuple(decision.id for decision in decisions))
    for decision in decisions:
        _require_text("missing_business_decision.id", decision.id)
        _require_text("missing_business_decision.title", decision.title)
        _require_text("missing_business_decision.question", decision.question)
        _require_text("missing_business_decision.business_impact", decision.business_impact)
        _require_text("missing_business_decision.recommendation", decision.recommendation)
        _require_items("missing_business_decision.affected_story_ids", decision.affected_story_ids)


def _validate_backlog_draft(draft: BacklogDraft) -> None:
    _require_text("key", draft.key)
    _require_text("title", draft.title)
    _require_text("overview", draft.overview)
    _require_text("created_at", draft.created_at)
    if not draft.epics:
        raise BacklogDraftError("at least one epic is required")
    _require_unique_ids("epic ids", tuple(epic.id for epic in draft.epics))
    story_ids = tuple(story.id for epic in draft.epics for story in epic.stories)
    _require_unique_ids("story ids", story_ids)
    for epic in draft.epics:
        _require_text("epic.id", epic.id)
        _require_text("epic.title", epic.title)
        _require_text("epic.description", epic.description)
        if not epic.stories:
            raise BacklogDraftError(f"epic {epic.id} requires at least one story")
        for story in epic.stories:
            _require_text("story.id", story.id)
            _require_text("story.title", story.title)
            _require_text("story.description", story.description)
            if not story.acceptance_criteria:
                raise BacklogDraftError("story.acceptance_criteria is required")
            for criterion in story.acceptance_criteria:
                _require_text("acceptance_criterion.id", criterion.id)
                _require_text("acceptance_criterion.description", criterion.description)
            for dependency in story.dependencies:
                _require_text("dependency.prerequisite_story_id", dependency.prerequisite_story_id)
                _require_text("dependency.dependent_story_id", dependency.dependent_story_id)
                _require_text("dependency.link_type", dependency.link_type)
    _require_unique_ids("sprint ring ids", tuple(sprint.id for sprint in draft.sprint_rings))
    for sprint in draft.sprint_rings:
        _require_text("sprint.id", sprint.id)
        _require_text("sprint.name", sprint.name)
        _require_text("sprint.goal", sprint.goal)
        _require_items("sprint.story_ids", sprint.story_ids)
        for story_id in sprint.story_ids:
            if story_id not in story_ids:
                raise BacklogDraftError(f"sprint {sprint.id} references unknown story id {story_id}")
    _validate_missing_business_decisions(draft.missing_business_decisions)


def _epic_draft_from_dict(data: dict[str, Any]) -> BacklogEpicDraft:
    return BacklogEpicDraft(
        id=_optional_text(data.get("id")),
        title=_optional_text(data.get("title")),
        description=_optional_text(data.get("description")),
        stories=tuple(_story_draft_from_dict(story) for story in data.get("stories", ())),
    )


def _story_draft_from_dict(data: dict[str, Any]) -> BacklogStoryDraft:
    return BacklogStoryDraft(
        id=_optional_text(data.get("id")),
        title=_optional_text(data.get("title")),
        description=_optional_text(data.get("description")),
        acceptance_criteria=tuple(
            AcceptanceCriterionDraft(
                id=_optional_text(criterion.get("id")),
                description=_optional_text(criterion.get("description")),
            )
            for criterion in data.get("acceptance_criteria", ())
        ),
        dependencies=tuple(
            BacklogDependencyDraft(
                prerequisite_story_id=_optional_text(dependency.get("prerequisite_story_id")),
                dependent_story_id=_optional_text(dependency.get("dependent_story_id")),
                link_type=_optional_text(dependency.get("link_type")) or "blocks",
            )
            for dependency in data.get("dependencies", ())
        ),
        complexity=_complexity_from_dict(data.get("complexity", {})),
    )


def _sprint_draft_from_dict(data: dict[str, Any]) -> BacklogSprintDraft:
    return BacklogSprintDraft(
        id=_optional_text(data.get("id")),
        name=_optional_text(data.get("name")),
        goal=_optional_text(data.get("goal")),
        story_ids=tuple(_optional_text(item) for item in data.get("story_ids", ())),
        capacity_note=_optional_text(data.get("capacity_note")),
    )


def _missing_business_decision_from_dict(data: dict[str, Any]) -> MissingBusinessDecision:
    return MissingBusinessDecision(
        id=_optional_text(data.get("id")),
        title=_optional_text(data.get("title")),
        question=_optional_text(data.get("question")),
        business_impact=_optional_text(data.get("business_impact")),
        recommendation=_optional_text(data.get("recommendation")),
        affected_story_ids=tuple(_optional_text(item) for item in data.get("affected_story_ids", ())),
    )


def _requirement_epic_from_dict(data: dict[str, Any]) -> RequirementEpicInput:
    return RequirementEpicInput(
        id=_optional_text(data.get("id")),
        title=_optional_text(data.get("title")),
        description=_optional_text(data.get("description")),
        stories=tuple(_requirement_story_from_dict(story) for story in data.get("stories", ())),
    )


def _requirement_story_from_dict(data: dict[str, Any]) -> RequirementStoryInput:
    return RequirementStoryInput(
        id=_optional_text(data.get("id")),
        title=_optional_text(data.get("title")),
        description=_optional_text(data.get("description")),
        acceptance_criteria=tuple(_optional_text(item) for item in data.get("acceptance_criteria", ())),
        prerequisite_story_ids=tuple(_optional_text(item) for item in data.get("prerequisite_story_ids", ())),
        complexity=ComplexityLevel(_optional_text(data.get("complexity"))),
        complexity_rationale=_optional_text(data.get("complexity_rationale")),
        role=_agent_role_or_none(data.get("role")),
    )


def _requirement_sprint_from_dict(data: dict[str, Any]) -> RequirementSprintInput:
    return RequirementSprintInput(
        id=_optional_text(data.get("id")),
        name=_optional_text(data.get("name")),
        goal=_optional_text(data.get("goal")),
        story_ids=tuple(_optional_text(item) for item in data.get("story_ids", ())),
        capacity_note=_optional_text(data.get("capacity_note")),
    )


def _complexity_to_dict(metadata: StoryRoutingMetadata) -> dict[str, Any]:
    return {
        "complexity": metadata.complexity.value,
        "complexity_name": metadata.complexity_name,
        "complexity_points": metadata.complexity_points,
        "model": metadata.model,
        "reasoning": metadata.reasoning.value,
        "speed": metadata.speed,
        "rationale": metadata.rationale,
        "routing_source": metadata.routing_source.value,
        "role": metadata.role,
        "c4_justification": metadata.c4_justification,
    }


def _complexity_from_dict(data: dict[str, Any]) -> StoryRoutingMetadata:
    return StoryRoutingMetadata(
        complexity=ComplexityLevel(_optional_text(data.get("complexity"))),
        complexity_name=_optional_text(data.get("complexity_name")),
        complexity_points=int(data.get("complexity_points", 0)),
        model=_optional_text(data.get("model")),
        reasoning=ReasoningLevel(_optional_text(data.get("reasoning"))),
        speed=_optional_text(data.get("speed")),
        rationale=_optional_text(data.get("rationale")),
        routing_source=RoutingSource(_optional_text(data.get("routing_source")) or RoutingSource.COMPLEXITY_FALLBACK.value),
        role=_optional_text(data.get("role")),
        c4_justification=data.get("c4_justification"),
    )


def _optional_text(value: Any) -> str:
    return "" if value is None else str(value)


def _agent_role_or_none(value: Any) -> AgentRole | None:
    text = _optional_text(value)
    return AgentRole(text) if text else None


def _require_text(field_name: str, value: str) -> None:
    if not value.strip():
        raise BacklogDraftError(f"{field_name} is required")


def _require_items(field_name: str, value: tuple[str, ...]) -> None:
    if not value:
        raise BacklogDraftError(f"{field_name} is required")
    for index, item in enumerate(value):
        if not item.strip():
            raise BacklogDraftError(f"{field_name}[{index}] is required")


def _require_unique_ids(field_name: str, values: tuple[str, ...]) -> None:
    if len(set(values)) != len(values):
        raise BacklogDraftError(f"{field_name} must be unique")
