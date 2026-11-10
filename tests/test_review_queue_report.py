import pytest

from agentic_boilerplate.domain import (
    PROCESS_REPOSITORY_OWNER,
    TARGET_REPOSITORY_OWNER,
    ReviewQueueBlockerType,
    ReviewQueueCheckState,
    ReviewQueueJiraIssue,
    ReviewQueuePullRequest,
    ReviewQueueReportError,
    ReviewQueueRepositoryKind,
    build_review_queue_item,
    build_review_queue_report,
    render_review_queue_report_markdown,
)


def test_clean_target_project_pr_is_review_ready() -> None:
    item = build_review_queue_item(
        pull_request=_pull_request(check_state=ReviewQueueCheckState.SUCCESS),
        jira_issue=_jira_issue(evidence_paths=("data/agent-logs/AP-33/review.md",)),
    )

    assert item.review_ready
    assert item.blocker_types == ()
    assert item.next_owner == TARGET_REPOSITORY_OWNER


def test_draft_dependency_and_pending_checks_block_review_pickup() -> None:
    item = build_review_queue_item(
        pull_request=_pull_request(draft=True, check_state=ReviewQueueCheckState.PENDING),
        jira_issue=_jira_issue(dependency_blockers=("AP-2",)),
    )

    assert not item.review_ready
    assert item.blocker_types == (
        ReviewQueueBlockerType.DEPENDENCY_BLOCKED,
        ReviewQueueBlockerType.DRAFT_PR,
        ReviewQueueBlockerType.CHECKS_PENDING,
    )
    assert item.next_owner == "Orchestrator/Product Owner"


def test_missing_remote_checks_block_even_when_local_validation_evidence_exists() -> None:
    item = build_review_queue_item(
        pull_request=_pull_request(check_state=ReviewQueueCheckState.MISSING),
        jira_issue=_jira_issue(),
        local_validation_evidence=("data/codex-results/AP-29/validation.md",),
    )

    assert not item.review_ready
    assert item.blocker_types == (ReviewQueueBlockerType.CHECKS_MISSING,)
    assert item.next_owner == "Developer Agent"


def test_missing_checks_without_evidence_block_review() -> None:
    item = build_review_queue_item(
        pull_request=_pull_request(check_state=ReviewQueueCheckState.MISSING),
        jira_issue=_jira_issue(),
    )

    assert not item.review_ready
    assert item.blocker_types == (ReviewQueueBlockerType.CHECKS_MISSING,)
    assert item.next_owner == "Developer Agent"


def test_stale_base_and_merge_conflict_are_separate_blockers() -> None:
    stale = build_review_queue_item(
        pull_request=_pull_request(mergeable_state="behind"),
        jira_issue=_jira_issue(),
    )
    conflicted = build_review_queue_item(
        pull_request=_pull_request(mergeable_state="dirty"),
        jira_issue=_jira_issue(),
    )

    assert stale.blocker_types == (ReviewQueueBlockerType.STALE_BASE,)
    assert conflicted.blocker_types == (ReviewQueueBlockerType.MERGE_CONFLICT,)


def test_process_repository_pr_is_handoff_not_self_merge() -> None:
    item = build_review_queue_item(
        pull_request=_pull_request(
            repository="example-org/agentic-boilerplate",
            repository_kind=ReviewQueueRepositoryKind.PROCESS,
            check_state=ReviewQueueCheckState.MISSING,
        ),
        jira_issue=_jira_issue(status="ACCEPTED/DONE"),
        local_validation_evidence=("data/agent-logs/AP-29/review/review-pr-120.md",),
    )

    assert not item.review_ready
    assert item.next_owner == PROCESS_REPOSITORY_OWNER
    assert ReviewQueueBlockerType.PROCESS_REPO_HANDOFF in item.blocker_types
    assert ReviewQueueBlockerType.WRONG_JIRA_STATUS in item.blocker_types
    assert ReviewQueueBlockerType.CHECKS_MISSING in item.blocker_types


def test_report_renders_queue_table_and_blocker_guidance() -> None:
    ready = build_review_queue_item(
        pull_request=_pull_request(number=9, check_state=ReviewQueueCheckState.SUCCESS),
        jira_issue=_jira_issue(key="AP-33", status="DEV COMPLETED"),
    )
    blocked = build_review_queue_item(
        pull_request=_pull_request(number=120, draft=True),
        jira_issue=_jira_issue(key="AP-29", visible_pr_link=False),
    )
    report = build_review_queue_report(
        generated_at="2026-07-19T03:10:00Z",
        sprint_name="AP R1 S3 Process Tooling",
        items=(ready, blocked),
    )

    markdown = render_review_queue_report_markdown(report)

    assert "# Review Agent Queue Report - AP R1 S3 Process Tooling" in markdown
    assert "Review-ready target PRs: 1" in markdown
    assert "[#9](https://github.example/pull/9)" in markdown
    assert "missing-jira-link" in markdown
    assert "Developer Agent should add a visible PR link or Jira comment." in markdown


def test_report_requires_core_fields() -> None:
    with pytest.raises(ReviewQueueReportError, match="pull_request.repository is required"):
        build_review_queue_item(
            pull_request=_pull_request(repository=""),
            jira_issue=_jira_issue(),
        )

    with pytest.raises(ReviewQueueReportError, match="sprint_name is required"):
        build_review_queue_report(generated_at="2026-07-19T03:10:00Z", sprint_name="", items=())


def _pull_request(
    *,
    repository: str = "example-org/airlines-pdf-parser",
    number: int = 9,
    draft: bool = False,
    mergeable_state: str = "clean",
    check_state: ReviewQueueCheckState = ReviewQueueCheckState.SUCCESS,
    repository_kind: ReviewQueueRepositoryKind = ReviewQueueRepositoryKind.TARGET_PROJECT,
) -> ReviewQueuePullRequest:
    return ReviewQueuePullRequest(
        repository=repository,
        number=number,
        title="AP-33 Add focused parser unittest CI",
        url=f"https://github.example/pull/{number}",
        head_branch="feature/AP-33-focused-parser-unittest-ci",
        base_branch="main",
        state="open",
        draft=draft,
        mergeable_state=mergeable_state,
        check_state=check_state,
        check_names=("Contract and parser service tests",) if check_state is ReviewQueueCheckState.SUCCESS else (),
        repository_kind=repository_kind,
    )


def _jira_issue(
    *,
    key: str = "AP-33",
    status: str = "DEV COMPLETED",
    issue_type: str = "Story",
    visible_pr_link: bool = True,
    dependency_blockers: tuple[str, ...] = (),
    incomplete_subtasks: tuple[str, ...] = (),
    evidence_paths: tuple[str, ...] = (),
) -> ReviewQueueJiraIssue:
    return ReviewQueueJiraIssue(
        key=key,
        summary="Add focused parser unittest CI",
        issue_type=issue_type,
        status=status,
        visible_pr_link=visible_pr_link,
        dependency_blockers=dependency_blockers,
        incomplete_subtasks=incomplete_subtasks,
        evidence_paths=evidence_paths,
    )
