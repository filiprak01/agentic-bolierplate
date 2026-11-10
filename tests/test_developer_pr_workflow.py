import pytest

from agentic_boilerplate.domain import (
    DeveloperCommitStage,
    DeveloperCommitStageStatus,
    DeveloperPullRequestPlan,
    DeveloperPullRequestStackMetadata,
    DeveloperPullRequestWorkflowError,
    DeveloperStackExecutionMode,
    StoryBackedChangeSurface,
    developer_pull_request_result_to_dict,
    execute_developer_pull_request_creation,
    github_pull_request_fields_for_plan,
    jira_status_after_developer_pull_request_created,
    render_developer_pull_request_body,
    render_jira_pr_created_comment,
    require_ready_for_pull_request,
)
from agentic_boilerplate.integrations import GitHubAdapterConfig, MockGitHubRepositoryAdapter
from agentic_boilerplate.storage import FileDeveloperPullRequestResultStore


def test_pull_request_plan_requires_all_stages_committed_and_validation_logs() -> None:
    plan = _ready_plan()

    assert require_ready_for_pull_request(plan) == plan


def test_pull_request_plan_rejects_missing_validation_path() -> None:
    plan = DeveloperPullRequestPlan(
        **{
            **_ready_plan().__dict__,
            "validation_log_paths": (),
        }
    )

    with pytest.raises(DeveloperPullRequestWorkflowError) as exc:
        require_ready_for_pull_request(plan)

    assert "Every development stage must have durable validation evidence" in str(exc.value)


def test_pull_request_plan_rejects_blank_validation_path() -> None:
    plan = DeveloperPullRequestPlan(
        **{
            **_ready_plan().__dict__,
            "validation_log_paths": (" ",),
        }
    )

    with pytest.raises(DeveloperPullRequestWorkflowError) as exc:
        require_ready_for_pull_request(plan)

    assert "validation_log_paths[0]" in str(exc.value)


def test_pull_request_plan_rejects_uncommitted_stage() -> None:
    stage = DeveloperCommitStage(
        stage_id="stage-1",
        jira_subtask_key="AGENT-258",
        title="PR eligibility and body model",
        validation_commands=("pytest",),
        status=DeveloperCommitStageStatus.VALIDATED,
    )
    plan = DeveloperPullRequestPlan(
        jira_issue_key="AGENT-46",
        summary="Implement Developer Pull Request Creation Workflow",
        branch_name="feature/AGENT-46-developer-pr-creation",
        base_branch="main",
        stages=(stage,),
        validation_log_paths=("data/agent-logs/AGENT-46/validation/stage-1.md",),
    )

    with pytest.raises(DeveloperPullRequestWorkflowError) as exc:
        require_ready_for_pull_request(plan)

    assert "Development stage must be committed before PR creation" in str(exc.value)


def test_pull_request_body_links_jira_subtasks_commits_and_validation_logs() -> None:
    body = render_developer_pull_request_body(_ready_plan())

    assert "Jira: AGENT-46" in body
    assert "Change surface: code-change" in body
    assert "Affects boilerplate behavior: yes" in body
    assert "AGENT-258: PR eligibility and body model (abc1234)" in body
    assert "data/agent-logs/AGENT-46/validation/stage-1.md" in body
    assert "Jira-visible pull request trace is required" in body
    assert "Review and merge are handled by the Review Agent workflow." in body


def test_stacked_pull_request_body_includes_stack_metadata() -> None:
    body = render_developer_pull_request_body(_stacked_plan())

    assert "## Stacked PR" in body
    assert "Stack ID: stack-agent-687" in body
    assert "Mode: base-branch-fallback" in body
    assert "Layer: 3" in body
    assert "Base branch: feature/AGENT-688-stack-metadata" in body
    assert "Parent PR: #200 https://github.com/example-org/agentic-boilerplate/pull/200" in body
    assert "Child stories: AGENT-690" in body
    assert "Context pack: data/context-packs/AGENT-689/context-pack.json" in body


def test_stacked_pull_request_fields_target_parent_branch_in_fallback_mode() -> None:
    fields = github_pull_request_fields_for_plan(_stacked_plan())

    assert fields.head == "feature/AGENT-689-developer-stacked-pr-workflow"
    assert fields.base == "feature/AGENT-688-stack-metadata"
    assert fields.draft is False
    assert "Mode: base-branch-fallback" in fields.body


def test_gh_stack_mode_is_recorded_in_pr_body_without_changing_jira_branch_format() -> None:
    plan = DeveloperPullRequestPlan(
        **{
            **_stacked_plan().__dict__,
            "stack_metadata": DeveloperPullRequestStackMetadata(
                **{
                    **_stacked_plan().stack_metadata.__dict__,
                    "execution_mode": DeveloperStackExecutionMode.GH_STACK,
                }
            ),
        }
    )

    fields = github_pull_request_fields_for_plan(plan)

    assert fields.head == "feature/AGENT-689-developer-stacked-pr-workflow"
    assert fields.base == "feature/AGENT-688-stack-metadata"
    assert "Mode: gh-stack" in fields.body


def test_stacked_pull_request_plan_rejects_stale_upper_layer() -> None:
    plan = DeveloperPullRequestPlan(
        **{
            **_stacked_plan().__dict__,
            "stack_metadata": DeveloperPullRequestStackMetadata(
                **{
                    **_stacked_plan().stack_metadata.__dict__,
                    "stale_state": "parent-branch-changed",
                    "rebase_required": True,
                }
            ),
        }
    )

    with pytest.raises(DeveloperPullRequestWorkflowError) as exc:
        require_ready_for_pull_request(plan)

    assert "must be rebased before PR creation" in str(exc.value)


def test_stacked_pull_request_plan_rejects_cross_repo_stack() -> None:
    plan = DeveloperPullRequestPlan(
        **{
            **_stacked_plan().__dict__,
            "stack_metadata": DeveloperPullRequestStackMetadata(
                **{
                    **_stacked_plan().stack_metadata.__dict__,
                    "parent_repository": "example-org/other-repo",
                }
            ),
        }
    )

    with pytest.raises(DeveloperPullRequestWorkflowError) as exc:
        require_ready_for_pull_request(plan)

    assert "cross-fork or cross-repo stacks are blocked" in str(exc.value)


def test_github_pull_request_fields_are_built_from_ready_plan() -> None:
    fields = github_pull_request_fields_for_plan(_ready_plan())

    assert fields.title == "AGENT-46 Implement Developer Pull Request Creation Workflow"
    assert fields.head == "feature/AGENT-46-developer-pr-creation"
    assert fields.base == "main"
    assert fields.draft is False
    assert "AGENT-258" in fields.body


def test_github_pull_request_fields_can_be_explicitly_draft_for_exception() -> None:
    fields = github_pull_request_fields_for_plan(_ready_plan(), draft=True)

    assert fields.draft is True


def test_execute_developer_pull_request_creation_uses_github_adapter() -> None:
    adapter = MockGitHubRepositoryAdapter(
        GitHubAdapterConfig(repository="ExampleOrg/example-repo", default_branch="main")
    )
    adapter.create_branch("feature/AGENT-46-developer-pr-creation", "main")

    result = execute_developer_pull_request_creation(adapter, _ready_plan())

    assert result.created is True
    assert result.pull_request_number == 1
    assert result.pull_request_url == "https://github.com/ExampleOrg/example-repo/pull/1"
    assert result.head_branch == "feature/AGENT-46-developer-pr-creation"
    assert result.base_branch == "main"
    assert result.head_sha == "0" * 40


def test_pull_request_result_is_stored_for_assignment_state(tmp_path) -> None:
    adapter = MockGitHubRepositoryAdapter(
        GitHubAdapterConfig(repository="ExampleOrg/example-repo", default_branch="main")
    )
    adapter.create_branch("feature/AGENT-46-developer-pr-creation", "main")
    result = execute_developer_pull_request_creation(adapter, _ready_plan(), draft=False)

    location = FileDeveloperPullRequestResultStore(tmp_path).write(result)

    assert location.path == tmp_path / "AGENT-46" / "pull-request.json"
    assert '"pull_request_number": 1' in location.path.read_text(encoding="utf-8")
    assert developer_pull_request_result_to_dict(result)["created"] is True


def test_jira_comment_and_status_are_prepared_after_pr_creation() -> None:
    adapter = MockGitHubRepositoryAdapter(
        GitHubAdapterConfig(repository="ExampleOrg/example-repo", default_branch="main")
    )
    adapter.create_branch("feature/AGENT-46-developer-pr-creation", "main")
    result = execute_developer_pull_request_creation(adapter, _ready_plan(), draft=False)

    comment = render_jira_pr_created_comment(_ready_plan(), result)

    assert jira_status_after_developer_pull_request_created() == "DEV COMPLETED"
    assert "Developer pull request created for AGENT-46." in comment
    assert "https://github.com/ExampleOrg/example-repo/pull/1" in comment
    assert "Commits:" in comment
    assert "abc1234" in comment
    assert "Validation evidence:" in comment
    assert "Review result: pending review" in comment


def test_jira_comment_includes_stacked_pr_metadata() -> None:
    adapter = MockGitHubRepositoryAdapter(
        GitHubAdapterConfig(repository="example-org/agentic-boilerplate", default_branch="main")
    )
    adapter.create_branch("feature/AGENT-688-stack-metadata", "main")
    adapter.create_branch("feature/AGENT-689-developer-stacked-pr-workflow", "feature/AGENT-688-stack-metadata")
    result = execute_developer_pull_request_creation(adapter, _stacked_plan(), draft=False)

    comment = render_jira_pr_created_comment(_stacked_plan(), result)

    assert "Stacked PR metadata:" in comment
    assert "Stack: stack-agent-687" in comment
    assert "Parent PR: #200 https://github.com/example-org/agentic-boilerplate/pull/200" in comment
    assert "Base: feature/AGENT-688-stack-metadata" in comment


def test_pull_request_body_includes_sprint_related_jira_and_process_scope() -> None:
    plan = DeveloperPullRequestPlan(
        **{
            **_ready_plan().__dict__,
            "change_surface": StoryBackedChangeSurface.PROCESS_DOCUMENTATION,
            "affects_boilerplate_behavior": False,
            "related_jira_issue_keys": ("AGENT-40", "AGENT-41"),
            "sprint_name": "Sprint 8",
            "sprint_publication_task_key": "AGENT-283",
        }
    )

    body = render_developer_pull_request_body(plan)

    assert "Change surface: process-documentation" in body
    assert "Affects boilerplate behavior: no" in body
    assert "Sprint: Sprint 8" in body
    assert "Sprint publication task: AGENT-283" in body
    assert "Related Jira: AGENT-40, AGENT-41" in body
    assert "retro, closure, and related Jira references" in body


def _ready_plan() -> DeveloperPullRequestPlan:
    return DeveloperPullRequestPlan(
        jira_issue_key="AGENT-46",
        summary="Implement Developer Pull Request Creation Workflow",
        branch_name="feature/AGENT-46-developer-pr-creation",
        base_branch="main",
        assignment_id="assignment-AGENT-46",
        stages=(
            DeveloperCommitStage(
                stage_id="stage-1",
                jira_subtask_key="AGENT-258",
                title="PR eligibility and body model",
                validation_commands=("pytest",),
                commit_sha="abc1234",
                status=DeveloperCommitStageStatus.COMMITTED,
            ),
        ),
        validation_log_paths=("data/agent-logs/AGENT-46/validation/stage-1.md",),
    )


def _stacked_plan() -> DeveloperPullRequestPlan:
    return DeveloperPullRequestPlan(
        jira_issue_key="AGENT-689",
        summary="Implement Developer Agent stacked branch and PR workflow",
        branch_name="feature/AGENT-689-developer-stacked-pr-workflow",
        base_branch="feature/AGENT-688-stack-metadata",
        assignment_id="assignment-AGENT-689",
        stages=(
            DeveloperCommitStage(
                stage_id="stage-1",
                jira_subtask_key="AGENT-946",
                title="Stacked developer workflow",
                validation_commands=("pytest",),
                commit_sha="abc1234",
                status=DeveloperCommitStageStatus.COMMITTED,
            ),
        ),
        validation_log_paths=("data/agent-logs/AGENT-689/validation/stage-1.md",),
        related_jira_issue_keys=("AGENT-687", "AGENT-688"),
        stack_metadata=DeveloperPullRequestStackMetadata(
            stack_id="stack-agent-687",
            lane_id="stack-lane-agent-687",
            execution_mode=DeveloperStackExecutionMode.BASE_BRANCH_FALLBACK,
            stack_layer=3,
            stack_trunk="main",
            parent_story_key="AGENT-688",
            parent_branch="feature/AGENT-688-stack-metadata",
            parent_pull_request_number=200,
            parent_pull_request_url="https://github.com/example-org/agentic-boilerplate/pull/200",
            child_story_keys=("AGENT-690",),
            context_pack_path="data/context-packs/AGENT-689/context-pack.json",
            repository="example-org/agentic-boilerplate",
            parent_repository="example-org/agentic-boilerplate",
        ),
    )
