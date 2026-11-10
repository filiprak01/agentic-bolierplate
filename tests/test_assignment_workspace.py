from dataclasses import replace
from pathlib import Path

from agentic_boilerplate.domain import (
    AgentAssignment,
    AgentRole,
    AssignmentPaths,
    AssignmentStatus,
    SharedDurablePath,
    WorkspaceProvisioningIssueKind,
    WorkspaceProvisioningMode,
    assignment_with_workspace_path,
    assignment_workspace_plan_to_dict,
    build_assignment_workspace_plan,
    default_shared_durable_paths_from_mapping,
    render_assignment_workspace_plan,
)


def test_assignment_workspace_plan_allocates_unique_isolated_path(tmp_path: Path) -> None:
    repo_root = _git_repo_root(tmp_path)
    durable_paths = _durable_paths(tmp_path)

    first = build_assignment_workspace_plan(
        _assignment("AGENT-634", repo_root=repo_root),
        workspaces_root=str(tmp_path / "agent-workspaces"),
        durable_paths=durable_paths,
    )
    second = build_assignment_workspace_plan(
        _assignment("AGENT-635", repo_root=repo_root),
        workspaces_root=str(tmp_path / "agent-workspaces"),
        durable_paths=durable_paths,
    )

    assert first.can_provision
    assert second.can_provision
    assert first.workspace_path.endswith("/AGENT/AGENT-634/developer")
    assert second.workspace_path.endswith("/AGENT/AGENT-635/developer")
    assert first.workspace_path != second.workspace_path
    assert first.commands[0].label == "fetch-base"
    assert first.commands[1].label == "create-worktree"


def test_assignment_workspace_plan_records_shared_durable_paths_and_assignment_path(tmp_path: Path) -> None:
    repo_root = _git_repo_root(tmp_path)
    assignment = _assignment("AGENT-634", repo_root=repo_root)

    plan = build_assignment_workspace_plan(
        assignment,
        workspaces_root=str(tmp_path / "agent-workspaces"),
        durable_paths=_durable_paths(tmp_path),
    )
    updated = assignment_with_workspace_path(assignment, plan)
    data = assignment_workspace_plan_to_dict(plan)

    assert plan.can_provision
    assert updated.paths.workspace_path == plan.workspace_path
    assert data["can_provision"] is True
    assert {path.name for path in plan.shared_durable_paths} >= {
        "po-inbox",
        "agent-logs",
        "agent-state",
        "codex-limits",
        "codex-jobs",
        "codex-results",
        "context-packs",
    }
    rendered = render_assignment_workspace_plan(plan)
    assert "Can provision: yes" in rendered
    assert "Shared durable paths:" in rendered


def test_assignment_workspace_plan_fails_safely_when_repo_or_credentials_missing(tmp_path: Path) -> None:
    plan = build_assignment_workspace_plan(
        _assignment("AGENT-634", repo_root=tmp_path / "missing-repo"),
        workspaces_root=str(tmp_path / "agent-workspaces"),
        durable_paths=_durable_paths(tmp_path),
        credentials_available=False,
    )

    assert not plan.can_provision
    assert plan.commands == ()
    assert {issue.kind for issue in plan.issues} >= {
        WorkspaceProvisioningIssueKind.MISSING_TARGET_REPO_ROOT,
        WorkspaceProvisioningIssueKind.MISSING_GIT_CREDENTIALS,
    }


def test_assignment_workspace_plan_rejects_branch_issue_mismatch(tmp_path: Path) -> None:
    repo_root = _git_repo_root(tmp_path)
    assignment = replace(
        _assignment("AGENT-634", repo_root=repo_root),
        branch_name="feature/AGENT-999-wrong-story",
    )

    plan = build_assignment_workspace_plan(
        assignment,
        workspaces_root=str(tmp_path / "agent-workspaces"),
        durable_paths=_durable_paths(tmp_path),
    )

    assert not plan.can_provision
    assert WorkspaceProvisioningIssueKind.BRANCH_ISSUE_MISMATCH in {issue.kind for issue in plan.issues}


def test_assignment_workspace_plan_rejects_durable_paths_inside_assignment_workspace(tmp_path: Path) -> None:
    repo_root = _git_repo_root(tmp_path)
    workspace_path = tmp_path / "agent-workspaces" / "AGENT" / "AGENT-634" / "developer"
    assignment = replace(
        _assignment("AGENT-634", repo_root=repo_root),
        paths=replace(_assignment("AGENT-634", repo_root=repo_root).paths, workspace_path=str(workspace_path)),
    )
    durable_paths = (
        SharedDurablePath(name="po-inbox", path=str(workspace_path / "data" / "po-inbox")),
        *_durable_paths(tmp_path)[1:],
    )

    plan = build_assignment_workspace_plan(
        assignment,
        workspaces_root=str(tmp_path / "agent-workspaces"),
        durable_paths=durable_paths,
    )

    assert not plan.can_provision
    assert WorkspaceProvisioningIssueKind.DURABLE_PATH_INSIDE_WORKSPACE in {issue.kind for issue in plan.issues}


def test_copied_snapshot_mode_does_not_require_branch_or_credentials(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    assignment = replace(
        _assignment("AGENT-700", repo_root=source),
        branch_name="",
        repository="",
    )

    plan = build_assignment_workspace_plan(
        assignment,
        workspaces_root=str(tmp_path / "agent-workspaces"),
        durable_paths=_durable_paths(tmp_path),
        mode=WorkspaceProvisioningMode.COPIED_SNAPSHOT,
        credentials_available=False,
    )

    assert plan.can_provision
    assert plan.commands[0].label == "copy-snapshot"


def test_default_shared_durable_paths_from_mapping_uses_env_overrides() -> None:
    paths = default_shared_durable_paths_from_mapping(
        {
            "DURABLE_PO_INBOX_PATH": "/durable/inbox",
            "DURABLE_AGENT_LOGS_PATH": "/durable/logs",
        }
    )

    by_name = {path.name: path.path for path in paths}
    assert by_name["po-inbox"] == "/durable/inbox"
    assert by_name["agent-logs"] == "/durable/logs"
    assert by_name["codex-limits"] == "data/codex-limits"


def _assignment(issue_key: str, *, repo_root: Path) -> AgentAssignment:
    return AgentAssignment(
        id=f"assignment-{issue_key}",
        jira_issue_key=issue_key,
        role=AgentRole.DEVELOPER,
        status=AssignmentStatus.QUEUED,
        paths=AssignmentPaths(
            context_pack_path=f"data/context-packs/{issue_key}/context.json",
            codex_job_path=f"data/codex-jobs/{issue_key}/job.json",
            output_path=f"data/codex-results/{issue_key}/result.json",
        ),
        branch_name=f"feature/{issue_key}-isolated-workspace",
        project_id="agentic-boilerplate",
        project_name="Agentic Boilerplate",
        project_root=str(repo_root),
        repository="example-org/agentic-boilerplate",
        jira_project_key="AGENT",
        created_at="2026-08-10T04:30:00Z",
        updated_at="2026-08-10T04:30:00Z",
    )


def _git_repo_root(tmp_path: Path) -> Path:
    repo_root = tmp_path / "target-repo"
    repo_root.mkdir(exist_ok=True)
    (repo_root / ".git").mkdir(exist_ok=True)
    return repo_root


def _durable_paths(tmp_path: Path) -> tuple[SharedDurablePath, ...]:
    root = tmp_path / "durable"
    return (
        SharedDurablePath(name="po-inbox", path=str(root / "po-inbox")),
        SharedDurablePath(name="agent-logs", path=str(root / "agent-logs")),
        SharedDurablePath(name="agent-state", path=str(root / "agent-state")),
        SharedDurablePath(name="codex-limits", path=str(root / "codex-limits")),
        SharedDurablePath(name="codex-jobs", path=str(root / "codex-jobs")),
        SharedDurablePath(name="codex-results", path=str(root / "codex-results")),
        SharedDurablePath(name="context-packs", path=str(root / "context-packs")),
    )
