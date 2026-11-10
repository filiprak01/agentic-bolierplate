from agentic_boilerplate import domain, storage
from agentic_boilerplate.domain.backlog_draft import (
    RequirementEpicInput,
    RequirementInput,
    RequirementSprintInput,
    RequirementStoryInput,
    create_backlog_draft,
)
from agentic_boilerplate.domain.jira_creation_workflow import (
    ApprovedBacklogDraft,
    JiraCreationWorkflowError,
    build_jira_backlog_creation_plan,
    execute_jira_backlog_creation_plan,
    jira_creation_result_from_dict,
    jira_creation_result_to_dict,
    jira_issue_fields_for_plan,
)
from agentic_boilerplate.domain.story_complexity import ComplexityLevel
from agentic_boilerplate.integrations.jira import JiraAdapterConfig, JiraIssue, MockJiraProjectIssueAdapter
from agentic_boilerplate.storage.jira_creation_result import FileJiraCreationResultStore


class StatuslessCreateAdapter(MockJiraProjectIssueAdapter):
    def create_issue(self, fields):
        created = super().create_issue(fields)
        return JiraIssue(
            key=created.key,
            summary=created.summary,
            issue_type=created.issue_type,
            status="",
            labels=created.labels,
            parent_key=created.parent_key,
        )


def sample_approved_draft() -> ApprovedBacklogDraft:
    draft = create_backlog_draft(
        RequirementInput(
            key="REQ-JIRA-CREATION",
            title="Jira creation workflow",
            overview="Create Jira issues from approved local drafts.",
            epics=(
                RequirementEpicInput(
                    id="EPIC-JIRA",
                    title="Jira Story Creation",
                    description="Create Jira issue hierarchy from approved drafts.",
                    stories=(
                        RequirementStoryInput(
                            id="STORY-JIRA-1",
                            title="Create first Jira story",
                            description="Create the first draft story in Jira.",
                            acceptance_criteria=("Story starts in Funnel.",),
                            prerequisite_story_ids=(),
                            complexity=ComplexityLevel.C2,
                            complexity_rationale="Single story creation operation.",
                        ),
                        RequirementStoryInput(
                            id="STORY-JIRA-2",
                            title="Create dependent Jira story",
                            description="Create the dependent draft story in Jira.",
                            acceptance_criteria=("Blocks dependency is preserved.",),
                            prerequisite_story_ids=("STORY-JIRA-1",),
                            complexity=ComplexityLevel.C3,
                            complexity_rationale="Dependency linking affects scheduler eligibility.",
                        ),
                    ),
                ),
            ),
            sprint_rings=(
                RequirementSprintInput(
                    id="SPRINT-1",
                    name="Jira creation sprint",
                    goal="Create approved Jira backlog.",
                    story_ids=("STORY-JIRA-1", "STORY-JIRA-2"),
                ),
            ),
        ),
        created_at="2026-06-21T08:40:00Z",
    )
    return ApprovedBacklogDraft(
        draft=draft,
        approved_by="Product Owner",
        approved_at="2026-06-21T08:45:00Z",
    )


def test_build_jira_creation_plan_preserves_lineage_labels_and_complexity() -> None:
    plan = build_jira_backlog_creation_plan(
        sample_approved_draft(),
        jira_config=JiraAdapterConfig(
            base_url="https://example.atlassian.net",
            project_key="AGENT",
            board_id="1",
        ),
        sprint_label="mvp-sprint-05",
        sprint_ring_label="sprint-ring-05",
        release_label="release-mvp",
    )

    assert plan.project_key == "AGENT"
    assert plan.expected_initial_status == "FUNNEL"
    assert tuple(issue.draft_id for issue in plan.issues) == ("EPIC-JIRA", "STORY-JIRA-1", "STORY-JIRA-2")
    assert plan.issues[0].fields.issue_type == "Epic"
    assert plan.issues[1].fields.issue_type == "Story"
    assert plan.issues[1].parent_draft_id == "EPIC-JIRA"
    assert "REQ-JIRA-CREATION" in plan.issues[1].fields.description
    assert "STORY-JIRA-1-AC1. Story starts in Funnel." in plan.issues[1].fields.description
    assert "Sprint proposal:" in plan.issues[1].fields.description
    assert "SPRINT-1 - Jira creation sprint: Create approved Jira backlog." in plan.issues[1].fields.description
    assert "Context references:" in plan.issues[1].fields.description
    assert "data/context-packs/STORY-JIRA-1/context-pack.md" in plan.issues[1].fields.description
    assert "complexity-c2" in plan.issues[1].fields.labels
    assert "reasoning-medium" in plan.issues[1].fields.labels
    assert "mvp-sprint-05" in plan.issues[1].fields.labels
    assert plan.dependency_links[0].prerequisite_draft_story_id == "STORY-JIRA-1"
    assert plan.dependency_links[0].dependent_draft_story_id == "STORY-JIRA-2"
    assert plan.dependency_links[0].link_type == "Blocks"


def test_child_issue_fields_require_created_parent_key() -> None:
    plan = build_jira_backlog_creation_plan(
        sample_approved_draft(),
        jira_config=JiraAdapterConfig(
            base_url="https://example.atlassian.net",
            project_key="AGENT",
            board_id="1",
        ),
        sprint_label="mvp-sprint-05",
        sprint_ring_label="sprint-ring-05",
        release_label="release-mvp",
    )

    try:
        jira_issue_fields_for_plan(plan.issues[1])
    except JiraCreationWorkflowError as exc:
        assert "created_parent_key is required" in str(exc)
    else:
        raise AssertionError("Expected JiraCreationWorkflowError")

    fields = jira_issue_fields_for_plan(plan.issues[1], created_parent_key="AGENT-100")
    assert fields.parent_key == "AGENT-100"
    assert fields.summary == "Create first Jira story"


def test_jira_creation_plan_requires_po_approval_metadata() -> None:
    approved = sample_approved_draft()
    invalid = ApprovedBacklogDraft(
        draft=approved.draft,
        approved_by=" ",
        approved_at="2026-06-21T08:45:00Z",
    )

    try:
        build_jira_backlog_creation_plan(
            invalid,
            jira_config=JiraAdapterConfig(
                base_url="https://example.atlassian.net",
                project_key="AGENT",
                board_id="1",
            ),
            sprint_label="mvp-sprint-05",
            sprint_ring_label="sprint-ring-05",
            release_label="release-mvp",
        )
    except JiraCreationWorkflowError as exc:
        assert "approved_by is required" in str(exc)
    else:
        raise AssertionError("Expected JiraCreationWorkflowError")


def test_execute_jira_creation_plan_creates_issues_and_blocks_links() -> None:
    config = JiraAdapterConfig(
        base_url="https://example.atlassian.net",
        project_key="AGENT",
        board_id="1",
    )
    plan = build_jira_backlog_creation_plan(
        sample_approved_draft(),
        jira_config=config,
        sprint_label="mvp-sprint-05",
        sprint_ring_label="sprint-ring-05",
        release_label="release-mvp",
    )
    adapter = MockJiraProjectIssueAdapter(config, issue_types=("Epic", "Story", "Subtask"))

    result = execute_jira_backlog_creation_plan(
        plan,
        adapter=adapter,
        created_at="2026-06-21T09:00:00Z",
    )

    assert tuple(mapping.jira_key for mapping in result.issue_mappings) == ("AGENT-1", "AGENT-2", "AGENT-3")
    assert result.issue_mappings[0].issue_type == "Epic"
    assert result.issue_mappings[1].parent_jira_key == "AGENT-1"
    assert result.issue_mappings[1].actual_status == "FUNNEL"
    assert result.dependency_links[0].blocker_jira_key == "AGENT-2"
    assert result.dependency_links[0].blocked_jira_key == "AGENT-3"
    assert adapter.get_dependency_links("AGENT-3").blockers == ("AGENT-2",)


def test_execute_jira_creation_plan_uses_expected_status_when_adapter_create_is_statusless() -> None:
    config = JiraAdapterConfig(
        base_url="https://example.atlassian.net",
        project_key="AGENT",
        board_id="1",
    )
    plan = build_jira_backlog_creation_plan(
        sample_approved_draft(),
        jira_config=config,
        sprint_label="mvp-sprint-05",
        sprint_ring_label="sprint-ring-05",
        release_label="release-mvp",
    )

    result = execute_jira_backlog_creation_plan(
        plan,
        adapter=StatuslessCreateAdapter(config, issue_types=("Epic", "Story", "Subtask")),
        created_at="2026-06-21T09:00:00Z",
    )

    assert {mapping.actual_status for mapping in result.issue_mappings} == {"FUNNEL"}


def test_jira_creation_result_serializes_for_resume() -> None:
    config = JiraAdapterConfig(
        base_url="https://example.atlassian.net",
        project_key="AGENT",
        board_id="1",
    )
    plan = build_jira_backlog_creation_plan(
        sample_approved_draft(),
        jira_config=config,
        sprint_label="mvp-sprint-05",
        sprint_ring_label="sprint-ring-05",
        release_label="release-mvp",
    )
    result = execute_jira_backlog_creation_plan(
        plan,
        adapter=MockJiraProjectIssueAdapter(config, issue_types=("Epic", "Story", "Subtask")),
        created_at="2026-06-21T09:00:00Z",
    )

    restored = jira_creation_result_from_dict(jira_creation_result_to_dict(result))

    assert restored == result


def test_file_jira_creation_result_store_roundtrip(tmp_path) -> None:
    config = JiraAdapterConfig(
        base_url="https://example.atlassian.net",
        project_key="AGENT",
        board_id="1",
    )
    plan = build_jira_backlog_creation_plan(
        sample_approved_draft(),
        jira_config=config,
        sprint_label="mvp-sprint-05",
        sprint_ring_label="sprint-ring-05",
        release_label="release-mvp",
    )
    result = execute_jira_backlog_creation_plan(
        plan,
        adapter=MockJiraProjectIssueAdapter(config, issue_types=("Epic", "Story", "Subtask")),
        created_at="2026-06-21T09:00:00Z",
    )
    store = FileJiraCreationResultStore(tmp_path / "jira-creation-results")

    location = store.save(result)
    restored = store.read(result.draft_key)

    assert location.path.name == "REQ-JIRA-CREATION.json"
    assert restored == result


def test_jira_creation_workflow_public_api_exports_are_available() -> None:
    assert domain.ApprovedBacklogDraft is ApprovedBacklogDraft
    assert domain.build_jira_backlog_creation_plan is build_jira_backlog_creation_plan
    assert domain.execute_jira_backlog_creation_plan is execute_jira_backlog_creation_plan
    assert domain.jira_creation_result_to_dict is jira_creation_result_to_dict
    assert storage.FileJiraCreationResultStore is FileJiraCreationResultStore
