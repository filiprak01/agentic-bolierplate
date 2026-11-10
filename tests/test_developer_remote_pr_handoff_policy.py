from pathlib import Path

import pytest

from agentic_boilerplate.domain import (
    DeveloperCommitStage,
    DeveloperCommitStageStatus,
    DeveloperPullRequestPlan,
    execute_developer_pull_request_creation,
)
from agentic_boilerplate.integrations import GitHubAdapterConfig, GitHubAdapterError, MockGitHubRepositoryAdapter


REPOSITORY = "ExampleOrg/example-repo"


def test_developer_pr_creation_requires_pushed_remote_head_branch() -> None:
    adapter = MockGitHubRepositoryAdapter(GitHubAdapterConfig(repository=REPOSITORY, default_branch="main"))

    with pytest.raises(GitHubAdapterError) as exc:
        execute_developer_pull_request_creation(adapter, _ready_plan())

    assert "Mock GitHub branch does not exist: feature/AGENT-1052-remote-pr-handoff" in str(exc.value)


def test_developer_handoff_docs_block_dev_completed_until_visible_pr_exists() -> None:
    project_root = Path(__file__).resolve().parents[1]
    combined = "\n".join(
        (
            (project_root / "ai_agents/roles/developer.md").read_text(encoding="utf-8"),
            (project_root / "docs/developer-pull-request-creation-workflow.md").read_text(encoding="utf-8"),
        )
    ).lower()
    normalized = " ".join(combined.split())

    assert "remote feature branch" in normalized
    assert "do not move a story or bug to `dev completed`" in normalized
    assert "visible pr trace" in normalized
    assert "github actions should run automatically" in normalized
    assert "should not poll or rerun remote ci after every local commit" in normalized
    assert "review agent checks ci at review time" in normalized


def _ready_plan() -> DeveloperPullRequestPlan:
    return DeveloperPullRequestPlan(
        jira_issue_key="AGENT-1052",
        summary="Add Developer Agent remote PR handoff guarantee",
        branch_name="feature/AGENT-1052-remote-pr-handoff",
        base_branch="main",
        assignment_id="assignment-AGENT-1052",
        stages=(
            DeveloperCommitStage(
                stage_id="stage-1",
                jira_subtask_key="AGENT-1052",
                title="Remote PR handoff policy",
                validation_commands=("pytest",),
                commit_sha="abc1234",
                status=DeveloperCommitStageStatus.COMMITTED,
            ),
        ),
        validation_log_paths=("data/agent-logs/AGENT-1050/validation/stage-2.md",),
    )
