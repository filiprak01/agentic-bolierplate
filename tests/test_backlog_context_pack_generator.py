from agentic_boilerplate import domain
from agentic_boilerplate.domain import (
    AgentRole,
    BacklogContextPackGenerationConfig,
    ContextPackDocumentationReference,
    RequirementEpicInput,
    RequirementInput,
    RequirementSprintInput,
    RequirementStoryInput,
    generate_context_packs_from_backlog_draft,
    backlog_context_pack_generation_result_to_dict,
    create_backlog_draft,
    require_valid_context_pack,
)
from agentic_boilerplate.domain.story_complexity import ComplexityLevel


def test_generate_context_packs_from_backlog_draft_separates_shared_and_role_context() -> None:
    draft = create_backlog_draft(_requirement(), created_at="2026-08-10T12:00:00Z")

    result = generate_context_packs_from_backlog_draft(
        draft,
        BacklogContextPackGenerationConfig(
            created_at="2026-08-10T12:05:00Z",
            target_repo_path="/workspace/airline",
            context_pack_root="data/context-packs",
            documentation_references=(
                ContextPackDocumentationReference(
                    path="docs/product/scope.md",
                    description="Approved PO scope.",
                ),
            ),
            shared_context=("Release 1.2 source docs are approved.",),
        ),
    )

    payload = backlog_context_pack_generation_result_to_dict(result)
    first_pack = result.items[0].context_pack
    second_pack = result.items[1].context_pack

    assert payload["context_pack_count"] == 2
    assert first_pack.issue_key == "STORY-1"
    assert first_pack.dependencies == ()
    assert "Draft prerequisites: none" in first_pack.shared_context
    assert first_pack.role == AgentRole.DEVELOPER
    assert first_pack.role_specific_context[0].role == AgentRole.DEVELOPER
    assert second_pack.role == AgentRole.FRONTEND
    assert "Draft prerequisites: STORY-1" in second_pack.shared_context
    assert second_pack.routing.role_instruction_path == "ai_agents/roles/frontend.md"
    require_valid_context_pack(first_pack)
    require_valid_context_pack(second_pack)


def test_backlog_context_pack_public_api_exports_are_available() -> None:
    assert domain.BacklogContextPackGenerationConfig is BacklogContextPackGenerationConfig
    assert domain.generate_context_packs_from_backlog_draft is generate_context_packs_from_backlog_draft
    assert domain.backlog_context_pack_generation_result_to_dict is backlog_context_pack_generation_result_to_dict


def _requirement() -> RequirementInput:
    return RequirementInput(
        key="REQ-R1",
        title="Release 1 draft",
        overview="Create the initial release backlog from approved docs.",
        epics=(
            RequirementEpicInput(
                id="EPIC-PLANNING",
                title="Planning",
                description="Planning workflow.",
                stories=(
                    RequirementStoryInput(
                        id="STORY-1",
                        title="Generate draft",
                        description="Generate a local draft.",
                        acceptance_criteria=("Draft exists.",),
                        prerequisite_story_ids=(),
                        complexity=ComplexityLevel.C2,
                        complexity_rationale="Structured transformation.",
                    ),
                    RequirementStoryInput(
                        id="STORY-2",
                        title="Build inbox UI",
                        description="Implement accepted inbox UI.",
                        acceptance_criteria=("UI uses accepted design.",),
                        prerequisite_story_ids=("STORY-1",),
                        complexity=ComplexityLevel.C3,
                        complexity_rationale="Frontend work with project state.",
                        role=AgentRole.FRONTEND,
                    ),
                ),
            ),
        ),
        sprint_rings=(
            RequirementSprintInput(
                id="SPRINT-1",
                name="Planning setup",
                goal="Prepare planning and UI slices.",
                story_ids=("STORY-1", "STORY-2"),
            ),
        ),
    )
