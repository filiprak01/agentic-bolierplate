from pathlib import Path
from datetime import datetime, timezone

from agentic_boilerplate.domain import (
    CleanupApprovalPolicy,
    CompletedWorktree,
    WorkspaceClosureBlockerKind,
    WorkspaceClosureCandidate,
    WorktreeCleanupAction,
    assignment_workspace_archive_record_to_dict,
    build_assignment_workspace_archive_record,
    build_workspace_closure_readiness_report,
    build_worktree_cleanup_plan,
    render_workspace_closure_readiness_report,
)
from agentic_boilerplate.storage import (
    write_assignment_workspace_archive_record,
    write_workspace_closure_readiness_report,
    write_worktree_cleanup_log,
)


def test_manual_policy_requires_explicit_approval_before_deletion() -> None:
    plan = build_worktree_cleanup_plan(
        worktrees=(
            CompletedWorktree(
                issue_key="AGENT-199",
                branch_name="feature/AGENT-199-worktree-cleanup",
                worktree_path="/tmp/agent199",
                merged_to_main=True,
                has_uncommitted_changes=False,
                evidence_paths=("data/agent-logs/AGENT-199/test-evidence.md",),
            ),
        ),
        approval_policy=CleanupApprovalPolicy.MANUAL_APPROVAL,
        archive_root="data/worktree-archive",
    )

    assert plan.decisions[0].action is WorktreeCleanupAction.ARCHIVE_ONLY
    assert plan.decisions[0].archive_entries[0].archive_path.endswith("/AGENT-199/test-evidence.md")


def test_auto_archive_then_delete_prepares_archive_entries_and_delete_action() -> None:
    plan = build_worktree_cleanup_plan(
        worktrees=(
            CompletedWorktree(
                issue_key="AGENT-200",
                branch_name="feature/AGENT-200-validator",
                worktree_path="/tmp/agent200",
                merged_to_main=True,
                has_uncommitted_changes=False,
                status_paths=("data/agent-logs/AGENT-200/status.md",),
            ),
        ),
        approval_policy=CleanupApprovalPolicy.AUTO_ARCHIVE_THEN_DELETE,
        archive_root="data/worktree-archive",
    )

    assert plan.decisions[0].action is WorktreeCleanupAction.DELETE
    assert plan.decisions[0].archive_entries[0].archive_path.endswith("/AGENT-200/status.md")


def test_uncommitted_changes_block_cleanup_and_are_logged(tmp_path: Path) -> None:
    plan = build_worktree_cleanup_plan(
        worktrees=(
            CompletedWorktree(
                issue_key="AGENT-201",
                branch_name="feature/AGENT-201-report-publication",
                worktree_path="/tmp/agent201",
                merged_to_main=True,
                has_uncommitted_changes=True,
            ),
        ),
        approval_policy=CleanupApprovalPolicy.AUTO_DELETE_CLEAN,
        archive_root="data/worktree-archive",
    )

    path = write_worktree_cleanup_log(plan, tmp_path)

    assert plan.decisions[0].action is WorktreeCleanupAction.BLOCKED
    assert "uncommitted changes" in path.read_text(encoding="utf-8")


def test_assignment_workspace_archive_record_preserves_traceability_references() -> None:
    record = build_assignment_workspace_archive_record(
        CompletedWorktree(
            issue_key="AGENT-635",
            branch_name="feature/AGENT-635-workspace-cleanup",
            worktree_path="/workspaces/AGENT/AGENT-635/developer",
            merged_to_main=True,
            has_uncommitted_changes=False,
            evidence_paths=("data/agent-logs/AGENT-635/test-evidence.md",),
            status_paths=("data/agent-state/assignment-AGENT-635.json",),
            pull_request_url="https://github.com/example-org/agentic-boilerplate/pull/170",
            jira_issue_url="https://example.atlassian.net/browse/AGENT-635",
            merge_commit_sha="abc123",
        ),
        assignment_id="assignment-AGENT-635",
        role="developer",
        cleanup_policy=CleanupApprovalPolicy.MANUAL_APPROVAL,
        archived_at="2026-08-10T05:00:00Z",
    )

    data = assignment_workspace_archive_record_to_dict(record)

    assert data["issue_key"] == "AGENT-635"
    assert data["assignment_id"] == "assignment-AGENT-635"
    assert data["pull_request_url"] == "https://github.com/example-org/agentic-boilerplate/pull/170"
    assert data["jira_issue_url"] == "https://example.atlassian.net/browse/AGENT-635"
    assert data["merge_commit_sha"] == "abc123"
    assert data["cleanup_policy"] == "manual-approval"


def test_assignment_workspace_archive_record_is_written_as_durable_json(tmp_path: Path) -> None:
    record = build_assignment_workspace_archive_record(
        CompletedWorktree(
            issue_key="AGENT-635",
            branch_name="feature/AGENT-635-workspace-cleanup",
            worktree_path="/workspaces/AGENT/AGENT-635/developer",
            merged_to_main=True,
            has_uncommitted_changes=False,
            evidence_paths=("data/agent-logs/AGENT-635/test-evidence.md",),
            pull_request_url="https://github.com/example-org/agentic-boilerplate/pull/170",
        ),
        assignment_id="assignment-AGENT-635",
        role="developer",
        cleanup_policy=CleanupApprovalPolicy.AUTO_ARCHIVE_THEN_DELETE,
        archived_at="2026-08-10T05:00:00Z",
    )

    path = write_assignment_workspace_archive_record(
        record,
        tmp_path,
        created_at=datetime(2026, 8, 10, 5, 0, 0, tzinfo=timezone.utc),
    )

    text = path.read_text(encoding="utf-8")
    assert path.name == "workspace-archive-20260810T050000Z.json"
    assert path.parent.name == "AGENT-635"
    assert '"issue_key": "AGENT-635"' in text
    assert '"cleanup_policy": "auto-archive-then-delete"' in text


def test_unpushed_branch_blocks_cleanup_even_when_worktree_is_clean() -> None:
    plan = build_worktree_cleanup_plan(
        worktrees=(
            CompletedWorktree(
                issue_key="AGENT-636",
                branch_name="feature/AGENT-636-unpushed",
                worktree_path="/tmp/agent636",
                merged_to_main=True,
                has_uncommitted_changes=False,
                pushed_to_remote=False,
            ),
        ),
        approval_policy=CleanupApprovalPolicy.AUTO_DELETE_CLEAN,
        archive_root="data/worktree-archive",
    )

    assert plan.decisions[0].action is WorktreeCleanupAction.BLOCKED
    assert "not been pushed" in plan.decisions[0].reason


def test_workspace_closure_readiness_blocks_dirty_unpushed_unarchived_and_stale_workspaces() -> None:
    report = build_workspace_closure_readiness_report(
        candidates=(
            WorkspaceClosureCandidate(
                issue_key="AGENT-637",
                assignment_id="assignment-AGENT-637",
                role="developer",
                workspace_path="/workspaces/AGENT/AGENT-637/developer",
                branch_name="feature/AGENT-637-dirty",
                assignment_status="in_progress",
                merged_to_main=False,
                has_uncommitted_changes=True,
                pushed_to_remote=True,
                archived=False,
                updated_at="2026-08-10T04:00:00Z",
            ),
            WorkspaceClosureCandidate(
                issue_key="AGENT-638",
                assignment_id="assignment-AGENT-638",
                role="developer",
                workspace_path="/workspaces/AGENT/AGENT-638/developer",
                branch_name="feature/AGENT-638-unpushed",
                assignment_status="in_progress",
                merged_to_main=False,
                has_uncommitted_changes=False,
                pushed_to_remote=False,
                archived=False,
                updated_at="2026-08-10T04:00:00Z",
            ),
            WorkspaceClosureCandidate(
                issue_key="AGENT-639",
                assignment_id="assignment-AGENT-639",
                role="developer",
                workspace_path="/workspaces/AGENT/AGENT-639/developer",
                branch_name="feature/AGENT-639-unarchived",
                assignment_status="TEST COMPLETED",
                merged_to_main=True,
                has_uncommitted_changes=False,
                pushed_to_remote=True,
                archived=False,
                updated_at="2026-08-10T04:55:00Z",
            ),
            WorkspaceClosureCandidate(
                issue_key="AGENT-640",
                assignment_id="assignment-AGENT-640",
                role="developer",
                workspace_path="/workspaces/AGENT/AGENT-640/developer",
                branch_name="feature/AGENT-640-stale",
                assignment_status="in_progress",
                merged_to_main=False,
                has_uncommitted_changes=False,
                pushed_to_remote=True,
                archived=False,
                updated_at="2026-08-10T03:00:00Z",
            ),
        ),
        checked_at="2026-08-10T05:00:00Z",
        stale_after_seconds=1800,
    )

    assert not report.can_close
    assert {blocker.kind for blocker in report.blockers} == {
        WorkspaceClosureBlockerKind.DIRTY_WORKSPACE,
        WorkspaceClosureBlockerKind.UNPUSHED_BRANCH,
        WorkspaceClosureBlockerKind.UNARCHIVED_COMPLETED_WORKSPACE,
        WorkspaceClosureBlockerKind.STALE_ACTIVE_WORKSPACE,
    }
    rendered = render_workspace_closure_readiness_report(report)
    assert "Can close: no" in rendered
    assert "stale-active-workspace" in rendered


def test_workspace_closure_readiness_report_is_written_as_markdown_and_json(tmp_path: Path) -> None:
    report = build_workspace_closure_readiness_report(
        candidates=(
            WorkspaceClosureCandidate(
                issue_key="AGENT-641",
                assignment_id="assignment-AGENT-641",
                role="developer",
                workspace_path="/workspaces/AGENT/AGENT-641/developer",
                branch_name="feature/AGENT-641-clean",
                assignment_status="ACCEPTED/DONE",
                merged_to_main=True,
                has_uncommitted_changes=False,
                pushed_to_remote=True,
                archived=True,
                updated_at="2026-08-10T04:55:00Z",
            ),
        ),
        checked_at="2026-08-10T05:00:00Z",
        stale_after_seconds=1800,
    )

    markdown_path, json_path = write_workspace_closure_readiness_report(
        report,
        tmp_path,
        created_at=datetime(2026, 8, 10, 5, 0, 0, tzinfo=timezone.utc),
    )

    assert markdown_path.name == "workspace-closure-readiness-20260810T050000Z.md"
    assert json_path.name == "workspace-closure-readiness-20260810T050000Z.json"
    assert "Can close: yes" in markdown_path.read_text(encoding="utf-8")
    assert '"can_close": true' in json_path.read_text(encoding="utf-8")


def test_workspace_closure_readiness_allows_archived_clean_completed_workspaces() -> None:
    report = build_workspace_closure_readiness_report(
        candidates=(
            WorkspaceClosureCandidate(
                issue_key="AGENT-641",
                assignment_id="assignment-AGENT-641",
                role="developer",
                workspace_path="/workspaces/AGENT/AGENT-641/developer",
                branch_name="feature/AGENT-641-clean",
                assignment_status="ACCEPTED/DONE",
                merged_to_main=True,
                has_uncommitted_changes=False,
                pushed_to_remote=True,
                archived=True,
                updated_at="2026-08-10T04:55:00Z",
            ),
        ),
        checked_at="2026-08-10T05:00:00Z",
        stale_after_seconds=1800,
    )

    assert report.can_close
    assert report.blockers == ()
