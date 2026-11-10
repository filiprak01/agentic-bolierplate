"""Review Agent queue readiness report."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum


REVIEW_QUEUE_STATUSES = ("IN PROGRESS", "In Progress", "DEV COMPLETED", "Dev completed")
REVIEW_QUEUE_ISSUE_TYPES = ("Story", "Bug", "Task")
PROCESS_REPOSITORY_OWNER = "process-review/merge owner"
TARGET_REPOSITORY_OWNER = "Review Agent"


class ReviewQueueReportError(ValueError):
    """Raised when review queue report input is incomplete."""


class ReviewQueueBlockerType(str, Enum):
    """Blockers that prevent Review Agent pickup."""

    MISSING_JIRA_KEY = "missing-jira-key"
    MISSING_JIRA_LINK = "missing-jira-link"
    DRAFT_PR = "draft-pr"
    WRONG_JIRA_STATUS = "wrong-jira-status"
    UNSUPPORTED_ISSUE_TYPE = "unsupported-issue-type"
    DEPENDENCY_BLOCKED = "dependency-blocked"
    SUBTASKS_INCOMPLETE = "subtasks-incomplete"
    CHECKS_FAILED = "checks-failed"
    CHECKS_PENDING = "checks-pending"
    CHECKS_MISSING = "checks-missing"
    STALE_BASE = "stale-base"
    MERGE_CONFLICT = "merge-conflict"
    PROCESS_REPO_HANDOFF = "process-repo-handoff"


class ReviewQueueCheckState(str, Enum):
    """Aggregated GitHub check state for queue triage."""

    SUCCESS = "success"
    FAILED = "failed"
    PENDING = "pending"
    MISSING = "missing"
    NOT_REQUIRED = "not-required"


class ReviewQueueRepositoryKind(str, Enum):
    """Repository ownership boundary for a queued pull request."""

    TARGET_PROJECT = "target-project"
    PROCESS = "process"


@dataclass(frozen=True)
class ReviewQueuePullRequest:
    """Pull request metadata collected from GitHub."""

    repository: str
    number: int
    title: str
    url: str
    head_branch: str
    base_branch: str
    state: str
    draft: bool
    mergeable_state: str = ""
    check_state: ReviewQueueCheckState = ReviewQueueCheckState.MISSING
    check_names: tuple[str, ...] = ()
    repository_kind: ReviewQueueRepositoryKind = ReviewQueueRepositoryKind.TARGET_PROJECT


@dataclass(frozen=True)
class ReviewQueueJiraIssue:
    """Jira metadata collected for the pull request's referenced issue."""

    key: str
    summary: str
    issue_type: str
    status: str
    visible_pr_link: bool
    dependency_blockers: tuple[str, ...] = ()
    blocked_issue_keys: tuple[str, ...] = ()
    incomplete_subtasks: tuple[str, ...] = ()
    subtask_notes_present: bool = False
    evidence_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReviewQueueItem:
    """One PR/Jira pair in the Review Agent queue report."""

    pull_request: ReviewQueuePullRequest
    jira_issue: ReviewQueueJiraIssue | None
    blocker_types: tuple[ReviewQueueBlockerType, ...]
    next_owner: str

    @property
    def review_ready(self) -> bool:
        return not self.blocker_types and self.next_owner == TARGET_REPOSITORY_OWNER


@dataclass(frozen=True)
class ReviewQueueReport:
    """Queue-level readiness report."""

    generated_at: str
    sprint_name: str
    items: tuple[ReviewQueueItem, ...]

    @property
    def review_ready_items(self) -> tuple[ReviewQueueItem, ...]:
        return tuple(item for item in self.items if item.review_ready)

    @property
    def blocked_items(self) -> tuple[ReviewQueueItem, ...]:
        return tuple(item for item in self.items if item.blocker_types)


def build_review_queue_item(
    *,
    pull_request: ReviewQueuePullRequest,
    jira_issue: ReviewQueueJiraIssue | None,
    local_validation_evidence: Sequence[str] = (),
) -> ReviewQueueItem:
    """Evaluate one PR/Jira pair for Review Agent pickup."""

    _validate_pull_request(pull_request)
    evidence = tuple(path.strip() for path in local_validation_evidence if path.strip())
    blockers: list[ReviewQueueBlockerType] = []

    if jira_issue is None:
        blockers.append(ReviewQueueBlockerType.MISSING_JIRA_KEY)
    else:
        _validate_jira_issue(jira_issue)
        if jira_issue.issue_type not in REVIEW_QUEUE_ISSUE_TYPES:
            blockers.append(ReviewQueueBlockerType.UNSUPPORTED_ISSUE_TYPE)
        if not _status_matches(jira_issue.status, REVIEW_QUEUE_STATUSES):
            blockers.append(ReviewQueueBlockerType.WRONG_JIRA_STATUS)
        if not jira_issue.visible_pr_link:
            blockers.append(ReviewQueueBlockerType.MISSING_JIRA_LINK)
        if jira_issue.dependency_blockers:
            blockers.append(ReviewQueueBlockerType.DEPENDENCY_BLOCKED)
        if jira_issue.incomplete_subtasks and not jira_issue.subtask_notes_present:
            blockers.append(ReviewQueueBlockerType.SUBTASKS_INCOMPLETE)

    if pull_request.state.lower() != "open":
        blockers.append(ReviewQueueBlockerType.WRONG_JIRA_STATUS)
    if pull_request.draft:
        blockers.append(ReviewQueueBlockerType.DRAFT_PR)
    blockers.extend(_mergeability_blockers(pull_request.mergeable_state))
    blockers.extend(_check_blockers(pull_request.check_state, evidence))
    if pull_request.repository_kind is ReviewQueueRepositoryKind.PROCESS:
        blockers.append(ReviewQueueBlockerType.PROCESS_REPO_HANDOFF)

    return ReviewQueueItem(
        pull_request=pull_request,
        jira_issue=jira_issue,
        blocker_types=_dedupe_blockers(blockers),
        next_owner=_next_owner(pull_request, blockers),
    )


def build_review_queue_report(
    *,
    generated_at: str,
    sprint_name: str,
    items: Sequence[ReviewQueueItem],
) -> ReviewQueueReport:
    """Build a queue report from evaluated queue items."""

    _require_text("generated_at", generated_at)
    _require_text("sprint_name", sprint_name)
    return ReviewQueueReport(generated_at=generated_at.strip(), sprint_name=sprint_name.strip(), items=tuple(items))


def render_review_queue_report_markdown(report: ReviewQueueReport) -> str:
    """Render queue readiness as durable Markdown."""

    _require_text("generated_at", report.generated_at)
    _require_text("sprint_name", report.sprint_name)
    lines = [
        f"# Review Agent Queue Report - {report.sprint_name}",
        "",
        f"- Generated at: {report.generated_at}",
        f"- Items checked: {len(report.items)}",
        f"- Review-ready target PRs: {len(report.review_ready_items)}",
        f"- Blocked or handoff items: {len(report.blocked_items)}",
        "",
        "## Queue",
        "",
        "| Jira | Status | PR | Repo | Branch | Checks | Blockers | Next owner |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    if report.items:
        for item in report.items:
            issue = item.jira_issue
            jira_key = issue.key if issue is not None else "missing"
            status = issue.status if issue is not None else "unknown"
            blockers = ", ".join(blocker.value for blocker in item.blocker_types) or "none"
            checks = _checks_text(item.pull_request)
            branch = f"{item.pull_request.head_branch} -> {item.pull_request.base_branch}"
            pr_link = f"[#{item.pull_request.number}]({item.pull_request.url})"
            lines.append(
                "| "
                + " | ".join(
                    (
                        jira_key,
                        status,
                        pr_link,
                        item.pull_request.repository,
                        branch,
                        checks,
                        blockers,
                        item.next_owner,
                    )
                )
                + " |"
            )
    else:
        lines.append("| none | n/a | n/a | n/a | n/a | n/a | none | none |")

    lines.extend(["", "## Blockers"])
    if report.blocked_items:
        for item in report.blocked_items:
            issue_key = item.jira_issue.key if item.jira_issue is not None else "missing Jira issue"
            lines.append(f"- {issue_key} PR #{item.pull_request.number}:")
            for blocker in item.blocker_types:
                lines.append(f"  - {blocker.value}: {review_queue_blocker_guidance(blocker, item.next_owner)}")
    else:
        lines.append("- None")
    return "\n".join(lines) + "\n"


def review_queue_blocker_guidance(blocker: ReviewQueueBlockerType, next_owner: str = "") -> str:
    """Return concise owner-oriented guidance for one blocker."""

    owner = next_owner or "responsible owner"
    guidance = {
        ReviewQueueBlockerType.MISSING_JIRA_KEY: "Developer Agent should link the PR to a real Jira issue.",
        ReviewQueueBlockerType.MISSING_JIRA_LINK: "Developer Agent should add a visible PR link or Jira comment.",
        ReviewQueueBlockerType.DRAFT_PR: "Developer Agent should mark the PR ready for review.",
        ReviewQueueBlockerType.WRONG_JIRA_STATUS: "Jira owner should move the issue to a review-shaped status.",
        ReviewQueueBlockerType.UNSUPPORTED_ISSUE_TYPE: "Review Agent should skip subtasks, epics, and test issues.",
        ReviewQueueBlockerType.DEPENDENCY_BLOCKED: "Orchestrator or Product Owner should resolve prerequisite links.",
        ReviewQueueBlockerType.SUBTASKS_INCOMPLETE: "Developer Agent should complete subtasks or add handoff notes.",
        ReviewQueueBlockerType.CHECKS_FAILED: "Developer Agent should fix failing remote GitHub CI checks before review.",
        ReviewQueueBlockerType.CHECKS_PENDING: "Review Agent should wait for remote GitHub checks to finish.",
        ReviewQueueBlockerType.CHECKS_MISSING: (
            "Developer Agent should trigger remote GitHub CI and attach durable evidence; "
            "local validation is supplemental only."
        ),
        ReviewQueueBlockerType.STALE_BASE: "Developer Agent should update the PR branch against the current base and rerun CI.",
        ReviewQueueBlockerType.MERGE_CONFLICT: "Developer Agent should resolve merge conflicts.",
        ReviewQueueBlockerType.PROCESS_REPO_HANDOFF: f"{owner} should review and merge the process repository PR.",
    }
    return guidance[blocker]


def _mergeability_blockers(mergeable_state: str) -> tuple[ReviewQueueBlockerType, ...]:
    normalized = mergeable_state.strip().lower()
    if not normalized or normalized in ("clean", "unstable", "has_hooks"):
        return ()
    if normalized == "behind":
        return (ReviewQueueBlockerType.STALE_BASE,)
    return (ReviewQueueBlockerType.MERGE_CONFLICT,)


def _check_blockers(
    check_state: ReviewQueueCheckState,
    local_validation_evidence: tuple[str, ...],
) -> tuple[ReviewQueueBlockerType, ...]:
    # Local evidence is useful context, but it never substitutes for remote
    # GitHub CI evidence on review/merge readiness.
    _ = local_validation_evidence
    if check_state is ReviewQueueCheckState.SUCCESS or check_state is ReviewQueueCheckState.NOT_REQUIRED:
        return ()
    if check_state is ReviewQueueCheckState.FAILED:
        return (ReviewQueueBlockerType.CHECKS_FAILED,)
    if check_state is ReviewQueueCheckState.PENDING:
        return (ReviewQueueBlockerType.CHECKS_PENDING,)
    return (ReviewQueueBlockerType.CHECKS_MISSING,)


def _next_owner(pull_request: ReviewQueuePullRequest, blockers: Sequence[ReviewQueueBlockerType]) -> str:
    if pull_request.repository_kind is ReviewQueueRepositoryKind.PROCESS:
        return PROCESS_REPOSITORY_OWNER
    if not blockers:
        return TARGET_REPOSITORY_OWNER
    if ReviewQueueBlockerType.DEPENDENCY_BLOCKED in blockers:
        return "Orchestrator/Product Owner"
    if ReviewQueueBlockerType.CHECKS_PENDING in blockers:
        return TARGET_REPOSITORY_OWNER
    if ReviewQueueBlockerType.UNSUPPORTED_ISSUE_TYPE in blockers:
        return "Scheduler/Orchestrator"
    return "Developer Agent"


def _checks_text(pull_request: ReviewQueuePullRequest) -> str:
    names = ", ".join(pull_request.check_names)
    return f"{pull_request.check_state.value}{': ' + names if names else ''}"


def _status_matches(status: str, allowed_statuses: Sequence[str]) -> bool:
    normalized = status.strip().lower()
    return any(normalized == allowed.strip().lower() for allowed in allowed_statuses)


def _dedupe_blockers(blockers: Sequence[ReviewQueueBlockerType]) -> tuple[ReviewQueueBlockerType, ...]:
    seen: set[ReviewQueueBlockerType] = set()
    deduped: list[ReviewQueueBlockerType] = []
    for blocker in blockers:
        if blocker not in seen:
            seen.add(blocker)
            deduped.append(blocker)
    return tuple(deduped)


def _validate_pull_request(pull_request: ReviewQueuePullRequest) -> None:
    _require_text("pull_request.repository", pull_request.repository)
    _require_text("pull_request.title", pull_request.title)
    _require_text("pull_request.url", pull_request.url)
    _require_text("pull_request.head_branch", pull_request.head_branch)
    _require_text("pull_request.base_branch", pull_request.base_branch)
    _require_text("pull_request.state", pull_request.state)
    if pull_request.number <= 0:
        raise ReviewQueueReportError("pull_request.number must be positive.")
    if not isinstance(pull_request.check_state, ReviewQueueCheckState):
        raise ReviewQueueReportError("pull_request.check_state must be ReviewQueueCheckState.")
    if not isinstance(pull_request.repository_kind, ReviewQueueRepositoryKind):
        raise ReviewQueueReportError("pull_request.repository_kind must be ReviewQueueRepositoryKind.")


def _validate_jira_issue(jira_issue: ReviewQueueJiraIssue) -> None:
    _require_text("jira_issue.key", jira_issue.key)
    _require_text("jira_issue.summary", jira_issue.summary)
    _require_text("jira_issue.issue_type", jira_issue.issue_type)
    _require_text("jira_issue.status", jira_issue.status)


def _require_text(field: str, value: str) -> None:
    if not value.strip():
        raise ReviewQueueReportError(f"{field} is required.")
