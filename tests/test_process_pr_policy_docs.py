from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_developer_pr_workflow_documents_ready_by_default_and_draft_exceptions() -> None:
    workflow = (PROJECT_ROOT / "docs/developer-pull-request-creation-workflow.md").read_text(encoding="utf-8")
    developer_role = (PROJECT_ROOT / "ai_agents/roles/developer.md").read_text(encoding="utf-8")

    assert "open ready for review by default" in workflow
    assert "A draft pull\nrequest is allowed only" in workflow
    assert "Product Owner instruction" in workflow
    assert "opened as non-draft" in workflow
    assert "Open Developer Agent pull requests ready for review by default" in developer_role


def test_review_workflow_documents_process_repository_merge_ownership() -> None:
    workflow = (PROJECT_ROOT / "docs/review-agent-pr-workflow.md").read_text(encoding="utf-8")
    review_role = (PROJECT_ROOT / "ai_agents/roles/review.md").read_text(encoding="utf-8")

    assert "Process Repository Ownership" in workflow
    assert "process-review or release-manager merge owner" in workflow
    assert "does not silently" in workflow
    assert "merge\nownership belongs to another process owner" in review_role


def test_jira_status_workflow_documents_process_story_closure_rule() -> None:
    workflow = (PROJECT_ROOT / "docs/jira-status-transition-workflow.md").read_text(encoding="utf-8")

    assert "Process Story Closure" in workflow
    assert "can skip Tester\nAgent execution only when" in workflow
    assert "ready-for-review pull request is opened" in workflow
    assert "Developer Agent does not merge process-story pull requests" in workflow
