"""Generate draft context packs from local backlog drafts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agentic_boilerplate.domain.backlog_draft import BacklogDraft, BacklogEpicDraft, BacklogStoryDraft
from agentic_boilerplate.domain.context_pack import (
    ContextPack,
    ContextPackBuildInput,
    ContextPackDocumentationReference,
    ContextPackRouting,
    RoleSpecificContext,
    build_context_pack,
    context_pack_to_dict,
)
from agentic_boilerplate.domain.po_inbox import AgentRole
from agentic_boilerplate.domain.story_complexity import RoutingSource


@dataclass(frozen=True)
class BacklogContextPackGenerationConfig:
    """Config used to generate context packs for every story in a draft."""

    created_at: str
    target_repo_path: str
    context_pack_root: str = "data/context-packs"
    codex_jobs_root: str = "data/codex-jobs"
    codex_results_root: str = "data/codex-results"
    default_role: AgentRole = AgentRole.DEVELOPER
    default_sprint: str = "Draft backlog"
    role_instruction_version: str = "release-1.2"
    documentation_references: tuple[ContextPackDocumentationReference, ...] = (
        ContextPackDocumentationReference(
            path="docs/backlog-draft-workflow.md",
            description="Local draft generation workflow.",
        ),
        ContextPackDocumentationReference(
            path="docs/context-pack-generator.md",
            description="Worker context pack schema and validation rules.",
        ),
    )
    shared_context: tuple[str, ...] = ()
    test_expectations: tuple[str, ...] = (
        "Run focused validation for the changed workflow.",
        "Update durable evidence for every acceptance criterion.",
    )


@dataclass(frozen=True)
class BacklogContextPackGenerationItem:
    """One generated context pack and its draft lineage."""

    story_id: str
    epic_id: str
    sprint_id: str
    context_pack: ContextPack


@dataclass(frozen=True)
class BacklogContextPackGenerationResult:
    """Batch context pack generation output."""

    draft_key: str
    items: tuple[BacklogContextPackGenerationItem, ...]


def generate_context_packs_from_backlog_draft(
    draft: BacklogDraft,
    config: BacklogContextPackGenerationConfig,
) -> BacklogContextPackGenerationResult:
    """Generate one context pack for every draft story."""

    items: list[BacklogContextPackGenerationItem] = []
    sprint_by_story = _sprint_by_story_id(draft)
    for epic in draft.epics:
        for story in epic.stories:
            sprint_id, sprint_name = sprint_by_story.get(story.id, ("", config.default_sprint))
            context_pack = build_context_pack(
                _context_pack_input_for_story(
                    draft,
                    epic,
                    story,
                    sprint_name=sprint_name,
                    config=config,
                ),
                context_pack_root=config.context_pack_root,
                codex_jobs_root=config.codex_jobs_root,
                codex_results_root=config.codex_results_root,
            )
            items.append(
                BacklogContextPackGenerationItem(
                    story_id=story.id,
                    epic_id=epic.id,
                    sprint_id=sprint_id,
                    context_pack=context_pack,
                )
            )
    return BacklogContextPackGenerationResult(draft_key=draft.key, items=tuple(items))


def backlog_context_pack_generation_result_to_dict(
    result: BacklogContextPackGenerationResult,
) -> dict[str, Any]:
    """Convert generation output into JSON-compatible data."""

    return {
        "draft_key": result.draft_key,
        "context_pack_count": len(result.items),
        "items": [
            {
                "story_id": item.story_id,
                "epic_id": item.epic_id,
                "sprint_id": item.sprint_id,
                "context_pack": context_pack_to_dict(item.context_pack),
            }
            for item in result.items
        ],
    }


def _context_pack_input_for_story(
    draft: BacklogDraft,
    epic: BacklogEpicDraft,
    story: BacklogStoryDraft,
    *,
    sprint_name: str,
    config: BacklogContextPackGenerationConfig,
) -> ContextPackBuildInput:
    role = _role_for_story(story, config.default_role)
    routing = story.complexity
    return ContextPackBuildInput(
        issue_key=story.id,
        summary=story.title,
        issue_type="Story",
        status="DRAFT",
        sprint=sprint_name,
        role=role,
        branch_name=f"feature/{story.id}-{_slug(story.title)}",
        target_repo_path=config.target_repo_path,
        created_at=config.created_at,
        routing=ContextPackRouting(
            model=routing.model,
            reasoning=routing.reasoning,
            speed=routing.speed,
            complexity=routing.complexity.value,
            effort_mode=routing.complexity_name,
            rationale=routing.rationale,
            routing_source=routing.routing_source,
            role_instruction_path=_role_instruction_path(role),
            role_instruction_version=config.role_instruction_version,
            role_routing_override_reason="" if routing.routing_source is RoutingSource.ROLE else "Complexity fallback route.",
            manual_switch_required=True,
            manual_switch_prompt=(
                f"Before starting {story.id}, switch Codex to {routing.model} "
                f"with {routing.reasoning.value} reasoning and {routing.speed} speed for {role.value}."
            ),
        ),
        labels=(
            "draft-context-pack",
            f"draft-{draft.key}",
            f"epic-{epic.id}",
        ),
        acceptance_criteria=tuple(criterion.description for criterion in story.acceptance_criteria),
        documentation_references=config.documentation_references,
        shared_context=(
            f"Backlog draft: {draft.key} - {draft.title}",
            f"Draft overview: {draft.overview}",
            f"Epic: {epic.id} - {epic.title}",
            f"Draft prerequisites: {_dependency_summary(story)}",
            *config.shared_context,
        ),
        role_specific_context=(
            RoleSpecificContext(
                role=role,
                instructions=(
                    f"Load `{_role_instruction_path(role)}` before executing this draft story.",
                    "Use shared context only for release-wide facts; keep role-specific assumptions in this section.",
                ),
            ),
        ),
        test_expectations=config.test_expectations,
    )


def _sprint_by_story_id(draft: BacklogDraft) -> dict[str, tuple[str, str]]:
    mapping: dict[str, tuple[str, str]] = {}
    for sprint in draft.sprint_rings:
        for story_id in sprint.story_ids:
            mapping[story_id] = (sprint.id, sprint.name)
    return mapping


def _role_for_story(story: BacklogStoryDraft, default_role: AgentRole) -> AgentRole:
    return AgentRole(story.complexity.role) if story.complexity.role else default_role


def _role_instruction_path(role: AgentRole) -> str:
    return f"ai_agents/roles/{role.value}.md"


def _dependency_summary(story: BacklogStoryDraft) -> str:
    if not story.dependencies:
        return "none"
    return ", ".join(dependency.prerequisite_story_id for dependency in story.dependencies)


def _slug(value: str) -> str:
    slug = "".join(character.lower() if character.isalnum() else "-" for character in value)
    return "-".join(part for part in slug.split("-") if part)[:48] or "story"
