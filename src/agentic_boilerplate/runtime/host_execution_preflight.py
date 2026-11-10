"""Fail-closed preflight for host-side Codex execution."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from agentic_boilerplate.domain import (
    AgentAssignment,
    AgentRole,
    AssignmentWorkspacePlan,
    CodexLimitAvailabilityRecord,
    CodexLimitGateDecision,
    CodexLimitObservationSource,
    decide_codex_limit_gate,
)

ELIGIBLE_EXECUTION_STATUSES: tuple[str, ...] = ("READY TO START", "IN PROGRESS")


class HostCodexPreflightIssueKind(str, Enum):
    """Machine-readable blocker kind for host-side execution preflight."""

    WORKSPACE_PLAN_BLOCKED = "workspace-plan-blocked"
    MISSING_PATH_MAPPING = "missing-path-mapping"
    PATH_ESCAPE = "path-escape"
    CHECKOUT_MISSING = "checkout-missing"
    GIT_METADATA_MISSING = "git-metadata-missing"
    SOURCE_CHECKOUT_REUSED = "source-checkout-reused"
    REPOSITORY_MISMATCH = "repository-mismatch"
    BRANCH_MISMATCH = "branch-mismatch"
    PROJECT_MISMATCH = "project-mismatch"
    JIRA_PROJECT_MISMATCH = "jira-project-mismatch"
    ISSUE_MISMATCH = "issue-mismatch"
    ROLE_MISMATCH = "role-mismatch"
    OUTPUT_ROOT_MISSING = "output-root-missing"
    OUTPUT_PATH_OUTSIDE_ROOT = "output-path-outside-root"
    STATUS_NOT_ELIGIBLE = "status-not-eligible"
    DEPENDENCIES_UNRESOLVED = "dependencies-unresolved"
    BLOCKING_BUGS = "blocking-bugs"
    PO_BLOCKERS = "po-blockers"
    UI_DESIGN_NOT_ACCEPTED = "ui-design-not-accepted"
    STALE_CONTEXT = "stale-context"
    FOREIGN_LOCK = "foreign-lock"
    LIMIT_REFRESH_MISSING = "limit-refresh-missing"
    LIMIT_SOURCE_UNSUPPORTED = "limit-source-unsupported"
    LIMIT_RECORD_MISSING = "limit-record-missing"
    LIMIT_GATE_CLOSED = "limit-gate-closed"


@dataclass(frozen=True)
class HostPathMapping:
    """Explicit mapping from a configured runtime path prefix to a host path prefix."""

    source_prefix: str
    host_prefix: str
    name: str = ""


@dataclass(frozen=True)
class HostCheckoutState:
    """Observed identity of an already provisioned host checkout."""

    repository: str
    branch_name: str
    project_id: str
    jira_project_key: str
    jira_issue_key: str
    role: AgentRole | str
    source_repo_root: str = ""


@dataclass(frozen=True)
class HostScopeState:
    """Current workflow state that must still authorize execution."""

    jira_issue_key: str
    jira_project_key: str
    project_id: str
    role: AgentRole | str
    status: str
    eligible_statuses: tuple[str, ...] = ELIGIBLE_EXECUTION_STATUSES
    unresolved_dependency_keys: tuple[str, ...] = ()
    blocking_bug_keys: tuple[str, ...] = ()
    po_blocker_ids: tuple[str, ...] = ()
    ui_design_required: bool = False
    accepted_ui_design_reference: str = ""
    context_revision_current: bool = True
    context_revision: str = ""
    assignment_lock_owner: str = ""
    expected_worker_id: str = ""
    assignment_reference: str = ""
    po_inbox_reference: str = ""


@dataclass(frozen=True)
class HostCodexLimitRefreshEvidence:
    """Evidence that the host refreshed Codex quota from account/rateLimits/read."""

    record: CodexLimitAvailabilityRecord | None
    observation_id: str
    observed_at: str
    source: CodexLimitObservationSource | str = CodexLimitObservationSource.CODEX_APP_SERVER
    account_scope_id: str = ""
    bucket_id: str = ""
    refreshed_this_attempt: bool = True


@dataclass(frozen=True)
class HostCodexPreflightIssue:
    """One fail-closed reason returned by the host-side execution preflight."""

    kind: HostCodexPreflightIssueKind
    field: str
    message: str
    reference: str = ""


@dataclass(frozen=True)
class HostCodexPreflightRequest:
    """All context needed to decide whether a host-side Codex stage may start."""

    assignment: AgentAssignment
    workspace_plan: AssignmentWorkspacePlan
    checkout: HostCheckoutState
    scope: HostScopeState
    limit_refresh: HostCodexLimitRefreshEvidence | None
    path_mappings: tuple[HostPathMapping, ...]
    permitted_output_roots: tuple[str, ...]
    now: str
    limit_stale_after_seconds: int | None = 300
    limit_future_tolerance_seconds: int = 30


@dataclass(frozen=True)
class HostCodexPreflightDecision:
    """Visible allow/block decision for one host-side Codex executor launch."""

    allowed: bool
    issues: tuple[HostCodexPreflightIssue, ...]
    host_workspace_path: str
    limit_gate: CodexLimitGateDecision | None = None
    limit_observation_id: str = ""
    limit_observation_source: str = ""
    limit_observed_at: str = ""
    limit_account_scope_id: str = ""
    limit_bucket_id: str = ""
    assignment_reference: str = ""
    po_inbox_reference: str = ""

    @property
    def blocking_reasons(self) -> tuple[str, ...]:
        """Return human-readable issue messages for blocked decisions."""

        return tuple(issue.message for issue in self.issues)


def evaluate_host_codex_preflight(request: HostCodexPreflightRequest) -> HostCodexPreflightDecision:
    """Return a fail-closed decision before any host-side Codex process starts."""

    issues: list[HostCodexPreflightIssue] = []
    issues.extend(_workspace_plan_issues(request.workspace_plan))
    workspace_path = _resolve_required_host_path(
        request.workspace_plan.workspace_path,
        request.path_mappings,
        field="workspace_plan.workspace_path",
        issues=issues,
    )
    source_repo_root = request.checkout.source_repo_root or request.workspace_plan.source_repo_root
    if workspace_path is not None:
        _validate_workspace_path(workspace_path, source_repo_root=source_repo_root, issues=issues)
    _validate_checkout_identity(request.assignment, request.workspace_plan, request.checkout, request.scope, issues)
    _validate_output_roots(request.assignment, request.path_mappings, request.permitted_output_roots, issues)
    _validate_scope(request.scope, issues)
    limit_gate = _validate_limit_refresh(request, issues)

    return HostCodexPreflightDecision(
        allowed=not issues,
        issues=tuple(issues),
        host_workspace_path=str(workspace_path) if workspace_path is not None else "",
        limit_gate=limit_gate,
        limit_observation_id=request.limit_refresh.observation_id if request.limit_refresh else "",
        limit_observation_source=_source_value(request.limit_refresh.source) if request.limit_refresh else "",
        limit_observed_at=request.limit_refresh.observed_at if request.limit_refresh else "",
        limit_account_scope_id=request.limit_refresh.account_scope_id if request.limit_refresh else "",
        limit_bucket_id=request.limit_refresh.bucket_id if request.limit_refresh else "",
        assignment_reference=request.scope.assignment_reference,
        po_inbox_reference=request.scope.po_inbox_reference,
    )


def require_host_codex_preflight(request: HostCodexPreflightRequest) -> HostCodexPreflightDecision:
    """Return the decision or raise ValueError with structured blocker text."""

    decision = evaluate_host_codex_preflight(request)
    if not decision.allowed:
        raise ValueError(render_host_codex_preflight_decision(decision))
    return decision


def render_host_codex_preflight_decision(decision: HostCodexPreflightDecision) -> str:
    """Render a compact Markdown decision for logs, inbox items, or Jira comments."""

    lines = [
        f"Host Codex preflight: {'allowed' if decision.allowed else 'blocked'}",
        f"Workspace: {decision.host_workspace_path or 'unresolved'}",
        f"Limit observation: {decision.limit_observation_id or 'missing'}",
        f"Limit source: {decision.limit_observation_source or 'missing'}",
        f"Observed at: {decision.limit_observed_at or 'missing'}",
    ]
    if decision.assignment_reference:
        lines.append(f"Assignment: {decision.assignment_reference}")
    if decision.po_inbox_reference:
        lines.append(f"PO inbox: {decision.po_inbox_reference}")
    if decision.limit_gate is not None:
        lines.append(f"Limit gate: {decision.limit_gate.action.value} - {decision.limit_gate.reason}")
    if decision.issues:
        lines.append("Issues:")
        lines.extend(
            f"- {issue.kind.value} ({issue.field}): {issue.message}"
            + (f" [{issue.reference}]" if issue.reference else "")
            for issue in decision.issues
        )
    return "\n".join(lines)


def _workspace_plan_issues(plan: AssignmentWorkspacePlan) -> tuple[HostCodexPreflightIssue, ...]:
    return tuple(
        HostCodexPreflightIssue(
            kind=HostCodexPreflightIssueKind.WORKSPACE_PLAN_BLOCKED,
            field=issue.field,
            message=issue.message,
            reference=issue.kind.value,
        )
        for issue in plan.issues
    )


def _validate_workspace_path(
    workspace_path: Path,
    *,
    source_repo_root: str,
    issues: list[HostCodexPreflightIssue],
) -> None:
    if not workspace_path.exists():
        issues.append(
            HostCodexPreflightIssue(
                HostCodexPreflightIssueKind.CHECKOUT_MISSING,
                "workspace_plan.workspace_path",
                "Resolved host checkout path does not exist.",
                str(workspace_path),
            )
        )
        return
    if not (workspace_path / ".git").exists():
        issues.append(
            HostCodexPreflightIssue(
                HostCodexPreflightIssueKind.GIT_METADATA_MISSING,
                "workspace_plan.workspace_path",
                "Resolved host checkout does not contain Git metadata.",
                str(workspace_path),
            )
        )
    if source_repo_root and _same_or_inside(workspace_path, Path(source_repo_root)):
        issues.append(
            HostCodexPreflightIssue(
                HostCodexPreflightIssueKind.SOURCE_CHECKOUT_REUSED,
                "workspace_plan.workspace_path",
                "Host execution workspace must not reuse the shared source checkout.",
                str(workspace_path),
            )
        )


def _validate_checkout_identity(
    assignment: AgentAssignment,
    plan: AssignmentWorkspacePlan,
    checkout: HostCheckoutState,
    scope: HostScopeState,
    issues: list[HostCodexPreflightIssue],
) -> None:
    expected_role = _role_value(assignment.role)
    checkout_role = _role_value(checkout.role)
    scope_role = _role_value(scope.role)
    _check_equal(
        issues,
        HostCodexPreflightIssueKind.REPOSITORY_MISMATCH,
        "checkout.repository",
        checkout.repository,
        plan.repository or assignment.repository,
        "Observed repository does not match the assignment workspace plan.",
    )
    _check_equal(
        issues,
        HostCodexPreflightIssueKind.BRANCH_MISMATCH,
        "checkout.branch_name",
        checkout.branch_name,
        plan.branch_name or assignment.branch_name,
        "Observed branch does not match the assignment feature branch.",
    )
    _check_equal(
        issues,
        HostCodexPreflightIssueKind.PROJECT_MISMATCH,
        "checkout.project_id",
        checkout.project_id,
        assignment.project_id,
        "Observed project id does not match the assignment.",
    )
    _check_equal(
        issues,
        HostCodexPreflightIssueKind.JIRA_PROJECT_MISMATCH,
        "checkout.jira_project_key",
        checkout.jira_project_key,
        assignment.jira_project_key,
        "Observed Jira project key does not match the assignment.",
    )
    _check_equal(
        issues,
        HostCodexPreflightIssueKind.ISSUE_MISMATCH,
        "checkout.jira_issue_key",
        checkout.jira_issue_key,
        assignment.jira_issue_key,
        "Observed Jira issue key does not match the assignment.",
    )
    _check_equal(
        issues,
        HostCodexPreflightIssueKind.ISSUE_MISMATCH,
        "scope.jira_issue_key",
        scope.jira_issue_key,
        assignment.jira_issue_key,
        "Current workflow scope is not for the assignment issue.",
    )
    if checkout_role != expected_role or scope_role != expected_role:
        issues.append(
            HostCodexPreflightIssue(
                HostCodexPreflightIssueKind.ROLE_MISMATCH,
                "checkout.role",
                "Observed role and current scope must match the assignment role.",
                f"assignment={expected_role} checkout={checkout_role} scope={scope_role}",
            )
        )


def _validate_output_roots(
    assignment: AgentAssignment,
    path_mappings: Sequence[HostPathMapping],
    permitted_output_roots: Sequence[str],
    issues: list[HostCodexPreflightIssue],
) -> None:
    roots = tuple(Path(root).expanduser().resolve(strict=False) for root in permitted_output_roots if root.strip())
    if not roots:
        issues.append(
            HostCodexPreflightIssue(
                HostCodexPreflightIssueKind.OUTPUT_ROOT_MISSING,
                "permitted_output_roots",
                "At least one permitted durable output root is required.",
            )
        )
        return

    for field_name, raw_path in (
        ("assignment.paths.output_path", assignment.paths.output_path),
        ("assignment.paths.codex_job_path", assignment.paths.codex_job_path),
        ("assignment.paths.evidence_path", assignment.paths.evidence_path),
        ("assignment.paths.failed_request_path", assignment.paths.failed_request_path),
    ):
        if not raw_path.strip():
            continue
        resolved = _resolve_optional_host_path(raw_path, path_mappings)
        if resolved is None:
            issues.append(
                HostCodexPreflightIssue(
                    HostCodexPreflightIssueKind.MISSING_PATH_MAPPING,
                    field_name,
                    "Configured output path must resolve through an explicit host path mapping.",
                    raw_path,
                )
            )
            continue
        if not any(_same_or_inside(resolved, root) for root in roots):
            issues.append(
                HostCodexPreflightIssue(
                    HostCodexPreflightIssueKind.OUTPUT_PATH_OUTSIDE_ROOT,
                    field_name,
                    "Configured output path is outside permitted durable output roots.",
                    str(resolved),
                )
            )


def _validate_scope(scope: HostScopeState, issues: list[HostCodexPreflightIssue]) -> None:
    status = _normalize_status(scope.status)
    eligible = {_normalize_status(value) for value in scope.eligible_statuses}
    if status not in eligible:
        issues.append(
            HostCodexPreflightIssue(
                HostCodexPreflightIssueKind.STATUS_NOT_ELIGIBLE,
                "scope.status",
                "Story is no longer in an execution-eligible Jira status.",
                scope.status,
            )
        )
    if scope.unresolved_dependency_keys:
        issues.append(
            HostCodexPreflightIssue(
                HostCodexPreflightIssueKind.DEPENDENCIES_UNRESOLVED,
                "scope.unresolved_dependency_keys",
                "Unresolved prerequisite links prevent executor invocation.",
                ", ".join(scope.unresolved_dependency_keys),
            )
        )
    if scope.blocking_bug_keys:
        issues.append(
            HostCodexPreflightIssue(
                HostCodexPreflightIssueKind.BLOCKING_BUGS,
                "scope.blocking_bug_keys",
                "Linked blocking bugs prevent executor invocation.",
                ", ".join(scope.blocking_bug_keys),
            )
        )
    if scope.po_blocker_ids:
        issues.append(
            HostCodexPreflightIssue(
                HostCodexPreflightIssueKind.PO_BLOCKERS,
                "scope.po_blocker_ids",
                "Open Product Owner blockers prevent executor invocation.",
                ", ".join(scope.po_blocker_ids),
            )
        )
    if scope.ui_design_required and not scope.accepted_ui_design_reference.strip():
        issues.append(
            HostCodexPreflightIssue(
                HostCodexPreflightIssueKind.UI_DESIGN_NOT_ACCEPTED,
                "scope.accepted_ui_design_reference",
                "UI work requires an accepted design reference before execution.",
            )
        )
    if not scope.context_revision_current:
        issues.append(
            HostCodexPreflightIssue(
                HostCodexPreflightIssueKind.STALE_CONTEXT,
                "scope.context_revision_current",
                "Context pack revision is stale and must be rebuilt before execution.",
                scope.context_revision,
            )
        )
    if scope.expected_worker_id.strip() and scope.assignment_lock_owner.strip() != scope.expected_worker_id.strip():
        issues.append(
            HostCodexPreflightIssue(
                HostCodexPreflightIssueKind.FOREIGN_LOCK,
                "scope.assignment_lock_owner",
                "Assignment lock is absent or owned by another worker.",
                f"owner={scope.assignment_lock_owner or 'none'} expected={scope.expected_worker_id}",
            )
        )


def _validate_limit_refresh(
    request: HostCodexPreflightRequest,
    issues: list[HostCodexPreflightIssue],
) -> CodexLimitGateDecision | None:
    evidence = request.limit_refresh
    if evidence is None or not evidence.refreshed_this_attempt:
        issues.append(
            HostCodexPreflightIssue(
                HostCodexPreflightIssueKind.LIMIT_REFRESH_MISSING,
                "limit_refresh",
                "A fresh account/rateLimits/read observation is required for this launch or resume.",
            )
        )
        return None
    source = _source_value(evidence.source)
    if source != CodexLimitObservationSource.CODEX_APP_SERVER.value:
        issues.append(
            HostCodexPreflightIssue(
                HostCodexPreflightIssueKind.LIMIT_SOURCE_UNSUPPORTED,
                "limit_refresh.source",
                "Codex quota preflight must come from the authenticated host App Server.",
                source,
            )
        )
    if evidence.record is None:
        issues.append(
            HostCodexPreflightIssue(
                HostCodexPreflightIssueKind.LIMIT_RECORD_MISSING,
                "limit_refresh.record",
                "Fresh quota refresh did not produce a persisted availability record.",
            )
        )
        return None
    gate = decide_codex_limit_gate(
        evidence.record,
        now=request.now,
        stale_after_seconds=request.limit_stale_after_seconds,
        future_tolerance_seconds=request.limit_future_tolerance_seconds,
    )
    if not gate.allowed:
        issues.append(
            HostCodexPreflightIssue(
                HostCodexPreflightIssueKind.LIMIT_GATE_CLOSED,
                "limit_refresh.record",
                gate.reason,
                gate.resume_after,
            )
        )
    return gate


def _resolve_required_host_path(
    raw_path: str,
    mappings: Sequence[HostPathMapping],
    *,
    field: str,
    issues: list[HostCodexPreflightIssue],
) -> Path | None:
    resolved = _resolve_optional_host_path(raw_path, mappings)
    if resolved is None:
        issues.append(
            HostCodexPreflightIssue(
                HostCodexPreflightIssueKind.MISSING_PATH_MAPPING,
                field,
                "Path must resolve through an explicit host path mapping.",
                raw_path,
            )
        )
        return None
    mapping = _matching_mapping(raw_path, mappings)
    if mapping is not None and not _same_or_inside(resolved, Path(mapping.host_prefix)):
        issues.append(
            HostCodexPreflightIssue(
                HostCodexPreflightIssueKind.PATH_ESCAPE,
                field,
                "Mapped path escapes its configured host prefix.",
                str(resolved),
            )
        )
    return resolved


def _resolve_optional_host_path(raw_path: str, mappings: Sequence[HostPathMapping]) -> Path | None:
    mapping = _matching_mapping(raw_path, mappings)
    if mapping is None:
        return None
    suffix = _strip_prefix(raw_path, mapping.source_prefix)
    return (Path(mapping.host_prefix) / suffix).expanduser().resolve(strict=False)


def _matching_mapping(raw_path: str, mappings: Sequence[HostPathMapping]) -> HostPathMapping | None:
    value = _normalized_path_text(raw_path)
    candidates = sorted(mappings, key=lambda item: len(_normalized_path_text(item.source_prefix)), reverse=True)
    for mapping in candidates:
        prefix = _normalized_path_text(mapping.source_prefix).rstrip("/")
        if not prefix or not mapping.host_prefix.strip():
            continue
        if value == prefix or value.startswith(prefix + "/"):
            return mapping
    return None


def _strip_prefix(raw_path: str, prefix: str) -> Path:
    value = _normalized_path_text(raw_path)
    normalized_prefix = _normalized_path_text(prefix).rstrip("/")
    suffix = value[len(normalized_prefix) :].lstrip("/")
    return Path(suffix)


def _check_equal(
    issues: list[HostCodexPreflightIssue],
    kind: HostCodexPreflightIssueKind,
    field: str,
    actual: str,
    expected: str,
    message: str,
) -> None:
    if (actual or "").strip() != (expected or "").strip():
        issues.append(
            HostCodexPreflightIssue(
                kind,
                field,
                message,
                f"actual={actual or 'missing'} expected={expected or 'missing'}",
            )
        )


def _same_or_inside(child: Path, parent: Path) -> bool:
    try:
        child_path = child.expanduser().resolve(strict=False)
        parent_path = parent.expanduser().resolve(strict=False)
        return child_path == parent_path or parent_path in child_path.parents
    except RuntimeError:
        return False


def _normalized_path_text(value: str) -> str:
    return str(value).strip().replace("\\", "/").rstrip("/")


def _role_value(value: AgentRole | str) -> str:
    return value.value if isinstance(value, AgentRole) else str(value).strip()


def _normalize_status(value: str) -> str:
    return " ".join(value.replace("_", " ").replace("/", " /").split()).upper()


def _source_value(value: CodexLimitObservationSource | str) -> str:
    return value.value if isinstance(value, CodexLimitObservationSource) else str(value).strip()
