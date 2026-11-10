"""Product Planning workflow for creating Jira issues from approved drafts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agentic_boilerplate.domain.backlog_draft import BacklogDraft, BacklogStoryDraft
from agentic_boilerplate.integrations.jira import JiraAdapterConfig, JiraIssueFields, JiraProjectIssueAdapter


class JiraCreationWorkflowError(ValueError):
    """Raised when Jira creation workflow input is incomplete."""


@dataclass(frozen=True)
class ApprovedBacklogDraft:
    """Backlog draft approved by the Product Owner for Jira creation."""

    draft: BacklogDraft
    approved_by: str
    approved_at: str


@dataclass(frozen=True)
class JiraDraftIssuePlan:
    """One Jira issue create operation planned from a local draft item."""

    draft_id: str
    issue_type: str
    fields: JiraIssueFields
    expected_initial_status: str
    parent_draft_id: str = ""


@dataclass(frozen=True)
class JiraDraftDependencyLinkPlan:
    """One Jira Blocks link planned from draft story dependencies."""

    prerequisite_draft_story_id: str
    dependent_draft_story_id: str
    link_type: str = "Blocks"


@dataclass(frozen=True)
class JiraBacklogCreationPlan:
    """Jira issue and link creation plan for an approved backlog draft."""

    draft_key: str
    project_key: str
    approved_by: str
    approved_at: str
    expected_initial_status: str
    issues: tuple[JiraDraftIssuePlan, ...]
    dependency_links: tuple[JiraDraftDependencyLinkPlan, ...]


@dataclass(frozen=True)
class JiraCreatedIssueMapping:
    """Mapping between a local draft item and a created Jira issue."""

    draft_id: str
    jira_key: str
    issue_type: str
    expected_initial_status: str
    actual_status: str
    parent_draft_id: str = ""
    parent_jira_key: str = ""


@dataclass(frozen=True)
class JiraCreatedDependencyLink:
    """Audit record for one created Jira dependency link."""

    prerequisite_draft_story_id: str
    dependent_draft_story_id: str
    blocker_jira_key: str
    blocked_jira_key: str
    link_type: str


@dataclass(frozen=True)
class JiraBacklogCreationResult:
    """Result of executing a Jira backlog creation plan."""

    draft_key: str
    project_key: str
    created_at: str
    issue_mappings: tuple[JiraCreatedIssueMapping, ...]
    dependency_links: tuple[JiraCreatedDependencyLink, ...]


def build_jira_backlog_creation_plan(
    approved_draft: ApprovedBacklogDraft,
    *,
    jira_config: JiraAdapterConfig,
    sprint_label: str,
    sprint_ring_label: str,
    release_label: str,
    context_pack_root: str = "data/context-packs",
) -> JiraBacklogCreationPlan:
    """Build Jira create and dependency-link operations from an approved draft."""

    _require_text("approved_by", approved_draft.approved_by)
    _require_text("approved_at", approved_draft.approved_at)
    _require_text("project_key", jira_config.project_key)
    _require_text("sprint_label", sprint_label)
    _require_text("sprint_ring_label", sprint_ring_label)
    _require_text("release_label", release_label)

    base_labels = (
        sprint_label,
        sprint_ring_label,
        release_label,
        "created-from-backlog-draft",
        f"draft-{approved_draft.draft.key.lower()}",
    )
    issues: list[JiraDraftIssuePlan] = []
    dependency_links: list[JiraDraftDependencyLinkPlan] = []
    sprint_by_story_id = _sprint_by_story_id(approved_draft.draft)
    for epic in approved_draft.draft.epics:
        issues.append(
            JiraDraftIssuePlan(
                draft_id=epic.id,
                issue_type="Epic",
                fields=JiraIssueFields(
                    summary=epic.title,
                    issue_type="Epic",
                    description=_epic_description(approved_draft.draft.key, epic.description),
                    labels=_dedupe_labels(base_labels + ("draft-epic",)),
                ),
                expected_initial_status=jira_config.default_issue_status,
            )
        )
        for story in epic.stories:
            issues.append(
                JiraDraftIssuePlan(
                    draft_id=story.id,
                    issue_type=jira_config.story_issue_type,
                    fields=JiraIssueFields(
                        summary=story.title,
                        issue_type=jira_config.story_issue_type,
                        description=_story_description(
                            approved_draft.draft.key,
                            story,
                            sprint_summary=sprint_by_story_id.get(story.id, "Unassigned draft sprint"),
                            context_pack_root=context_pack_root,
                        ),
                        labels=_dedupe_labels(base_labels + _complexity_labels(story)),
                        parent_key="",
                    ),
                    expected_initial_status=jira_config.default_issue_status,
                    parent_draft_id=epic.id,
                )
            )
            dependency_links.extend(
                JiraDraftDependencyLinkPlan(
                    prerequisite_draft_story_id=dependency.prerequisite_story_id,
                    dependent_draft_story_id=dependency.dependent_story_id,
                    link_type=jira_config.blocks_link_type,
                )
                for dependency in story.dependencies
            )
    if not issues:
        raise JiraCreationWorkflowError("at least one Jira issue is required")
    return JiraBacklogCreationPlan(
        draft_key=approved_draft.draft.key,
        project_key=jira_config.project_key,
        approved_by=approved_draft.approved_by,
        approved_at=approved_draft.approved_at,
        expected_initial_status=jira_config.default_issue_status,
        issues=tuple(issues),
        dependency_links=tuple(dependency_links),
    )


def execute_jira_backlog_creation_plan(
    plan: JiraBacklogCreationPlan,
    *,
    adapter: JiraProjectIssueAdapter,
    created_at: str,
) -> JiraBacklogCreationResult:
    """Create Jira issues and Blocks links from a creation plan."""

    _require_text("created_at", created_at)
    created_by_draft_id: dict[str, JiraCreatedIssueMapping] = {}
    mappings: list[JiraCreatedIssueMapping] = []
    for issue_plan in plan.issues:
        parent_mapping = created_by_draft_id.get(issue_plan.parent_draft_id) if issue_plan.parent_draft_id else None
        fields = jira_issue_fields_for_plan(
            issue_plan,
            created_parent_key=parent_mapping.jira_key if parent_mapping else "",
        )
        created = adapter.create_issue(fields)
        mapping = JiraCreatedIssueMapping(
            draft_id=issue_plan.draft_id,
            jira_key=created.key,
            issue_type=created.issue_type,
            expected_initial_status=issue_plan.expected_initial_status,
            actual_status=created.status or issue_plan.expected_initial_status,
            parent_draft_id=issue_plan.parent_draft_id,
            parent_jira_key=created.parent_key,
        )
        created_by_draft_id[issue_plan.draft_id] = mapping
        mappings.append(mapping)

    created_links: list[JiraCreatedDependencyLink] = []
    for link_plan in plan.dependency_links:
        blocker = _mapping_for(created_by_draft_id, link_plan.prerequisite_draft_story_id)
        blocked = _mapping_for(created_by_draft_id, link_plan.dependent_draft_story_id)
        adapter.create_blocks_link(blocker.jira_key, blocked.jira_key)
        created_links.append(
            JiraCreatedDependencyLink(
                prerequisite_draft_story_id=link_plan.prerequisite_draft_story_id,
                dependent_draft_story_id=link_plan.dependent_draft_story_id,
                blocker_jira_key=blocker.jira_key,
                blocked_jira_key=blocked.jira_key,
                link_type=link_plan.link_type,
            )
        )

    return JiraBacklogCreationResult(
        draft_key=plan.draft_key,
        project_key=plan.project_key,
        created_at=created_at,
        issue_mappings=tuple(mappings),
        dependency_links=tuple(created_links),
    )


def jira_creation_result_to_dict(result: JiraBacklogCreationResult) -> dict[str, Any]:
    """Convert a Jira creation result to JSON-compatible data."""

    _validate_creation_result(result)
    return {
        "draft_key": result.draft_key,
        "project_key": result.project_key,
        "created_at": result.created_at,
        "issue_mappings": [
            {
                "draft_id": mapping.draft_id,
                "jira_key": mapping.jira_key,
                "issue_type": mapping.issue_type,
                "expected_initial_status": mapping.expected_initial_status,
                "actual_status": mapping.actual_status,
                "parent_draft_id": mapping.parent_draft_id,
                "parent_jira_key": mapping.parent_jira_key,
            }
            for mapping in result.issue_mappings
        ],
        "dependency_links": [
            {
                "prerequisite_draft_story_id": link.prerequisite_draft_story_id,
                "dependent_draft_story_id": link.dependent_draft_story_id,
                "blocker_jira_key": link.blocker_jira_key,
                "blocked_jira_key": link.blocked_jira_key,
                "link_type": link.link_type,
            }
            for link in result.dependency_links
        ],
    }


def jira_creation_result_from_dict(data: dict[str, Any]) -> JiraBacklogCreationResult:
    """Build a Jira creation result from JSON-compatible data."""

    result = JiraBacklogCreationResult(
        draft_key=_optional_text(data.get("draft_key")),
        project_key=_optional_text(data.get("project_key")),
        created_at=_optional_text(data.get("created_at")),
        issue_mappings=tuple(_issue_mapping_from_dict(item) for item in data.get("issue_mappings", ())),
        dependency_links=tuple(_dependency_link_from_dict(item) for item in data.get("dependency_links", ())),
    )
    _validate_creation_result(result)
    return result


def jira_issue_fields_for_plan(plan: JiraDraftIssuePlan, *, created_parent_key: str = "") -> JiraIssueFields:
    """Return Jira create fields, resolving an optional parent issue key."""

    if plan.parent_draft_id and not created_parent_key:
        raise JiraCreationWorkflowError("created_parent_key is required for child draft issues")
    if not plan.parent_draft_id:
        return plan.fields
    return JiraIssueFields(
        summary=plan.fields.summary,
        issue_type=plan.fields.issue_type,
        description=plan.fields.description,
        labels=plan.fields.labels,
        parent_key=created_parent_key,
    )


def _mapping_for(
    mappings: dict[str, JiraCreatedIssueMapping],
    draft_id: str,
) -> JiraCreatedIssueMapping:
    try:
        return mappings[draft_id]
    except KeyError as exc:
        raise JiraCreationWorkflowError(f"Missing created Jira issue for draft id: {draft_id}") from exc


def _validate_creation_result(result: JiraBacklogCreationResult) -> None:
    _require_text("draft_key", result.draft_key)
    _require_text("project_key", result.project_key)
    _require_text("created_at", result.created_at)
    if not result.issue_mappings:
        raise JiraCreationWorkflowError("at least one created issue mapping is required")
    for mapping in result.issue_mappings:
        _require_text("issue_mapping.draft_id", mapping.draft_id)
        _require_text("issue_mapping.jira_key", mapping.jira_key)
        _require_text("issue_mapping.issue_type", mapping.issue_type)
        _require_text("issue_mapping.expected_initial_status", mapping.expected_initial_status)
        _require_text("issue_mapping.actual_status", mapping.actual_status)
    for link in result.dependency_links:
        _require_text("dependency_link.prerequisite_draft_story_id", link.prerequisite_draft_story_id)
        _require_text("dependency_link.dependent_draft_story_id", link.dependent_draft_story_id)
        _require_text("dependency_link.blocker_jira_key", link.blocker_jira_key)
        _require_text("dependency_link.blocked_jira_key", link.blocked_jira_key)
        _require_text("dependency_link.link_type", link.link_type)


def _issue_mapping_from_dict(data: dict[str, Any]) -> JiraCreatedIssueMapping:
    return JiraCreatedIssueMapping(
        draft_id=_optional_text(data.get("draft_id")),
        jira_key=_optional_text(data.get("jira_key")),
        issue_type=_optional_text(data.get("issue_type")),
        expected_initial_status=_optional_text(data.get("expected_initial_status")),
        actual_status=_optional_text(data.get("actual_status")),
        parent_draft_id=_optional_text(data.get("parent_draft_id")),
        parent_jira_key=_optional_text(data.get("parent_jira_key")),
    )


def _dependency_link_from_dict(data: dict[str, Any]) -> JiraCreatedDependencyLink:
    return JiraCreatedDependencyLink(
        prerequisite_draft_story_id=_optional_text(data.get("prerequisite_draft_story_id")),
        dependent_draft_story_id=_optional_text(data.get("dependent_draft_story_id")),
        blocker_jira_key=_optional_text(data.get("blocker_jira_key")),
        blocked_jira_key=_optional_text(data.get("blocked_jira_key")),
        link_type=_optional_text(data.get("link_type")),
    )


def _optional_text(value: Any) -> str:
    return "" if value is None else str(value)


def _epic_description(draft_key: str, description: str) -> str:
    return f"Backlog draft: {draft_key}\n\n{description}"


def _story_description(
    draft_key: str,
    story: BacklogStoryDraft,
    *,
    sprint_summary: str,
    context_pack_root: str,
) -> str:
    criteria = "\n".join(
        f"{criterion.id}. {criterion.description}"
        for criterion in story.acceptance_criteria
    )
    dependencies = "\n".join(
        f"- {dependency.prerequisite_story_id} {dependency.link_type} {dependency.dependent_story_id}"
        for dependency in story.dependencies
    ) or "None"
    return (
        f"Backlog draft: {draft_key}\n\n"
        f"{story.description}\n\n"
        "Acceptance criteria:\n"
        f"{criteria}\n\n"
        "Dependencies:\n"
        f"{dependencies}\n\n"
        "Sprint proposal:\n"
        f"{sprint_summary}\n\n"
        "Context references:\n"
        f"- Markdown: {context_pack_root.rstrip('/')}/{story.id}/context-pack.md\n"
        f"- JSON: {context_pack_root.rstrip('/')}/{story.id}/context-pack.json\n\n"
        "Complexity metadata:\n"
        f"- Level: {story.complexity.complexity.value}\n"
        f"- Points: {story.complexity.complexity_points}\n"
        f"- Model: {story.complexity.model}\n"
        f"- Reasoning: {story.complexity.reasoning.value}\n"
        f"- Speed: {story.complexity.speed}\n"
        f"- Rationale: {story.complexity.rationale}"
    )


def _sprint_by_story_id(draft: BacklogDraft) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for sprint in draft.sprint_rings:
        for story_id in sprint.story_ids:
            mapping[story_id] = f"{sprint.id} - {sprint.name}: {sprint.goal}"
    return mapping


def _complexity_labels(story: BacklogStoryDraft) -> tuple[str, ...]:
    return (
        f"complexity-{story.complexity.complexity.value.lower()}",
        f"reasoning-{story.complexity.reasoning.value}",
        f"model-{story.complexity.model.replace('.', '-')}",
        f"speed-{story.complexity.speed}",
    )


def _dedupe_labels(labels: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(label for label in labels if label))


def _require_text(field_name: str, value: str) -> None:
    if not value.strip():
        raise JiraCreationWorkflowError(f"{field_name} is required")
