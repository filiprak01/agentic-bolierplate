import pytest

from agentic_boilerplate import domain, storage
from agentic_boilerplate.domain.backlog_draft import (
    BacklogDraftError,
    MissingBusinessDecision,
    RequirementEpicInput,
    RequirementInput,
    RequirementSprintInput,
    RequirementStoryInput,
    backlog_draft_from_dict,
    backlog_draft_to_dict,
    build_missing_business_decision_questions,
    create_backlog_draft,
    requirement_input_from_dict,
)
from agentic_boilerplate.domain.po_inbox import AgentRole, InboxMessageType, InboxStatus
from agentic_boilerplate.domain.story_complexity import ComplexityLevel, ReasoningLevel
from agentic_boilerplate.storage.backlog_draft import FileBacklogDraftStore


def sample_requirement() -> RequirementInput:
    return RequirementInput(
        key="REQ-AGENT-35",
        title="Product Planning Draft Workflow",
        overview="Create local backlog drafts before Jira story creation.",
        epics=(
            RequirementEpicInput(
                id="EPIC-DRAFTS",
                title="Backlog Drafting",
                description="Draft backlog items locally for PO review.",
                stories=(
                    RequirementStoryInput(
                        id="STORY-DRAFT-1",
                        title="Create local draft",
                        description="Generate a draft story from structured requirements.",
                        acceptance_criteria=(
                            "Draft includes acceptance criteria.",
                            "Draft includes complexity metadata.",
                        ),
                        prerequisite_story_ids=(),
                        complexity=ComplexityLevel.C2,
                        complexity_rationale="Structured transformation with local persistence.",
                    ),
                    RequirementStoryInput(
                        id="STORY-DRAFT-2",
                        title="Create Jira story after approval",
                        description="Prepare approved draft for later Jira creation.",
                        acceptance_criteria=("Draft keeps dependency links.",),
                        prerequisite_story_ids=("STORY-DRAFT-1",),
                        complexity=ComplexityLevel.C3,
                        complexity_rationale="Jira creation depends on PO-approved draft content.",
                    ),
                ),
            ),
        ),
        sprint_rings=(
            RequirementSprintInput(
                id="SPRINT-1",
                name="Planning Drafts",
                goal="Deliver local backlog draft creation before Jira promotion.",
                story_ids=("STORY-DRAFT-1", "STORY-DRAFT-2"),
                capacity_note="Scope-first slice for one Codex session.",
            ),
        ),
        missing_business_decisions=(
            MissingBusinessDecision(
                id="DECISION-SCOPE",
                title="Sprint slicing rule",
                question="Should this release slice by workflow or by integration boundary?",
                business_impact="Sprint slicing changes story dependencies and Product Owner review order.",
                recommendation="Use workflow slicing unless the PO requests integration-first delivery.",
                affected_story_ids=("STORY-DRAFT-1", "STORY-DRAFT-2"),
            ),
        ),
    )


def test_create_backlog_draft_from_requirement_input() -> None:
    draft = create_backlog_draft(sample_requirement(), created_at="2026-06-21T08:30:00Z")

    assert draft.key == "REQ-AGENT-35"
    assert draft.created_at == "2026-06-21T08:30:00Z"
    assert draft.epics[0].id == "EPIC-DRAFTS"
    assert draft.epics[0].stories[0].acceptance_criteria[0].id == "STORY-DRAFT-1-AC1"
    assert draft.epics[0].stories[0].complexity.complexity == ComplexityLevel.C2
    assert draft.epics[0].stories[0].complexity.reasoning == ReasoningLevel.MEDIUM
    assert draft.epics[0].stories[1].dependencies[0].prerequisite_story_id == "STORY-DRAFT-1"
    assert draft.epics[0].stories[1].dependencies[0].dependent_story_id == "STORY-DRAFT-2"
    assert draft.epics[0].stories[1].complexity.complexity == ComplexityLevel.C3
    assert draft.sprint_rings[0].id == "SPRINT-1"
    assert draft.sprint_rings[0].story_ids == ("STORY-DRAFT-1", "STORY-DRAFT-2")
    assert draft.missing_business_decisions[0].affected_story_ids == ("STORY-DRAFT-1", "STORY-DRAFT-2")


def test_backlog_draft_rejects_missing_acceptance_criteria() -> None:
    requirement = RequirementInput(
        key="REQ-INVALID",
        title="Invalid draft",
        overview="Missing acceptance criteria.",
        epics=(
            RequirementEpicInput(
                id="EPIC-INVALID",
                title="Invalid epic",
                description="Invalid epic description.",
                stories=(
                    RequirementStoryInput(
                        id="STORY-INVALID",
                        title="Invalid story",
                        description="Invalid story description.",
                        acceptance_criteria=(),
                        prerequisite_story_ids=(),
                        complexity=ComplexityLevel.C1,
                        complexity_rationale="Simple invalid story.",
                    ),
                ),
            ),
        ),
    )

    with pytest.raises(BacklogDraftError, match="story.acceptance_criteria is required"):
        create_backlog_draft(requirement, created_at="2026-06-21T08:30:00Z")


def test_backlog_draft_rejects_duplicate_story_ids() -> None:
    story = RequirementStoryInput(
        id="STORY-DUPLICATE",
        title="Duplicate story",
        description="Duplicate story description.",
        acceptance_criteria=("Criterion exists.",),
        prerequisite_story_ids=(),
        complexity=ComplexityLevel.C1,
        complexity_rationale="Simple duplicate test.",
    )
    requirement = RequirementInput(
        key="REQ-DUPLICATE",
        title="Duplicate draft",
        overview="Duplicate story ids should fail.",
        epics=(
            RequirementEpicInput(
                id="EPIC-DUPLICATE",
                title="Duplicate epic",
                description="Duplicate epic description.",
                stories=(story, story),
            ),
        ),
    )

    with pytest.raises(BacklogDraftError, match="story ids must be unique"):
        create_backlog_draft(requirement, created_at="2026-06-21T08:30:00Z")


def test_backlog_draft_rejects_blank_dependency_ids() -> None:
    requirement = RequirementInput(
        key="REQ-BLANK-DEPENDENCY",
        title="Blank dependency draft",
        overview="Blank dependency ids should fail.",
        epics=(
            RequirementEpicInput(
                id="EPIC-BLANK-DEPENDENCY",
                title="Blank dependency epic",
                description="Blank dependency epic description.",
                stories=(
                    RequirementStoryInput(
                        id="STORY-BLANK-DEPENDENCY",
                        title="Blank dependency story",
                        description="Blank dependency story description.",
                        acceptance_criteria=("Criterion exists.",),
                        prerequisite_story_ids=(" ",),
                        complexity=ComplexityLevel.C1,
                        complexity_rationale="Simple dependency validation.",
                    ),
                ),
            ),
        ),
    )

    with pytest.raises(BacklogDraftError, match=r"story.prerequisite_story_ids\[0\] is required"):
        create_backlog_draft(requirement, created_at="2026-06-21T08:30:00Z")


def test_backlog_draft_rejects_sprint_ring_with_unknown_story_id() -> None:
    requirement = RequirementInput(
        key="REQ-SPRINT-MISSING",
        title="Invalid sprint draft",
        overview="Sprint references an unknown story.",
        epics=(
            RequirementEpicInput(
                id="EPIC-SPRINT-MISSING",
                title="Invalid sprint epic",
                description="Invalid sprint epic description.",
                stories=(
                    RequirementStoryInput(
                        id="STORY-SPRINT-MISSING",
                        title="Valid story",
                        description="Valid story description.",
                        acceptance_criteria=("Criterion exists.",),
                        prerequisite_story_ids=(),
                        complexity=ComplexityLevel.C1,
                        complexity_rationale="Simple validation.",
                    ),
                ),
            ),
        ),
        sprint_rings=(
            RequirementSprintInput(
                id="SPRINT-INVALID",
                name="Invalid",
                goal="Should fail.",
                story_ids=("STORY-UNKNOWN",),
            ),
        ),
    )

    with pytest.raises(BacklogDraftError, match="unknown story ids"):
        create_backlog_draft(requirement, created_at="2026-06-21T08:30:00Z")


def test_requirement_input_from_dict_includes_sprint_rings_and_decisions() -> None:
    source = {
        "key": "REQ-AGENT-35",
        "title": "Product Planning Draft Workflow",
        "overview": "Create local backlog drafts before Jira story creation.",
        "epics": [
            {
                "id": "EPIC-DRAFTS",
                "title": "Backlog Drafting",
                "description": "Draft backlog items locally for PO review.",
                "stories": [
                    {
                        "id": "STORY-DRAFT-1",
                        "title": "Create local draft",
                        "description": "Generate a draft story from structured requirements.",
                        "acceptance_criteria": ["Draft includes acceptance criteria."],
                        "prerequisite_story_ids": [],
                        "complexity": "C2",
                        "complexity_rationale": "Parsed from approved source docs.",
                    },
                    {
                        "id": "STORY-DRAFT-2",
                        "title": "Create Jira story after approval",
                        "description": "Prepare approved draft for later Jira creation.",
                        "acceptance_criteria": ["Draft keeps dependency links."],
                        "prerequisite_story_ids": ["STORY-DRAFT-1"],
                        "complexity": "C3",
                        "complexity_rationale": "Parsed from approved source docs.",
                    },
                ],
            }
        ],
        "sprint_rings": [
            {
                "id": "SPRINT-1",
                "name": "Planning Drafts",
                "goal": "Deliver local backlog draft creation before Jira promotion.",
                "story_ids": ["STORY-DRAFT-1", "STORY-DRAFT-2"],
                "capacity_note": "Scope-first slice for one Codex session.",
            }
        ],
        "missing_business_decisions": [
            {
                "id": "DECISION-SCOPE",
                "title": "Sprint slicing rule",
                "question": "Should this release slice by workflow or by integration boundary?",
                "business_impact": "Sprint slicing changes story dependencies and PO review order.",
                "recommendation": "Use workflow slicing unless the PO requests integration-first delivery.",
                "affected_story_ids": ["STORY-DRAFT-1", "STORY-DRAFT-2"],
            }
        ],
    }

    requirement = requirement_input_from_dict(source)
    draft = create_backlog_draft(requirement, created_at="2026-06-21T08:40:00Z")

    assert draft.sprint_rings[0].name == "Planning Drafts"
    assert draft.missing_business_decisions[0].id == "DECISION-SCOPE"
    assert draft.epics[0].stories[1].dependencies[0].prerequisite_story_id == "STORY-DRAFT-1"


def test_missing_business_decisions_create_po_inbox_questions() -> None:
    draft = create_backlog_draft(sample_requirement(), created_at="2026-06-21T08:30:00Z")

    questions = build_missing_business_decision_questions(
        draft,
        created_at="2026-06-21T08:35:00Z",
        jira_issue_key="AGENT-35",
        context_pack_path="data/context/AGENT-35.json",
    )

    assert len(questions) == 1
    assert questions[0].id == "REQ-AGENT-35-decision-DECISION-SCOPE"
    assert questions[0].message_type == InboxMessageType.BLOCKING_QUESTION
    assert questions[0].status == InboxStatus.OPEN
    assert questions[0].agent_role == AgentRole.PRODUCT_PLANNING
    assert questions[0].jira_issue_key == "AGENT-35"
    assert questions[0].context_pack_path == "data/context/AGENT-35.json"
    assert "STORY-DRAFT-1" in questions[0].message
    assert questions[0].business_impact
    assert questions[0].recommendation


def test_backlog_draft_serializes_for_resume() -> None:
    draft = create_backlog_draft(sample_requirement(), created_at="2026-06-21T08:30:00Z")

    restored = backlog_draft_from_dict(backlog_draft_to_dict(draft))

    assert restored == draft


def test_file_backlog_draft_store_roundtrip(tmp_path) -> None:
    draft = create_backlog_draft(sample_requirement(), created_at="2026-06-21T08:30:00Z")
    store = FileBacklogDraftStore(tmp_path / "backlog-drafts")

    location = store.create(draft)
    restored = store.read(draft.key)

    assert location.path.name == "REQ-AGENT-35.json"
    assert restored == draft
    assert store.list_drafts() == (draft,)


def test_backlog_draft_public_api_exports_are_available() -> None:
    assert domain.RequirementInput is RequirementInput
    assert domain.RequirementSprintInput is RequirementSprintInput
    assert domain.create_backlog_draft is create_backlog_draft
    assert domain.requirement_input_from_dict is requirement_input_from_dict
    assert domain.build_missing_business_decision_questions is build_missing_business_decision_questions
    assert domain.backlog_draft_to_dict is backlog_draft_to_dict
    assert storage.FileBacklogDraftStore is FileBacklogDraftStore
