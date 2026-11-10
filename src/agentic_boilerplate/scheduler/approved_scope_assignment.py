"""Approved sprint scope assignment workflow."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from agentic_boilerplate.domain import (
    AgentAssignment,
    AgentRole,
    AssignmentPaths,
    AssignmentLockDecision,
    AssignmentStatus,
    CodexLimitGateDecision,
    DefinitionOfReadyDecision,
    GateDecision,
    ReleaseScope,
    SprintRing,
    sprint_ring_by_number,
)
from agentic_boilerplate.domain.dependency_eligibility import DependencyGraphAuditResult
from agentic_boilerplate.storage import FileAgentAssignmentStore


READY_TO_START_STATUS = "READY TO START"


@dataclass(frozen=True)
class SchedulerIssueCandidate:
    """Jira issue considered by the scheduler for assignment."""

    issue_key: str
    title: str
    status: str
    role: AgentRole
    dependency_gate: GateDecision
    context_pack_path: str
    codex_job_path: str
    output_path: str
    branch_name: str = ""
    definition_of_ready: DefinitionOfReadyDecision | None = None
    assignment_lock: AssignmentLockDecision | None = None
    codex_limit_gate: CodexLimitGateDecision | None = None
    po_inbox_item_id: str = ""
    po_block_reason: str = ""
    conflict_reason: str = ""
    unresolved_linked_bug_keys: tuple[str, ...] = ()


class SchedulerRejectionKind(str, Enum):
    """Machine-readable scheduler rejection or fallback skip categories."""

    STATUS_NOT_READY = "status_not_ready"
    OUT_OF_SCOPE = "out_of_scope"
    DEPENDENCY_BLOCKED = "dependency_blocked"
    DEPENDENCY_GRAPH_BLOCKED = "dependency_graph_blocked"
    ASSIGNMENT_LOCKED = "assignment_locked"
    CODEX_LIMIT_BLOCKED = "codex_limit_blocked"
    PO_BLOCKED = "po_blocked"
    CONFLICT_BLOCKED = "conflict_blocked"
    LINKED_BUG_BLOCKED = "linked_bug_blocked"
    DEFINITION_OF_READY_MISSING = "definition_of_ready_missing"
    DEFINITION_OF_READY_FAILED = "definition_of_ready_failed"
    ROLE_MISMATCH = "role_mismatch"
    MISSING_PREFERRED = "missing_preferred"


@dataclass(frozen=True)
class RejectedSchedulerIssue:
    """Issue skipped by the assignment planner."""

    issue_key: str
    reason: str
    kind: SchedulerRejectionKind | None = None
    details: tuple[str, ...] = ()


@dataclass(frozen=True)
class SchedulerAssignmentPlan:
    """Assignments and rejections for one approved sprint ring."""

    release_scope_key: str
    sprint_ring_number: int
    assignments: tuple[AgentAssignment, ...]
    rejected: tuple[RejectedSchedulerIssue, ...]
    override_reason: str = ""


@dataclass(frozen=True)
class SchedulerFallbackPlan:
    """Single-assignment fallback decision for a blocked preferred issue."""

    release_scope_key: str
    sprint_ring_number: int
    preferred_issue_key: str
    selected_assignment: AgentAssignment | None
    skipped: tuple[RejectedSchedulerIssue, ...]
    fallback_used: bool
    paused_reason: str = ""


def build_approved_scope_assignment_plan(
    release_scope: ReleaseScope,
    *,
    sprint_ring_number: int,
    candidates: tuple[SchedulerIssueCandidate, ...],
    created_at: str,
    dependency_graph_audit: DependencyGraphAuditResult | None = None,
    allow_out_of_scope_override: bool = False,
    override_reason: str = "",
) -> SchedulerAssignmentPlan:
    """Create queued assignments for approved, ready, unblocked sprint issues."""

    ring = sprint_ring_by_number(release_scope, sprint_ring_number)
    ring_issue_keys = {issue.key for issue in ring.included_issues}
    selected: list[AgentAssignment] = []
    rejected: list[RejectedSchedulerIssue] = []
    normalized_status = _normalize_status(READY_TO_START_STATUS)
    override = allow_out_of_scope_override and bool(override_reason.strip())
    graph_blocked_issue_keys = _dependency_graph_blocked_issue_keys(dependency_graph_audit)

    for candidate in candidates:
        rejection = _candidate_rejection(
            candidate,
            ring_issue_keys=ring_issue_keys,
            normalized_ready_status=normalized_status,
            override=override,
            graph_blocked_issue_keys=graph_blocked_issue_keys,
            dependency_graph_audit=dependency_graph_audit,
        )
        if rejection is not None:
            rejected.append(rejection)
            continue
        selected.append(_assignment_from_candidate(candidate, created_at))

    return SchedulerAssignmentPlan(
        release_scope_key=release_scope.key,
        sprint_ring_number=ring.number,
        assignments=tuple(selected),
        rejected=tuple(rejected),
        override_reason=override_reason.strip() if override else "",
    )


def build_scheduler_fallback_plan(
    release_scope: ReleaseScope,
    *,
    sprint_ring_number: int,
    preferred_issue_key: str,
    candidates: tuple[SchedulerIssueCandidate, ...],
    created_at: str,
    preferred_role: AgentRole | None = None,
    dependency_graph_audit: DependencyGraphAuditResult | None = None,
    allow_out_of_scope_override: bool = False,
    override_reason: str = "",
) -> SchedulerFallbackPlan:
    """Select the preferred issue or the next eligible same-role sprint issue.

    This policy is used when a worker or orchestrator wakes up after a trigger
    and the story it wanted to continue is currently blocked. The blocked
    preferred story remains visible in ``skipped`` while another same-sprint,
    same-role item can keep the sprint moving.
    """

    ring = sprint_ring_by_number(release_scope, sprint_ring_number)
    ring_issue_keys = {issue.key for issue in ring.included_issues}
    normalized_status = _normalize_status(READY_TO_START_STATUS)
    override = allow_out_of_scope_override and bool(override_reason.strip())
    graph_blocked_issue_keys = _dependency_graph_blocked_issue_keys(dependency_graph_audit)
    preferred = next((candidate for candidate in candidates if candidate.issue_key == preferred_issue_key), None)
    selected_preferred_role = preferred.role if preferred is not None else preferred_role
    skipped: list[RejectedSchedulerIssue] = []

    if preferred is None:
        skipped.append(
            RejectedSchedulerIssue(
                preferred_issue_key,
                "Preferred issue was not present in scheduler candidates.",
                SchedulerRejectionKind.MISSING_PREFERRED,
            )
        )
        if selected_preferred_role is None:
            return SchedulerFallbackPlan(
                release_scope_key=release_scope.key,
                sprint_ring_number=ring.number,
                preferred_issue_key=preferred_issue_key,
                selected_assignment=None,
                skipped=tuple(skipped),
                fallback_used=False,
                paused_reason="Preferred issue was not present and no preferred role was provided.",
            )
    else:
        preferred_rejection = _candidate_rejection(
            preferred,
            ring_issue_keys=ring_issue_keys,
            normalized_ready_status=normalized_status,
            override=override,
            graph_blocked_issue_keys=graph_blocked_issue_keys,
            dependency_graph_audit=dependency_graph_audit,
        )
        if preferred_rejection is None:
            return SchedulerFallbackPlan(
                release_scope_key=release_scope.key,
                sprint_ring_number=ring.number,
                preferred_issue_key=preferred_issue_key,
                selected_assignment=_assignment_from_candidate(preferred, created_at),
                skipped=(),
                fallback_used=False,
            )
        skipped.append(preferred_rejection)

    for candidate in candidates:
        if candidate.issue_key == preferred_issue_key:
            continue
        if selected_preferred_role is not None and candidate.role is not selected_preferred_role:
            skipped.append(
                RejectedSchedulerIssue(
                    candidate.issue_key,
                    "Issue role differs from the blocked preferred issue role.",
                    SchedulerRejectionKind.ROLE_MISMATCH,
                    (candidate.role.value, selected_preferred_role.value),
                )
            )
            continue
        rejection = _candidate_rejection(
            candidate,
            ring_issue_keys=ring_issue_keys,
            normalized_ready_status=normalized_status,
            override=override,
            graph_blocked_issue_keys=graph_blocked_issue_keys,
            dependency_graph_audit=dependency_graph_audit,
        )
        if rejection is not None:
            skipped.append(rejection)
            continue
        return SchedulerFallbackPlan(
            release_scope_key=release_scope.key,
            sprint_ring_number=ring.number,
            preferred_issue_key=preferred_issue_key,
            selected_assignment=_assignment_from_candidate(candidate, created_at),
            skipped=tuple(skipped),
            fallback_used=True,
        )

    return SchedulerFallbackPlan(
        release_scope_key=release_scope.key,
        sprint_ring_number=ring.number,
        preferred_issue_key=preferred_issue_key,
        selected_assignment=None,
        skipped=tuple(skipped),
        fallback_used=False,
        paused_reason="No eligible READY TO START issue exists for the same role in the approved sprint ring.",
    )


def render_scheduler_fallback_plan(plan: SchedulerFallbackPlan) -> str:
    """Render a human-readable scheduler fallback decision for logs/Jira."""

    selected_key = plan.selected_assignment.jira_issue_key if plan.selected_assignment else "None"
    lines = [
        f"# Scheduler Fallback - {plan.preferred_issue_key}",
        "",
        f"- Release scope: {plan.release_scope_key}",
        f"- Sprint ring: {plan.sprint_ring_number}",
        f"- Preferred issue: {plan.preferred_issue_key}",
        f"- Selected issue: {selected_key}",
        f"- Fallback used: {'yes' if plan.fallback_used else 'no'}",
    ]
    if plan.paused_reason:
        lines.append(f"- Paused reason: {plan.paused_reason}")
    lines.extend(["", "## Skipped Issues"])
    if plan.skipped:
        for skipped in plan.skipped:
            kind = skipped.kind.value if skipped.kind else "unknown"
            lines.append(f"- {skipped.issue_key}: {kind} - {skipped.reason}")
            if skipped.details:
                lines.append(f"  Details: {', '.join(skipped.details)}")
    else:
        lines.append("- None")
    if plan.selected_assignment:
        lines.extend(
            [
                "",
                "## Queued Assignment",
                f"- Assignment id: {plan.selected_assignment.id}",
                f"- Jira issue: {plan.selected_assignment.jira_issue_key}",
                f"- Role: {plan.selected_assignment.role.value}",
                f"- Status: {plan.selected_assignment.status.value}",
                f"- Context pack: {plan.selected_assignment.paths.context_pack_path}",
                f"- Codex job: {plan.selected_assignment.paths.codex_job_path}",
                f"- Output path: {plan.selected_assignment.paths.output_path}",
                f"- Branch: {plan.selected_assignment.branch_name or 'not set'}",
            ]
        )
    return "\n".join(lines) + "\n"


def scheduler_fallback_plan_to_dict(plan: SchedulerFallbackPlan) -> dict[str, Any]:
    """Convert a fallback plan to JSON-compatible data."""

    selected = plan.selected_assignment
    return {
        "release_scope_key": plan.release_scope_key,
        "sprint_ring_number": plan.sprint_ring_number,
        "preferred_issue_key": plan.preferred_issue_key,
        "selected_assignment": None
        if selected is None
        else {
            "id": selected.id,
            "jira_issue_key": selected.jira_issue_key,
            "role": selected.role.value,
            "status": selected.status.value,
            "context_pack_path": selected.paths.context_pack_path,
            "codex_job_path": selected.paths.codex_job_path,
            "output_path": selected.paths.output_path,
            "branch_name": selected.branch_name,
        },
        "skipped": [
            {
                "issue_key": skipped.issue_key,
                "reason": skipped.reason,
                "kind": skipped.kind.value if skipped.kind else "",
                "details": list(skipped.details),
            }
            for skipped in plan.skipped
        ],
        "fallback_used": plan.fallback_used,
        "paused_reason": plan.paused_reason,
    }


def persist_assignment_plan(
    plan: SchedulerAssignmentPlan,
    store: FileAgentAssignmentStore,
) -> tuple[AgentAssignment, ...]:
    """Persist planned assignments to the durable assignment store."""

    for assignment in plan.assignments:
        store.create_assignment(assignment)
    return plan.assignments


def _assignment_from_candidate(candidate: SchedulerIssueCandidate, created_at: str) -> AgentAssignment:
    return AgentAssignment(
        id=f"assignment-{candidate.issue_key}",
        jira_issue_key=candidate.issue_key,
        role=candidate.role,
        status=AssignmentStatus.QUEUED,
        paths=AssignmentPaths(
            context_pack_path=candidate.context_pack_path,
            codex_job_path=candidate.codex_job_path,
            output_path=candidate.output_path,
        ),
        branch_name=candidate.branch_name,
        created_at=created_at,
        updated_at=created_at,
    )


def _candidate_rejection(
    candidate: SchedulerIssueCandidate,
    *,
    ring_issue_keys: set[str],
    normalized_ready_status: str,
    override: bool,
    graph_blocked_issue_keys: set[str] | None = None,
    dependency_graph_audit: DependencyGraphAuditResult | None = None,
) -> RejectedSchedulerIssue | None:
    if _normalize_status(candidate.status) != normalized_ready_status:
        return RejectedSchedulerIssue(
            candidate.issue_key,
            "Issue is not READY TO START.",
            SchedulerRejectionKind.STATUS_NOT_READY,
        )
    if candidate.issue_key not in ring_issue_keys and not override:
        return RejectedSchedulerIssue(
            candidate.issue_key,
            "Issue is outside the approved sprint ring.",
            SchedulerRejectionKind.OUT_OF_SCOPE,
        )
    if graph_blocked_issue_keys and candidate.issue_key in graph_blocked_issue_keys:
        return RejectedSchedulerIssue(
            candidate.issue_key,
            "Dependency graph audit found a cycle or reciprocal Blocks link.",
            SchedulerRejectionKind.DEPENDENCY_GRAPH_BLOCKED,
            _dependency_graph_issue_details(candidate.issue_key, dependency_graph_audit),
        )
    if not candidate.dependency_gate.passed:
        return RejectedSchedulerIssue(
            candidate.issue_key,
            "Issue has unresolved prerequisites.",
            SchedulerRejectionKind.DEPENDENCY_BLOCKED,
            tuple(str(blocker) for blocker in candidate.dependency_gate.blockers),
        )
    if candidate.assignment_lock is not None and not candidate.assignment_lock.allowed:
        return RejectedSchedulerIssue(
            candidate.issue_key,
            "Assignment lock blocks assignment: " + "; ".join(candidate.assignment_lock.reasons),
            SchedulerRejectionKind.ASSIGNMENT_LOCKED,
        )
    if candidate.codex_limit_gate is not None and not candidate.codex_limit_gate.allowed:
        return RejectedSchedulerIssue(
            candidate.issue_key,
            "Codex limit gate blocks assignment: " + candidate.codex_limit_gate.reason,
            SchedulerRejectionKind.CODEX_LIMIT_BLOCKED,
        )
    if candidate.po_inbox_item_id.strip() or candidate.po_block_reason.strip():
        details = tuple(item for item in (candidate.po_inbox_item_id.strip(), candidate.po_block_reason.strip()) if item)
        suffix = ": " + "; ".join(details) if details else "."
        return RejectedSchedulerIssue(
            candidate.issue_key,
            "Product Owner input blocks assignment" + suffix,
            SchedulerRejectionKind.PO_BLOCKED,
            details,
        )
    if candidate.conflict_reason.strip():
        return RejectedSchedulerIssue(
            candidate.issue_key,
            "Merge or file-scope conflict blocks assignment: " + candidate.conflict_reason.strip(),
            SchedulerRejectionKind.CONFLICT_BLOCKED,
        )
    if candidate.unresolved_linked_bug_keys:
        return RejectedSchedulerIssue(
            candidate.issue_key,
            "Issue has unresolved linked bugs: " + ", ".join(candidate.unresolved_linked_bug_keys) + ".",
            SchedulerRejectionKind.LINKED_BUG_BLOCKED,
            candidate.unresolved_linked_bug_keys,
        )
    if candidate.definition_of_ready is None:
        return RejectedSchedulerIssue(
            candidate.issue_key,
            "Definition of Ready decision is missing.",
            SchedulerRejectionKind.DEFINITION_OF_READY_MISSING,
        )
    if not candidate.definition_of_ready.ready:
        return RejectedSchedulerIssue(
            candidate.issue_key,
            "Definition of Ready failed: " + "; ".join(candidate.definition_of_ready.reasons),
            SchedulerRejectionKind.DEFINITION_OF_READY_FAILED,
        )
    return None


def _dependency_graph_blocked_issue_keys(dependency_graph_audit: DependencyGraphAuditResult | None) -> set[str]:
    if dependency_graph_audit is None or dependency_graph_audit.passed:
        return set()
    return set(dependency_graph_audit.blocked_issue_keys)


def _dependency_graph_issue_details(
    issue_key: str,
    dependency_graph_audit: DependencyGraphAuditResult | None,
) -> tuple[str, ...]:
    if dependency_graph_audit is None:
        return ()
    return tuple(
        issue.message
        for issue in dependency_graph_audit.issues
        if issue_key in issue.issue_keys
    )


def _normalize_status(status: str) -> str:
    return " ".join(status.replace("/", " / ").split()).casefold()