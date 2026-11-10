from pathlib import Path

from agentic_boilerplate.domain.review_queue_report import (
    ReviewQueueBlockerType,
    ReviewQueueCheckState,
    ReviewQueueJiraIssue,
    ReviewQueuePullRequest,
    build_review_queue_item,
)


def test_missing_remote_ci_blocks_even_with_local_validation_evidence() -> None:
    item = build_review_queue_item(
        pull_request=ReviewQueuePullRequest(
            repository="target/app",
            number=27,
            title="AGENT-1050 review CI gate",
            url="https://github.com/target/app/pull/27",
            head_branch="feature/AGENT-1050-review-ci-gate",
            base_branch="main",
            state="open",
            draft=False,
            mergeable_state="clean",
            check_state=ReviewQueueCheckState.MISSING,
        ),
        jira_issue=ReviewQueueJiraIssue(
            key="AGENT-1050",
            summary="Block review approval when CI is missing",
            issue_type="Story",
            status="DEV COMPLETED",
            visible_pr_link=True,
            evidence_paths=("data/agent-logs/AGENT-1050/local-validation.md",),
        ),
        local_validation_evidence=("data/agent-logs/AGENT-1050/local-validation.md",),
    )

    assert item.review_ready is False
    assert ReviewQueueBlockerType.CHECKS_MISSING in item.blocker_types
    assert item.next_owner == "Developer Agent"


def test_stale_base_blocks_even_when_ci_passed() -> None:
    item = build_review_queue_item(
        pull_request=ReviewQueuePullRequest(
            repository="target/app",
            number=28,
            title="AGENT-1050 stale review gate",
            url="https://github.com/target/app/pull/28",
            head_branch="feature/AGENT-1050-stale-review-gate",
            base_branch="main",
            state="open",
            draft=False,
            mergeable_state="behind",
            check_state=ReviewQueueCheckState.SUCCESS,
            check_names=("Pytest", "Docker Compose"),
        ),
        jira_issue=ReviewQueueJiraIssue(
            key="AGENT-1050",
            summary="Block stale base before merge",
            issue_type="Story",
            status="DEV COMPLETED",
            visible_pr_link=True,
        ),
    )

    assert item.review_ready is False
    assert item.blocker_types == (ReviewQueueBlockerType.STALE_BASE,)
    assert item.next_owner == "Developer Agent"


def test_review_docs_require_remote_ci_before_approval_or_merge(project_root: Path) -> None:
    paths = (
        project_root / "ai_agents/roles/review.md",
        project_root / "docs/review-agent-pr-workflow.md",
        project_root / "docs/review-agent-queue-report.md",
    )
    combined = "\n".join(path.read_text(encoding="utf-8") for path in paths).lower()

    assert "no workflow runs" in combined
    assert "no combined" in combined
    assert "checks-missing" in combined
    assert "local validation evidence" in combined
    assert "approval-comment fallback" in combined
    assert "token" in combined
    assert "permission" in combined
