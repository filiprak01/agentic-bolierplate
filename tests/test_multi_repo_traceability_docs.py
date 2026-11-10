from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_multi_repo_traceability_policy_documents_required_lanes_and_fallback() -> None:
    policy = (PROJECT_ROOT / "docs/multi-repo-jira-github-traceability.md").read_text(encoding="utf-8")

    assert "target-implementation" in policy
    assert "boilerplate-process" in policy
    assert "documentation" in policy
    assert "automation" in policy
    assert "Expected Repositories" in policy
    assert "manual Jira PR link" in policy
    assert "Boilerplate/process repository PRs" in policy


def test_story_and_pr_workflows_reference_multi_repo_traceability_policy() -> None:
    story_workflow = (PROJECT_ROOT / "docs/jira-story-creation-workflow.md").read_text(encoding="utf-8")
    pr_workflow = (PROJECT_ROOT / "docs/developer-pull-request-creation-workflow.md").read_text(encoding="utf-8")
    agents = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")

    assert "Expected Repositories" in story_workflow
    assert "docs/multi-repo-jira-github-traceability.md" in story_workflow
    assert "Multi-Repo PR Traceability" in pr_workflow
    assert "docs/multi-repo-jira-github-traceability.md" in pr_workflow
    assert "For multi-repository work" in agents


def test_setup_docs_include_repository_lane_env_vars() -> None:
    env_example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    credential_setup = (PROJECT_ROOT / "docs/credential-setup.md").read_text(encoding="utf-8")
    github_adapter = (PROJECT_ROOT / "docs/github-adapter.md").read_text(encoding="utf-8")
    target_layout = (PROJECT_ROOT / "docs/target-project-layout.md").read_text(encoding="utf-8")

    for expected in (
        "TARGET_IMPLEMENTATION_REPOSITORY",
        "BOILERPLATE_PROCESS_REPOSITORY",
        "DOCUMENTATION_REPOSITORY",
        "AUTOMATION_REPOSITORY",
        "TARGET_IMPLEMENTATION_JIRA_DEV_PANEL_EXPECTED",
    ):
        assert expected in env_example
        assert expected in credential_setup
    assert "DOCUMENTATION_REPOSITORY" in github_adapter
    assert "AUTOMATION_REPOSITORY" in target_layout
