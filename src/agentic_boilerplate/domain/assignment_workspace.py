"""Isolated workspace provisioning plans for agent assignments."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path

from agentic_boilerplate.domain.agent_assignment import AgentAssignment
from agentic_boilerplate.domain.po_inbox import AgentRole

FEATURE_BRANCH_PATTERN = re.compile(r"^feature/(?P<issue>[A-Z][A-Z0-9]+-\d+)-[a-z0-9][a-z0-9-]*$")
SAFE_PATH_COMPONENT_PATTERN = re.compile(r"[^A-Za-z0-9_.-]+")

REQUIRED_SHARED_DURABLE_PATH_NAMES: tuple[str, ...] = (
    "po-inbox",
    "agent-logs",
    "agent-state",
    "codex-limits",
    "codex-jobs",
    "codex-results",
    "context-packs",
)


class WorkspaceProvisioningMode(str, Enum):
    """Supported assignment workspace creation strategies."""

    GIT_WORKTREE = "git-worktree"
    FRESH_CLONE = "fresh-clone"
    COPIED_SNAPSHOT = "copied-snapshot"


class WorkspaceProvisioningIssueKind(str, Enum):
    """Validation issue kind for workspace provisioning."""

    MISSING_ASSIGNMENT_ID = "missing-assignment-id"
    MISSING_JIRA_ISSUE_KEY = "missing-jira-issue-key"
    MISSING_PROJECT_KEY = "missing-project-key"
    MISSING_WORKSPACES_ROOT = "missing-workspaces-root"
    MISSING_TARGET_REPO_ROOT = "missing-target-repo-root"
    MISSING_TARGET_GIT_METADATA = "missing-target-git-metadata"
    MISSING_REPOSITORY = "missing-repository"
    MISSING_GIT_CREDENTIALS = "missing-git-credentials"
    MISSING_BRANCH_NAME = "missing-branch-name"
    INVALID_BRANCH_NAME = "invalid-branch-name"
    BRANCH_ISSUE_MISMATCH = "branch-issue-mismatch"
    WORKSPACE_REUSES_SOURCE = "workspace-reuses-source"
    DURABLE_PATH_INSIDE_WORKSPACE = "durable-path-inside-workspace"
    MISSING_DURABLE_PATH = "missing-durable-path"
    UNSUPPORTED_ROLE = "unsupported-role"


@dataclass(frozen=True)
class SharedDurablePath:
    """One shared durable coordination path mounted outside mutable source code."""

    name: str
    path: str


@dataclass(frozen=True)
class WorkspaceProvisioningIssue:
    """A safe-failure reason for workspace provisioning."""

    kind: WorkspaceProvisioningIssueKind
    field: str
    message: str


@dataclass(frozen=True)
class WorkspaceProvisioningCommand:
    """One operator or worker command needed to create an isolated workspace."""

    label: str
    command: str


@dataclass(frozen=True)
class AssignmentWorkspacePlan:
    """Validated workspace plan for one agent assignment."""

    assignment_id: str
    jira_issue_key: str
    role: AgentRole
    mode: WorkspaceProvisioningMode
    workspace_path: str
    source_repo_root: str
    repository: str
    branch_name: str
    base_branch: str
    shared_durable_paths: tuple[SharedDurablePath, ...]
    commands: tuple[WorkspaceProvisioningCommand, ...]
    issues: tuple[WorkspaceProvisioningIssue, ...] = ()

    @property
    def can_provision(self) -> bool:
        """Return true when the plan can be executed without unresolved blockers."""

        return not self.issues


def build_assignment_workspace_plan(
    assignment: AgentAssignment,
    *,
    workspaces_root: str,
    durable_paths: tuple[SharedDurablePath, ...],
    mode: WorkspaceProvisioningMode = WorkspaceProvisioningMode.GIT_WORKTREE,
    base_branch: str = "main",
    credentials_available: bool = True,
    require_existing_source: bool = True,
) -> AssignmentWorkspacePlan:
    """Build a non-destructive workspace provisioning plan for an assignment."""

    assignment_id = assignment.id.strip()
    jira_issue_key = assignment.jira_issue_key.strip()
    project_key = (assignment.jira_project_key.strip() or _project_key_from_issue(jira_issue_key)).strip()
    branch_name = assignment.branch_name.strip()
    source_repo_root = assignment.project_root.strip()
    repository = assignment.repository.strip()
    workspace_path = assignment.paths.workspace_path.strip() or _default_workspace_path(
        workspaces_root=workspaces_root,
        project_key=project_key,
        jira_issue_key=jira_issue_key,
        role=assignment.role,
    )
    plan = AssignmentWorkspacePlan(
        assignment_id=assignment_id,
        jira_issue_key=jira_issue_key,
        role=assignment.role,
        mode=mode,
        workspace_path=workspace_path,
        source_repo_root=source_repo_root,
        repository=repository,
        branch_name=branch_name,
        base_branch=base_branch.strip() or "main",
        shared_durable_paths=_normalize_durable_paths(durable_paths),
        commands=(),
        issues=(),
    )

    issues = _validate_workspace_plan(
        plan,
        workspaces_root=workspaces_root,
        project_key=project_key,
        credentials_available=credentials_available,
        require_existing_source=require_existing_source,
    )
    commands = () if issues else _build_provisioning_commands(plan)
    return replace(plan, commands=commands, issues=issues)


def assignment_with_workspace_path(
    assignment: AgentAssignment,
    plan: AssignmentWorkspacePlan,
) -> AgentAssignment:
    """Return an assignment copy whose durable paths include the workspace path."""

    return replace(assignment, paths=replace(assignment.paths, workspace_path=plan.workspace_path))


def render_assignment_workspace_plan(plan: AssignmentWorkspacePlan) -> str:
    """Render a Markdown-friendly provisioning plan for evidence or operator review."""

    lines = [
        f"Assignment: {plan.assignment_id}",
        f"Jira issue: {plan.jira_issue_key}",
        f"Role: {plan.role.value}",
        f"Mode: {plan.mode.value}",
        f"Workspace: {plan.workspace_path}",
        f"Source repo root: {plan.source_repo_root or 'n/a'}",
        f"Repository: {plan.repository or 'n/a'}",
        f"Branch: {plan.branch_name or 'n/a'}",
        f"Base branch: {plan.base_branch}",
        f"Can provision: {'yes' if plan.can_provision else 'no'}",
        "",
        "Shared durable paths:",
    ]
    lines.extend(f"- {path.name}: {path.path}" for path in plan.shared_durable_paths)
    if plan.issues:
        lines.extend(["", "Issues:"])
        lines.extend(f"- {issue.kind.value} ({issue.field}): {issue.message}" for issue in plan.issues)
    if plan.commands:
        lines.extend(["", "Commands:"])
        lines.extend(f"- {command.label}: `{command.command}`" for command in plan.commands)
    return "\n".join(lines).strip()


def assignment_workspace_plan_to_dict(plan: AssignmentWorkspacePlan) -> dict[str, object]:
    """Convert a workspace plan into JSON-compatible data."""

    return {
        "assignment_id": plan.assignment_id,
        "jira_issue_key": plan.jira_issue_key,
        "role": plan.role.value,
        "mode": plan.mode.value,
        "workspace_path": plan.workspace_path,
        "source_repo_root": plan.source_repo_root,
        "repository": plan.repository,
        "branch_name": plan.branch_name,
        "base_branch": plan.base_branch,
        "can_provision": plan.can_provision,
        "shared_durable_paths": [
            {"name": path.name, "path": path.path} for path in plan.shared_durable_paths
        ],
        "commands": [
            {"label": command.label, "command": command.command} for command in plan.commands
        ],
        "issues": [
            {"kind": issue.kind.value, "field": issue.field, "message": issue.message}
            for issue in plan.issues
        ],
    }


def default_shared_durable_paths_from_mapping(values: Mapping[str, str]) -> tuple[SharedDurablePath, ...]:
    """Build shared durable path entries from common environment/config keys."""

    defaults = {
        "po-inbox": "data/po-inbox",
        "agent-logs": "data/agent-logs",
        "agent-state": "data/agent-state",
        "codex-limits": "data/codex-limits",
        "codex-jobs": "data/codex-jobs",
        "codex-results": "data/codex-results",
        "context-packs": "data/context-packs",
    }
    env_keys = {
        "po-inbox": "DURABLE_PO_INBOX_PATH",
        "agent-logs": "DURABLE_AGENT_LOGS_PATH",
        "agent-state": "DURABLE_AGENT_STATE_PATH",
        "codex-limits": "DURABLE_CODEX_LIMITS_PATH",
        "codex-jobs": "DURABLE_CODEX_JOBS_PATH",
        "codex-results": "DURABLE_CODEX_RESULTS_PATH",
        "context-packs": "DURABLE_CONTEXT_PACKS_PATH",
    }
    return tuple(
        SharedDurablePath(name=name, path=values.get(env_key, defaults[name]).strip() or defaults[name])
        for name, env_key in env_keys.items()
    )


def _validate_workspace_plan(
    plan: AssignmentWorkspacePlan,
    *,
    workspaces_root: str,
    project_key: str,
    credentials_available: bool,
    require_existing_source: bool,
) -> tuple[WorkspaceProvisioningIssue, ...]:
    issues: list[WorkspaceProvisioningIssue] = []
    _require_text(issues, WorkspaceProvisioningIssueKind.MISSING_ASSIGNMENT_ID, "assignment.id", plan.assignment_id)
    _require_text(
        issues,
        WorkspaceProvisioningIssueKind.MISSING_JIRA_ISSUE_KEY,
        "assignment.jira_issue_key",
        plan.jira_issue_key,
    )
    _require_text(issues, WorkspaceProvisioningIssueKind.MISSING_PROJECT_KEY, "assignment.jira_project_key", project_key)
    _require_text(issues, WorkspaceProvisioningIssueKind.MISSING_WORKSPACES_ROOT, "workspaces_root", workspaces_root)
    if not isinstance(plan.role, AgentRole):
        issues.append(
            WorkspaceProvisioningIssue(
                kind=WorkspaceProvisioningIssueKind.UNSUPPORTED_ROLE,
                field="assignment.role",
                message="Assignment role must be a known AgentRole.",
            )
        )
    if plan.mode in {WorkspaceProvisioningMode.GIT_WORKTREE, WorkspaceProvisioningMode.COPIED_SNAPSHOT}:
        _require_text(
            issues,
            WorkspaceProvisioningIssueKind.MISSING_TARGET_REPO_ROOT,
            "assignment.project_root",
            plan.source_repo_root,
        )
        if require_existing_source and plan.source_repo_root:
            source_path = Path(plan.source_repo_root)
            if not source_path.exists():
                issues.append(
                    WorkspaceProvisioningIssue(
                        kind=WorkspaceProvisioningIssueKind.MISSING_TARGET_REPO_ROOT,
                        field="assignment.project_root",
                        message="Target repository root does not exist.",
                    )
                )
            elif plan.mode is WorkspaceProvisioningMode.GIT_WORKTREE and not (source_path / ".git").exists():
                issues.append(
                    WorkspaceProvisioningIssue(
                        kind=WorkspaceProvisioningIssueKind.MISSING_TARGET_GIT_METADATA,
                        field="assignment.project_root",
                        message="Git worktree mode requires a Git-backed target repository.",
                    )
                )
    if plan.mode in {WorkspaceProvisioningMode.GIT_WORKTREE, WorkspaceProvisioningMode.FRESH_CLONE}:
        _require_text(issues, WorkspaceProvisioningIssueKind.MISSING_REPOSITORY, "assignment.repository", plan.repository)
        _validate_feature_branch(issues, plan)
        if not credentials_available:
            issues.append(
                WorkspaceProvisioningIssue(
                    kind=WorkspaceProvisioningIssueKind.MISSING_GIT_CREDENTIALS,
                    field="git.credentials",
                    message="Git credentials must be configured before provisioning a mutating workspace.",
                )
            )
    if plan.workspace_path and plan.source_repo_root and _same_or_inside(plan.workspace_path, plan.source_repo_root):
        issues.append(
            WorkspaceProvisioningIssue(
                kind=WorkspaceProvisioningIssueKind.WORKSPACE_REUSES_SOURCE,
                field="workspace_path",
                message="Isolated workspace must not reuse the mutable source repository root.",
            )
        )
    issues.extend(_validate_durable_paths(plan))
    return tuple(issues)


def _validate_feature_branch(issues: list[WorkspaceProvisioningIssue], plan: AssignmentWorkspacePlan) -> None:
    if not plan.branch_name:
        issues.append(
            WorkspaceProvisioningIssue(
                kind=WorkspaceProvisioningIssueKind.MISSING_BRANCH_NAME,
                field="assignment.branch_name",
                message="Mutating workspace modes require an assignment feature branch.",
            )
        )
        return
    match = FEATURE_BRANCH_PATTERN.fullmatch(plan.branch_name)
    if match is None:
        issues.append(
            WorkspaceProvisioningIssue(
                kind=WorkspaceProvisioningIssueKind.INVALID_BRANCH_NAME,
                field="assignment.branch_name",
                message="Branch must follow feature/{JIRA_KEY}-{short-slug}.",
            )
        )
        return
    if match.group("issue") != plan.jira_issue_key:
        issues.append(
            WorkspaceProvisioningIssue(
                kind=WorkspaceProvisioningIssueKind.BRANCH_ISSUE_MISMATCH,
                field="assignment.branch_name",
                message="Feature branch Jira key must match the assignment issue key.",
            )
        )


def _validate_durable_paths(plan: AssignmentWorkspacePlan) -> tuple[WorkspaceProvisioningIssue, ...]:
    issues: list[WorkspaceProvisioningIssue] = []
    by_name = {path.name: path.path for path in plan.shared_durable_paths}
    for required in REQUIRED_SHARED_DURABLE_PATH_NAMES:
        if not by_name.get(required, "").strip():
            issues.append(
                WorkspaceProvisioningIssue(
                    kind=WorkspaceProvisioningIssueKind.MISSING_DURABLE_PATH,
                    field=f"durable_paths.{required}",
                    message="Required shared durable coordination path is missing.",
                )
            )
    for durable_path in plan.shared_durable_paths:
        if durable_path.path and plan.workspace_path and _same_or_inside(durable_path.path, plan.workspace_path):
            issues.append(
                WorkspaceProvisioningIssue(
                    kind=WorkspaceProvisioningIssueKind.DURABLE_PATH_INSIDE_WORKSPACE,
                    field=f"durable_paths.{durable_path.name}",
                    message="Shared durable paths must stay outside the assignment workspace.",
                )
            )
    return tuple(issues)


def _build_provisioning_commands(plan: AssignmentWorkspacePlan) -> tuple[WorkspaceProvisioningCommand, ...]:
    workspace = _shell_quote(plan.workspace_path)
    branch = _shell_quote(plan.branch_name)
    base_branch = _shell_quote(plan.base_branch)
    if plan.mode is WorkspaceProvisioningMode.GIT_WORKTREE:
        source = _shell_quote(plan.source_repo_root)
        return (
            WorkspaceProvisioningCommand(
                label="fetch-base",
                command=f"git -C {source} fetch origin {base_branch}",
            ),
            WorkspaceProvisioningCommand(
                label="create-worktree",
                command=f"git -C {source} worktree add {workspace} -b {branch} origin/{plan.base_branch}",
            ),
        )
    if plan.mode is WorkspaceProvisioningMode.FRESH_CLONE:
        repository = _shell_quote(plan.repository)
        return (
            WorkspaceProvisioningCommand(
                label="clone-repository",
                command=f"git clone --branch {base_branch} {repository} {workspace}",
            ),
            WorkspaceProvisioningCommand(
                label="create-feature-branch",
                command=f"git -C {workspace} checkout -b {branch}",
            ),
        )
    source = _shell_quote(plan.source_repo_root.rstrip("/") + "/")
    return (
        WorkspaceProvisioningCommand(
            label="copy-snapshot",
            command=f"rsync -a --delete --exclude .git {source} {workspace}/",
        ),
    )


def _default_workspace_path(
    *,
    workspaces_root: str,
    project_key: str,
    jira_issue_key: str,
    role: AgentRole,
) -> str:
    root = Path(workspaces_root.strip() or "data/agent-workspaces")
    return str(
        root
        / _safe_path_component(project_key or _project_key_from_issue(jira_issue_key) or "unknown-project")
        / _safe_path_component(jira_issue_key or "unknown-issue")
        / _safe_path_component(role.value if isinstance(role, AgentRole) else str(role))
    )


def _normalize_durable_paths(paths: tuple[SharedDurablePath, ...]) -> tuple[SharedDurablePath, ...]:
    return tuple(SharedDurablePath(name=path.name.strip(), path=path.path.strip()) for path in paths)


def _require_text(
    issues: list[WorkspaceProvisioningIssue],
    kind: WorkspaceProvisioningIssueKind,
    field: str,
    value: str,
) -> None:
    if not value.strip():
        issues.append(WorkspaceProvisioningIssue(kind=kind, field=field, message="Value is required."))


def _project_key_from_issue(jira_issue_key: str) -> str:
    return jira_issue_key.split("-", 1)[0] if "-" in jira_issue_key else ""


def _safe_path_component(value: str) -> str:
    normalized = SAFE_PATH_COMPONENT_PATTERN.sub("-", value.strip()).strip(".-")
    return normalized or "unknown"


def _same_or_inside(child: str, parent: str) -> bool:
    try:
        child_path = Path(child).expanduser().resolve(strict=False)
        parent_path = Path(parent).expanduser().resolve(strict=False)
        return child_path == parent_path or parent_path in child_path.parents
    except RuntimeError:
        return False


def _shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"
