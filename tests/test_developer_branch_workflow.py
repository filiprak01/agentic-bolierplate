import pytest

from agentic_boilerplate.domain import (
    DeveloperBranchWorkflowError,
    DeveloperCommitStage,
    DeveloperCommitStageStatus,
    DeveloperStackBranchContext,
    DeveloperStackExecutionMode,
    DeveloperStageValidationResult,
    DeveloperValidationCommandResult,
    build_developer_branch_plan,
    build_feature_branch_name,
    build_stacked_developer_branch_plan,
    commit_message_for_stage,
    mark_stage_committed,
    mark_stage_validated,
    next_developer_commit_stage,
    resolve_stacked_developer_branch_decision,
    render_stage_validation_result,
    validation_output_path,
)
from agentic_boilerplate.storage import DeveloperValidationStoreError, FileDeveloperValidationStore


def test_feature_branch_name_uses_jira_key_and_short_slug() -> None:
    branch = build_feature_branch_name("agent-45", "Implement Developer Branch Commit And Validation Workflow")

    assert branch == "feature/AGENT-45-implement-developer-branch-commit-and-validation"


def test_developer_branch_plan_defaults_branch_and_validation_output_root() -> None:
    plan = build_developer_branch_plan(
        jira_issue_key="AGENT-45",
        summary="Implement Developer Branch Commit And Validation Workflow",
        base_branch="main",
        target_repo_path="/workspace/repo",
        stages=(
            DeveloperCommitStage(
                stage_id="stage-1",
                jira_subtask_key="AGENT-255",
                title="Branch and commit workflow model",
                validation_commands=("python -m pytest tests/test_developer_branch_workflow.py",),
            ),
        ),
    )

    assert plan.branch_name == "feature/AGENT-45-implement-developer-branch-commit-and-validation"
    assert plan.validation_output_root == "data/agent-logs/AGENT-45/validation"
    assert next_developer_commit_stage(plan) == plan.stages[0]


def test_developer_branch_plan_rejects_non_feature_branch_name() -> None:
    with pytest.raises(DeveloperBranchWorkflowError) as exc:
        build_developer_branch_plan(
            jira_issue_key="AGENT-45",
            summary="Implement Developer Branch Commit And Validation Workflow",
            branch_name="bugfix/AGENT-45-wrong",
            base_branch="main",
            target_repo_path="/workspace/repo",
            stages=(
                DeveloperCommitStage(
                    stage_id="stage-1",
                    jira_subtask_key="AGENT-255",
                    title="Branch and commit workflow model",
                    validation_commands=("python -m pytest tests/test_developer_branch_workflow.py",),
                ),
            ),
        )

    assert "feature/AGENT-45-" in str(exc.value)


def test_developer_branch_plan_requires_validation_commands_before_completion() -> None:
    with pytest.raises(DeveloperBranchWorkflowError) as exc:
        build_developer_branch_plan(
            jira_issue_key="AGENT-45",
            summary="Implement Developer Branch Commit And Validation Workflow",
            base_branch="main",
            target_repo_path="/workspace/repo",
            stages=(
                DeveloperCommitStage(
                    stage_id="stage-1",
                    jira_subtask_key="AGENT-255",
                    title="Branch and commit workflow model",
                    validation_commands=(),
                ),
            ),
        )

    assert "Validation commands are required" in str(exc.value)


def test_stacked_developer_branch_plan_uses_parent_branch_for_upper_layer() -> None:
    plan = build_stacked_developer_branch_plan(
        jira_issue_key="AGENT-689",
        summary="Implement Developer Agent stacked branch and PR workflow",
        target_repo_path="/workspace/repo",
        stack_context=DeveloperStackBranchContext(
            stack_id="stack-agent-687",
            lane_id="stack-lane-agent-687",
            stack_trunk="main",
            stack_layer=3,
            repository="example-org/agentic-boilerplate",
            parent_repository="example-org/agentic-boilerplate",
            parent_story_key="AGENT-688",
            parent_branch="feature/AGENT-688-stack-metadata",
            parent_story_state="review-pending",
            execution_mode=DeveloperStackExecutionMode.BASE_BRANCH_FALLBACK,
        ),
        stages=(
            DeveloperCommitStage(
                stage_id="stage-1",
                jira_subtask_key="AGENT-946",
                title="Stacked developer workflow",
                validation_commands=("pytest tests/test_developer_branch_workflow.py",),
            ),
        ),
    )

    assert plan.branch_name == "feature/AGENT-689-implement-developer-agent-stacked-branch-and-pr"
    assert plan.base_branch == "feature/AGENT-688-stack-metadata"
    assert plan.stack_decision.can_continue_upper_layer is True
    assert plan.stack_decision.execution_mode is DeveloperStackExecutionMode.BASE_BRANCH_FALLBACK


def test_stacked_developer_branch_decision_marks_stale_parent_for_rebase() -> None:
    decision = resolve_stacked_developer_branch_decision(
        DeveloperStackBranchContext(
            stack_id="stack-agent-687",
            lane_id="stack-lane-agent-687",
            stack_trunk="main",
            stack_layer=2,
            repository="example-org/agentic-boilerplate",
            parent_repository="example-org/agentic-boilerplate",
            parent_story_key="AGENT-687",
            parent_branch="feature/AGENT-687-stacked-pr-path-resolver",
            parent_story_state="review-pending",
            recorded_parent_head_sha="a" * 40,
            current_parent_head_sha="b" * 40,
        )
    )

    assert decision.rebase_required is True
    assert decision.stale_state == "parent-branch-changed"
    assert decision.blockers == ()


def test_stacked_developer_branch_plan_blocks_cross_repo_missing_auth_and_sequential_path() -> None:
    with pytest.raises(DeveloperBranchWorkflowError) as exc:
        build_stacked_developer_branch_plan(
            jira_issue_key="AGENT-689",
            summary="Implement Developer Agent stacked branch and PR workflow",
            target_repo_path="/workspace/repo",
            stack_context=DeveloperStackBranchContext(
                stack_id="stack-agent-687",
                lane_id="stack-lane-agent-687",
                stack_trunk="main",
                stack_layer=2,
                repository="example-org/agentic-boilerplate",
                parent_repository="example-org/other-repo",
                parent_story_key="AGENT-688",
                parent_branch="feature/AGENT-688-stack-metadata",
                parent_story_state="in progress",
                resolver_path_kind="sequential-only",
                github_auth_ready=False,
            ),
            stages=(
                DeveloperCommitStage(
                    stage_id="stage-1",
                    jira_subtask_key="AGENT-946",
                    title="Stacked developer workflow",
                    validation_commands=("pytest",),
                ),
            ),
        )

    message = str(exc.value)
    assert "GitHub authentication is not ready" in message
    assert "cross-fork or cross-repo stacks are blocked" in message
    assert "use sequential workflow" in message
    assert "Parent story state does not allow upper-layer stacked development" in message


def test_next_developer_commit_stage_skips_committed_stages() -> None:
    plan = build_developer_branch_plan(
        jira_issue_key="AGENT-45",
        summary="Implement Developer Branch Commit And Validation Workflow",
        base_branch="main",
        target_repo_path="/workspace/repo",
        stages=(
            DeveloperCommitStage(
                stage_id="stage-1",
                jira_subtask_key="AGENT-255",
                title="Done stage",
                validation_commands=("pytest",),
                commit_sha="abc1234",
                status=DeveloperCommitStageStatus.COMMITTED,
            ),
            DeveloperCommitStage(
                stage_id="stage-2",
                jira_subtask_key="AGENT-256",
                title="Next stage",
                validation_commands=("pytest",),
            ),
        ),
    )

    assert next_developer_commit_stage(plan) == plan.stages[1]
    assert commit_message_for_stage(plan, plan.stages[1]) == "AGENT-45 Next stage"


def test_validation_result_marks_stage_validated_or_failed() -> None:
    stage = DeveloperCommitStage(
        stage_id="stage-1",
        jira_subtask_key="AGENT-255",
        title="Branch and commit workflow model",
        validation_commands=("pytest",),
    )
    passed = DeveloperStageValidationResult(
        jira_issue_key="AGENT-45",
        stage_id="stage-1",
        jira_subtask_key="AGENT-255",
        validated_at="2026-06-26T13:00:00Z",
        command_results=(DeveloperValidationCommandResult(command="pytest", exit_code=0, output="passed"),),
    )
    failed = DeveloperStageValidationResult(
        jira_issue_key="AGENT-45",
        stage_id="stage-1",
        jira_subtask_key="AGENT-255",
        validated_at="2026-06-26T13:00:00Z",
        command_results=(DeveloperValidationCommandResult(command="pytest", exit_code=1, output="failed"),),
    )

    assert mark_stage_validated(stage, passed).status == DeveloperCommitStageStatus.VALIDATED
    assert mark_stage_validated(stage, failed).status == DeveloperCommitStageStatus.VALIDATION_FAILED


def test_stage_must_be_validated_before_marking_committed() -> None:
    stage = DeveloperCommitStage(
        stage_id="stage-1",
        jira_subtask_key="AGENT-255",
        title="Branch and commit workflow model",
        validation_commands=("pytest",),
    )

    with pytest.raises(DeveloperBranchWorkflowError):
        mark_stage_committed(stage, commit_sha="abc1234")

    committed = mark_stage_committed(
        DeveloperCommitStage(
            **{
                **stage.__dict__,
                "status": DeveloperCommitStageStatus.VALIDATED,
            }
        ),
        commit_sha="abc1234",
    )

    assert committed.status == DeveloperCommitStageStatus.COMMITTED
    assert committed.commit_sha == "abc1234"


def test_validation_output_is_rendered_and_stored_durably(tmp_path) -> None:
    plan = build_developer_branch_plan(
        jira_issue_key="AGENT-45",
        summary="Implement Developer Branch Commit And Validation Workflow",
        base_branch="main",
        target_repo_path="/workspace/repo",
        validation_output_root=str(tmp_path / "validation"),
        stages=(
            DeveloperCommitStage(
                stage_id="stage-1",
                jira_subtask_key="AGENT-255",
                title="Branch and commit workflow model",
                validation_commands=("pytest",),
            ),
        ),
    )
    output_path = validation_output_path(plan, plan.stages[0], "2026-06-26T13:00:00Z")
    validation = DeveloperStageValidationResult(
        jira_issue_key="AGENT-45",
        stage_id="stage-1",
        jira_subtask_key="AGENT-255",
        validated_at="2026-06-26T13:00:00Z",
        command_results=(DeveloperValidationCommandResult(command="pytest", exit_code=0, output="9 passed"),),
        output_path=output_path,
    )

    location = FileDeveloperValidationStore().write(validation)
    markdown = location.markdown_path.read_text(encoding="utf-8")
    data = location.json_path.read_text(encoding="utf-8")

    assert location.markdown_path.name == "stage-1-20260626T130000Z.md"
    assert "Result: PASSED" in render_stage_validation_result(validation)
    assert "9 passed" in markdown
    assert '"passed": true' in data


def test_failed_validation_output_is_stored_for_resume(tmp_path) -> None:
    validation = DeveloperStageValidationResult(
        jira_issue_key="AGENT-45",
        stage_id="stage-2",
        jira_subtask_key="AGENT-256",
        validated_at="2026-06-26T13:05:00Z",
        command_results=(DeveloperValidationCommandResult(command="pytest", exit_code=1, output="1 failed"),),
        output_path=str(tmp_path / "validation" / "stage-2-20260626T130500Z.md"),
    )

    location = FileDeveloperValidationStore().write(validation)

    assert "Result: FAILED" in location.markdown_path.read_text(encoding="utf-8")
    assert '"passed": false' in location.json_path.read_text(encoding="utf-8")


def test_validation_store_requires_output_path() -> None:
    validation = DeveloperStageValidationResult(
        jira_issue_key="AGENT-45",
        stage_id="stage-2",
        jira_subtask_key="AGENT-256",
        validated_at="2026-06-26T13:05:00Z",
        command_results=(DeveloperValidationCommandResult(command="pytest", exit_code=1, output="1 failed"),),
    )

    with pytest.raises(DeveloperValidationStoreError):
        FileDeveloperValidationStore().write(validation)
