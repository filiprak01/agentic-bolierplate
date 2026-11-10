"""Durable worktree cleanup logs and archive reports."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from agentic_boilerplate.domain.worktree_cleanup import (
    AssignmentWorkspaceArchiveRecord,
    WorktreeCleanupPlan,
    WorkspaceClosureReadinessReport,
    assignment_workspace_archive_record_to_dict,
    render_workspace_closure_readiness_report,
    render_worktree_cleanup_log,
    workspace_closure_readiness_report_to_dict,
)


def write_worktree_cleanup_log(
    plan: WorktreeCleanupPlan,
    directory: Path,
    *,
    created_at: datetime | None = None,
) -> Path:
    """Persist a cleanup log and return its path."""

    timestamp = _timestamp(created_at)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"worktree-cleanup-{timestamp}.md"
    path.write_text(render_worktree_cleanup_log(plan), encoding="utf-8")
    return path


def write_assignment_workspace_archive_record(
    record: AssignmentWorkspaceArchiveRecord,
    directory: Path,
    *,
    created_at: datetime | None = None,
) -> Path:
    """Persist a completed assignment workspace archive record as JSON."""

    timestamp = _timestamp(created_at)
    issue_directory = directory / record.issue_key
    issue_directory.mkdir(parents=True, exist_ok=True)
    path = issue_directory / f"workspace-archive-{timestamp}.json"
    path.write_text(
        json.dumps(assignment_workspace_archive_record_to_dict(record), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def write_workspace_closure_readiness_report(
    report: WorkspaceClosureReadinessReport,
    directory: Path,
    *,
    created_at: datetime | None = None,
) -> tuple[Path, Path]:
    """Persist a Release Manager workspace closure report as Markdown and JSON."""

    timestamp = _timestamp(created_at)
    directory.mkdir(parents=True, exist_ok=True)
    markdown_path = directory / f"workspace-closure-readiness-{timestamp}.md"
    json_path = directory / f"workspace-closure-readiness-{timestamp}.json"
    markdown_path.write_text(render_workspace_closure_readiness_report(report), encoding="utf-8")
    json_path.write_text(
        json.dumps(workspace_closure_readiness_report_to_dict(report), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return markdown_path, json_path


def _timestamp(created_at: datetime | None = None) -> str:
    return (created_at or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
