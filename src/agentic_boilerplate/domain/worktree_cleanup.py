"""Safe cleanup planning for completed feature worktrees."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path


class CleanupApprovalPolicy(str, Enum):
    """Policy controlling whether clean worktrees may be deleted."""

    MANUAL_APPROVAL = "manual-approval"
    AUTO_DELETE_CLEAN = "auto-delete-clean"
    AUTO_ARCHIVE_THEN_DELETE = "auto-archive-then-delete"


class WorktreeCleanupAction(str, Enum):
    """Cleanup outcome for one completed worktree."""

    KEEP = "keep"
    ARCHIVE_ONLY = "archive-only"
    DELETE = "delete"
    BLOCKED = "blocked"


class WorkspaceClosureBlockerKind(str, Enum):
    """Reason a sprint or release cannot close workspace cleanup yet."""

    DIRTY_WORKSPACE = "dirty-workspace"
    UNPUSHED_BRANCH = "unpushed-branch"
    UNARCHIVED_COMPLETED_WORKSPACE = "unarchived-completed-workspace"
    STALE_ACTIVE_WORKSPACE = "stale-active-workspace"


@dataclass(frozen=True)
class CompletedWorktree:
    """One completed feature worktree candidate."""

    issue_key: str
    branch_name: str
    worktree_path: str
    merged_to_main: bool
    has_uncommitted_changes: bool
    pushed_to_remote: bool = True
    evidence_paths: tuple[str, ...] = ()
    status_paths: tuple[str, ...] = ()
    pull_request_url: str = ""
    jira_issue_url: str = ""
    merge_commit_sha: str = ""
    archived_metadata_path: str = ""


@dataclass(frozen=True)
class WorktreeArchiveEntry:
    """Archive copy plan for one durable evidence or status file."""

    source_path: str
    archive_path: str


@dataclass(frozen=True)
class WorktreeCleanupDecision:
    """Cleanup decision for one worktree."""

    issue_key: str
    branch_name: str
    action: WorktreeCleanupAction
    reason: str
    archive_entries: tuple[WorktreeArchiveEntry, ...] = ()


@dataclass(frozen=True)
class WorktreeCleanupPlan:
    """Batch cleanup plan for completed worktrees."""

    approval_policy: CleanupApprovalPolicy
    decisions: tuple[WorktreeCleanupDecision, ...]


@dataclass(frozen=True)
class AssignmentWorkspaceArchiveRecord:
    """Durable archive metadata for one completed assignment workspace."""

    issue_key: str
    assignment_id: str
    role: str
    workspace_path: str
    branch_name: str
    pull_request_url: str
    jira_issue_url: str
    merge_commit_sha: str
    evidence_paths: tuple[str, ...]
    status_paths: tuple[str, ...]
    cleanup_policy: CleanupApprovalPolicy
    archived_at: str


@dataclass(frozen=True)
class WorkspaceClosureCandidate:
    """One workspace inspected before sprint or release closure."""

    issue_key: str
    assignment_id: str
    role: str
    workspace_path: str
    branch_name: str
    assignment_status: str
    merged_to_main: bool
    has_uncommitted_changes: bool
    pushed_to_remote: bool
    archived: bool
    updated_at: str


@dataclass(frozen=True)
class WorkspaceClosureBlocker:
    """One blocker preventing Release Manager workspace closure."""

    issue_key: str
    workspace_path: str
    kind: WorkspaceClosureBlockerKind
    message: str


@dataclass(frozen=True)
class WorkspaceClosureReadinessReport:
    """Release Manager report for active/completed assignment workspaces."""

    checked_at: str
    stale_after_seconds: int
    candidates: tuple[WorkspaceClosureCandidate, ...]
    blockers: tuple[WorkspaceClosureBlocker, ...]

    @property
    def can_close(self) -> bool:
        return not self.blockers


@dataclass(frozen=True)
class WorktreeCleanupIssue:
    """Validation issue for worktree cleanup input."""

    field: str
    message: str


class WorktreeCleanupError(ValueError):
    """Raised when cleanup input is incomplete."""

    def __init__(self, issues: Sequence[WorktreeCleanupIssue]) -> None:
        self.issues = tuple(issues)
        super().__init__(format_worktree_cleanup_issues(self.issues))


def build_worktree_cleanup_plan(
    *,
    worktrees: tuple[CompletedWorktree, ...],
    approval_policy: CleanupApprovalPolicy,
    archive_root: str,
    explicit_delete_approvals: tuple[str, ...] = (),
) -> WorktreeCleanupPlan:
    """Build a safe cleanup plan without deleting anything."""

    _require_text("archive_root", archive_root)
    if not worktrees:
        raise WorktreeCleanupError((WorktreeCleanupIssue("worktrees", "At least one worktree is required."),))
    approved = {key.strip() for key in explicit_delete_approvals if key.strip()}
    decisions = tuple(
        _decide_worktree_cleanup(
            worktree,
            approval_policy=approval_policy,
            archive_root=archive_root,
            explicit_delete_approved=worktree.issue_key in approved,
        )
        for worktree in worktrees
    )
    return WorktreeCleanupPlan(approval_policy=approval_policy, decisions=decisions)


def render_worktree_cleanup_log(plan: WorktreeCleanupPlan) -> str:
    """Render a durable markdown-friendly cleanup log."""

    lines = [f"Cleanup policy: {plan.approval_policy.value}", "", "Decisions:"]
    for decision in plan.decisions:
        lines.append(f"- {decision.issue_key} ({decision.branch_name}): {decision.action.value} - {decision.reason}")
        for entry in decision.archive_entries:
            lines.append(f"  - archive {entry.source_path} -> {entry.archive_path}")
    return "\n".join(lines).strip()


def build_assignment_workspace_archive_record(
    worktree: CompletedWorktree,
    *,
    assignment_id: str,
    role: str,
    cleanup_policy: CleanupApprovalPolicy,
    archived_at: str,
) -> AssignmentWorkspaceArchiveRecord:
    """Create durable archive metadata for a completed assignment workspace."""

    _require_text("assignment_id", assignment_id)
    _require_text("role", role)
    _require_text("archived_at", archived_at)
    _require_text("issue_key", worktree.issue_key)
    _require_text("branch_name", worktree.branch_name)
    _require_text("worktree_path", worktree.worktree_path)
    return AssignmentWorkspaceArchiveRecord(
        issue_key=worktree.issue_key.strip(),
        assignment_id=assignment_id.strip(),
        role=role.strip(),
        workspace_path=worktree.worktree_path.strip(),
        branch_name=worktree.branch_name.strip(),
        pull_request_url=worktree.pull_request_url.strip(),
        jira_issue_url=worktree.jira_issue_url.strip(),
        merge_commit_sha=worktree.merge_commit_sha.strip(),
        evidence_paths=tuple(path.strip() for path in worktree.evidence_paths if path.strip()),
        status_paths=tuple(path.strip() for path in worktree.status_paths if path.strip()),
        cleanup_policy=cleanup_policy,
        archived_at=archived_at.strip(),
    )


def assignment_workspace_archive_record_to_dict(
    record: AssignmentWorkspaceArchiveRecord,
) -> dict[str, object]:
    """Convert workspace archive metadata into JSON-compatible data."""

    return {
        "issue_key": record.issue_key,
        "assignment_id": record.assignment_id,
        "role": record.role,
        "workspace_path": record.workspace_path,
        "branch_name": record.branch_name,
        "pull_request_url": record.pull_request_url,
        "jira_issue_url": record.jira_issue_url,
        "merge_commit_sha": record.merge_commit_sha,
        "evidence_paths": list(record.evidence_paths),
        "status_paths": list(record.status_paths),
        "cleanup_policy": record.cleanup_policy.value,
        "archived_at": record.archived_at,
    }


def build_workspace_closure_readiness_report(
    *,
    candidates: tuple[WorkspaceClosureCandidate, ...],
    checked_at: str,
    stale_after_seconds: int,
) -> WorkspaceClosureReadinessReport:
    """Build a Release Manager closure report for assignment workspaces."""

    _require_text("checked_at", checked_at)
    if stale_after_seconds < 0:
        raise WorktreeCleanupError(
            (WorktreeCleanupIssue("stale_after_seconds", "Stale threshold cannot be negative."),)
        )
    blockers: list[WorkspaceClosureBlocker] = []
    checked_at_dt = _parse_timestamp(checked_at)
    for candidate in candidates:
        _require_text("issue_key", candidate.issue_key)
        _require_text("workspace_path", candidate.workspace_path)
        if candidate.has_uncommitted_changes:
            blockers.append(
                WorkspaceClosureBlocker(
                    issue_key=candidate.issue_key,
                    workspace_path=candidate.workspace_path,
                    kind=WorkspaceClosureBlockerKind.DIRTY_WORKSPACE,
                    message="Workspace has uncommitted changes.",
                )
            )
        if not candidate.pushed_to_remote:
            blockers.append(
                WorkspaceClosureBlocker(
                    issue_key=candidate.issue_key,
                    workspace_path=candidate.workspace_path,
                    kind=WorkspaceClosureBlockerKind.UNPUSHED_BRANCH,
                    message="Workspace branch has not been pushed to remote.",
                )
            )
        if _is_completed_status(candidate.assignment_status) and not candidate.archived:
            blockers.append(
                WorkspaceClosureBlocker(
                    issue_key=candidate.issue_key,
                    workspace_path=candidate.workspace_path,
                    kind=WorkspaceClosureBlockerKind.UNARCHIVED_COMPLETED_WORKSPACE,
                    message="Completed workspace must be archived before sprint or release closure.",
                )
            )
        if (
            not _is_completed_status(candidate.assignment_status)
            and stale_after_seconds
            and _is_stale(candidate.updated_at, checked_at_dt, stale_after_seconds)
        ):
            blockers.append(
                WorkspaceClosureBlocker(
                    issue_key=candidate.issue_key,
                    workspace_path=candidate.workspace_path,
                    kind=WorkspaceClosureBlockerKind.STALE_ACTIVE_WORKSPACE,
                    message="Active workspace exceeded the stale threshold.",
                )
            )
    return WorkspaceClosureReadinessReport(
        checked_at=checked_at.strip(),
        stale_after_seconds=stale_after_seconds,
        candidates=candidates,
        blockers=tuple(blockers),
    )


def render_workspace_closure_readiness_report(report: WorkspaceClosureReadinessReport) -> str:
    """Render a Markdown closure checklist for Release Manager evidence."""

    lines = [
        f"Checked at: {report.checked_at}",
        f"Stale threshold seconds: {report.stale_after_seconds}",
        f"Can close: {'yes' if report.can_close else 'no'}",
        "",
        "Workspaces:",
    ]
    for candidate in report.candidates:
        lines.append(
            "- "
            f"{candidate.issue_key} ({candidate.role}) {candidate.assignment_status} "
            f"archived={str(candidate.archived).lower()} path={candidate.workspace_path}"
        )
    if report.blockers:
        lines.extend(["", "Blockers:"])
        for blocker in report.blockers:
            lines.append(f"- {blocker.issue_key}: {blocker.kind.value} - {blocker.message}")
    return "\n".join(lines).strip()


def workspace_closure_readiness_report_to_dict(
    report: WorkspaceClosureReadinessReport,
) -> dict[str, object]:
    """Convert a workspace closure report into JSON-compatible data."""

    return {
        "checked_at": report.checked_at,
        "stale_after_seconds": report.stale_after_seconds,
        "can_close": report.can_close,
        "candidates": [
            {
                "issue_key": candidate.issue_key,
                "assignment_id": candidate.assignment_id,
                "role": candidate.role,
                "workspace_path": candidate.workspace_path,
                "branch_name": candidate.branch_name,
                "assignment_status": candidate.assignment_status,
                "merged_to_main": candidate.merged_to_main,
                "has_uncommitted_changes": candidate.has_uncommitted_changes,
                "pushed_to_remote": candidate.pushed_to_remote,
                "archived": candidate.archived,
                "updated_at": candidate.updated_at,
            }
            for candidate in report.candidates
        ],
        "blockers": [
            {
                "issue_key": blocker.issue_key,
                "workspace_path": blocker.workspace_path,
                "kind": blocker.kind.value,
                "message": blocker.message,
            }
            for blocker in report.blockers
        ],
    }


def format_worktree_cleanup_issues(issues: Sequence[WorktreeCleanupIssue]) -> str:
    return "; ".join(f"{issue.field}: {issue.message}" for issue in issues)


def _decide_worktree_cleanup(
    worktree: CompletedWorktree,
    *,
    approval_policy: CleanupApprovalPolicy,
    archive_root: str,
    explicit_delete_approved: bool,
) -> WorktreeCleanupDecision:
    _require_text("issue_key", worktree.issue_key)
    _require_text("branch_name", worktree.branch_name)
    _require_text("worktree_path", worktree.worktree_path)

    if not worktree.merged_to_main:
        return WorktreeCleanupDecision(
            issue_key=worktree.issue_key,
            branch_name=worktree.branch_name,
            action=WorktreeCleanupAction.KEEP,
            reason="Branch is not merged to main.",
        )
    if worktree.has_uncommitted_changes:
        return WorktreeCleanupDecision(
            issue_key=worktree.issue_key,
            branch_name=worktree.branch_name,
            action=WorktreeCleanupAction.BLOCKED,
            reason="Worktree has uncommitted changes and requires manual review.",
        )
    if not worktree.pushed_to_remote:
        return WorktreeCleanupDecision(
            issue_key=worktree.issue_key,
            branch_name=worktree.branch_name,
            action=WorktreeCleanupAction.BLOCKED,
            reason="Worktree branch has not been pushed to remote.",
        )

    archive_entries = _archive_entries(worktree, archive_root)
    if approval_policy is CleanupApprovalPolicy.MANUAL_APPROVAL and not explicit_delete_approved:
        action = WorktreeCleanupAction.ARCHIVE_ONLY if archive_entries else WorktreeCleanupAction.KEEP
        reason = "Explicit approval is required before deleting a completed worktree."
        return WorktreeCleanupDecision(
            issue_key=worktree.issue_key,
            branch_name=worktree.branch_name,
            action=action,
            reason=reason,
            archive_entries=archive_entries,
        )
    if approval_policy is CleanupApprovalPolicy.AUTO_ARCHIVE_THEN_DELETE:
        return WorktreeCleanupDecision(
            issue_key=worktree.issue_key,
            branch_name=worktree.branch_name,
            action=WorktreeCleanupAction.DELETE,
            reason="Merged worktree is clean and archive-before-delete policy is enabled.",
            archive_entries=archive_entries,
        )
    return WorktreeCleanupDecision(
        issue_key=worktree.issue_key,
        branch_name=worktree.branch_name,
        action=WorktreeCleanupAction.DELETE,
        reason="Merged worktree is clean and cleanup policy allows deletion.",
        archive_entries=archive_entries,
    )


def _archive_entries(worktree: CompletedWorktree, archive_root: str) -> tuple[WorktreeArchiveEntry, ...]:
    entries: list[WorktreeArchiveEntry] = []
    for source_path in (*worktree.status_paths, *worktree.evidence_paths):
        normalized = source_path.strip()
        if not normalized:
            continue
        filename = Path(normalized).name
        archive_path = str(Path(archive_root) / worktree.issue_key / filename)
        entries.append(WorktreeArchiveEntry(source_path=normalized, archive_path=archive_path))
    return tuple(entries)


def _require_text(field: str, value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise WorktreeCleanupError((WorktreeCleanupIssue(field, "Value is required."),))
    return normalized


def _is_completed_status(status: str) -> bool:
    normalized = status.strip().lower().replace("_", " ")
    return normalized in {
        "completed",
        "test completed",
        "accepted/done",
        "accepted done",
        "done",
    }


def _is_stale(updated_at: str, checked_at: datetime, stale_after_seconds: int) -> bool:
    updated = _parse_timestamp(updated_at)
    return (checked_at - updated).total_seconds() > stale_after_seconds


def _parse_timestamp(value: str) -> datetime:
    normalized = value.strip()
    if not normalized:
        raise WorktreeCleanupError((WorktreeCleanupIssue("timestamp", "Timestamp value is required."),))
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
