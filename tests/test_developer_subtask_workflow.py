import pytest

from agentic_boilerplate.domain import (
    DeveloperSubtaskCompletion,
    DeveloperSubtaskStage,
    DeveloperSubtaskStatus,
    DeveloperSubtaskWorkflowError,
    active_developer_subtask_stage,
    build_developer_subtask_plan,
    build_missing_developer_subtask_context_questions,
    execute_developer_subtask_creation,
    jira_subtask_fields_for_plan,
    jira_subtask_fields_for_stage,
    render_developer_subtask_completion_note,
    render_developer_subtask_plan_summary,
)
from agentic_boilerplate.integrations import JiraAdapterConfig, MockJiraProjectIssueAdapter


def test_developer_subtask_plan_creates_visible_jira_subtask_fields() -> None:
    plan = build_developer_subtask_plan(
        parent_issue_key="AGENT-44",
        parent_issue_type="Story",
        created_at="2026-06-26T12:00:00Z",
        context_pack_path="data/context-packs/AGENT-44/context-pack.md",
        acceptance_criteria=("Create subtasks before implementation.",),
        stages=(
            DeveloperSubtaskStage(
                stage_id="stage-1",
                title="Developer subtask workflow domain model",
                description="Add typed planning and validation for implementation stages.",
                expected_changes=("Add domain module.", "Expose the model for tests."),
                validation_commands=("python -m pytest tests/test_developer_subtask_workflow.py",),
            ),
        ),
    )

    fields = jira_subtask_fields_for_stage(plan, plan.stages[0], labels=("sprint-7",))

    assert fields.summary == "AGENT-44 - Developer subtask workflow domain model"
    assert fields.issue_type == "Subtask"
    assert fields.parent_key == "AGENT-44"
    assert fields.labels == ("developer-subtask", "sprint-7")
    assert "Context pack: data/context-packs/AGENT-44/context-pack.md" in fields.description
    assert "- Add domain module." in fields.description
    assert "- python -m pytest tests/test_developer_subtask_workflow.py" in fields.description


def test_active_developer_subtask_stage_enforces_one_stage_at_a_time() -> None:
    plan = build_developer_subtask_plan(
        parent_issue_key="AGENT-44",
        parent_issue_type="Bug",
        created_at="2026-06-26T12:00:00Z",
        context_pack_path="data/context-packs/AGENT-44/context-pack.md",
        acceptance_criteria=("Bug fix is covered by developer validation.",),
        stages=(
            DeveloperSubtaskStage(
                stage_id="stage-1",
                title="Done stage",
                description="Already completed.",
                status=DeveloperSubtaskStatus.DONE,
            ),
            DeveloperSubtaskStage(
                stage_id="stage-2",
                title="Next stage",
                description="Next visible implementation stage.",
                status=DeveloperSubtaskStatus.PLANNED,
            ),
        ),
    )

    assert active_developer_subtask_stage(plan) == plan.stages[1]


def test_jira_subtask_fields_for_plan_keeps_all_stages_under_parent() -> None:
    plan = build_developer_subtask_plan(
        parent_issue_key="AGENT-44",
        parent_issue_type="Story",
        created_at="2026-06-26T12:00:00Z",
        context_pack_path="data/context-packs/AGENT-44/context-pack.md",
        acceptance_criteria=("Create visible subtasks.",),
        stages=(
            DeveloperSubtaskStage(
                stage_id="stage-1",
                title="Domain model",
                description="Add domain model.",
            ),
            DeveloperSubtaskStage(
                stage_id="stage-2",
                title="Jira helpers",
                description="Add Jira helper fields.",
            ),
        ),
    )

    fields = jira_subtask_fields_for_plan(plan, labels=("sprint-7",))

    assert [field.parent_key for field in fields] == ["AGENT-44", "AGENT-44"]
    assert [field.summary for field in fields] == [
        "AGENT-44 - Domain model",
        "AGENT-44 - Jira helpers",
    ]
    assert all(field.labels == ("developer-subtask", "sprint-7") for field in fields)


def test_execute_developer_subtask_creation_returns_keyed_plan() -> None:
    adapter = MockJiraProjectIssueAdapter(
        JiraAdapterConfig(base_url="https://example.atlassian.net", project_key="AGENT", board_id="1")
    )
    plan = build_developer_subtask_plan(
        parent_issue_key="AGENT-44",
        parent_issue_type="Story",
        created_at="2026-06-26T12:00:00Z",
        context_pack_path="data/context-packs/AGENT-44/context-pack.md",
        acceptance_criteria=("Create visible subtasks.",),
        stages=(
            DeveloperSubtaskStage(
                stage_id="stage-1",
                title="Domain model",
                description="Add domain model.",
            ),
            DeveloperSubtaskStage(
                stage_id="stage-2",
                title="Jira helpers",
                description="Add Jira helper fields.",
            ),
        ),
    )

    result = execute_developer_subtask_creation(adapter, plan, labels=("sprint-7",))

    assert result.parent_issue_key == "AGENT-44"
    assert [created.stage_id for created in result.created_issues] == ["stage-1", "stage-2"]
    assert [created.jira_subtask_key for created in result.created_issues] == ["AGENT-1", "AGENT-2"]
    assert [stage.jira_subtask_key for stage in result.plan_with_keys.stages] == ["AGENT-1", "AGENT-2"]


def test_execute_developer_subtask_creation_preserves_existing_keys_on_resume() -> None:
    adapter = MockJiraProjectIssueAdapter(
        JiraAdapterConfig(base_url="https://example.atlassian.net", project_key="AGENT", board_id="1")
    )
    plan = build_developer_subtask_plan(
        parent_issue_key="AGENT-44",
        parent_issue_type="Story",
        created_at="2026-06-26T12:00:00Z",
        context_pack_path="data/context-packs/AGENT-44/context-pack.md",
        acceptance_criteria=("Create visible subtasks.",),
        stages=(
            DeveloperSubtaskStage(
                stage_id="stage-1",
                title="Existing subtask",
                description="Already created before pause.",
                jira_subtask_key="AGENT-249",
            ),
            DeveloperSubtaskStage(
                stage_id="stage-2",
                title="New subtask",
                description="Needs creation after resume.",
            ),
        ),
    )

    result = execute_developer_subtask_creation(adapter, plan)

    assert [created.jira_subtask_key for created in result.created_issues] == ["AGENT-249", "AGENT-1"]
    assert [issue.key for issue in adapter.search_issues("project = AGENT")] == ["AGENT-1"]


def test_render_developer_subtask_plan_summary_shows_next_stage() -> None:
    plan = build_developer_subtask_plan(
        parent_issue_key="AGENT-44",
        parent_issue_type="Story",
        created_at="2026-06-26T12:00:00Z",
        context_pack_path="data/context-packs/AGENT-44/context-pack.md",
        acceptance_criteria=("Create visible subtasks.",),
        stages=(
            DeveloperSubtaskStage(
                stage_id="stage-1",
                title="Done stage",
                description="Already complete.",
                jira_subtask_key="AGENT-249",
                status=DeveloperSubtaskStatus.DONE,
            ),
            DeveloperSubtaskStage(
                stage_id="stage-2",
                title="Jira helpers",
                description="Next stage.",
                jira_subtask_key="AGENT-250",
            ),
        ),
    )

    summary = render_developer_subtask_plan_summary(plan)

    assert "- stage-1 (AGENT-249): Done stage [done]" in summary
    assert "- stage-2 (AGENT-250): Jira helpers [planned]" in summary
    assert "Next developer stage: stage-2 - Jira helpers" in summary


def test_developer_subtask_plan_rejects_multiple_active_stages() -> None:
    with pytest.raises(DeveloperSubtaskWorkflowError) as exc:
        build_developer_subtask_plan(
            parent_issue_key="AGENT-44",
            parent_issue_type="Story",
            created_at="2026-06-26T12:00:00Z",
            stages=(
                DeveloperSubtaskStage(
                    stage_id="stage-1",
                    title="First active",
                    description="Active.",
                    status=DeveloperSubtaskStatus.IN_PROGRESS,
                ),
                DeveloperSubtaskStage(
                    stage_id="stage-2",
                    title="Second active",
                    description="Also active.",
                    status=DeveloperSubtaskStatus.IN_PROGRESS,
                ),
            ),
        )

    assert "Only one developer subtask stage can be in progress" in str(exc.value)


def test_developer_subtask_completion_note_records_commit_changes_and_validation() -> None:
    note = render_developer_subtask_completion_note(
        DeveloperSubtaskCompletion(
            stage=DeveloperSubtaskStage(
                stage_id="stage-1",
                title="Workflow domain",
                description="Add workflow domain.",
            ),
            commit_sha="abc1234",
            changed_files=("src/agentic_boilerplate/domain/developer_subtask_workflow.py",),
            validation_results=("tests/test_developer_subtask_workflow.py passed",),
            notes="Implemented as a reusable domain helper.",
        )
    )

    assert "Developer stage completed: stage-1 - Workflow domain" in note
    assert "Commit: abc1234" in note
    assert "- src/agentic_boilerplate/domain/developer_subtask_workflow.py" in note
    assert "- tests/test_developer_subtask_workflow.py passed" in note
    assert "Implemented as a reusable domain helper." in note


def test_missing_developer_context_creates_po_inbox_questions() -> None:
    plan = build_developer_subtask_plan(
        parent_issue_key="AGENT-44",
        parent_issue_type="Story",
        created_at="2026-06-26T12:00:00Z",
        stages=(
            DeveloperSubtaskStage(
                stage_id="stage-1",
                title="Workflow domain",
                description="Add workflow domain.",
            ),
        ),
    )

    questions = build_missing_developer_subtask_context_questions(plan)

    assert [question.jira_issue_key for question in questions] == ["AGENT-44", "AGENT-44", "AGENT-44"]
    assert {question.title for question in questions} == {
        "Missing acceptance criteria for AGENT-44",
        "Missing context pack for AGENT-44",
        "Missing developer validation commands for AGENT-44",
    }
    assert all(question.business_impact for question in questions)
