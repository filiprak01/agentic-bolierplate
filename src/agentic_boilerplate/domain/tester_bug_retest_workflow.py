"""Tester failed-test bug linking and retest workflow."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

from agentic_boilerplate.domain.agent_communication import AgentMessage
from agentic_boilerplate.domain.role_handoff_trigger import (
    RoleHandoffTriggerDecision,
    RoleHandoffTriggerInput,
    build_role_handoff_trigger_message,
)
from agentic_boilerplate.domain.story_processing_path_matrix import StoryPathEvent, StoryPathRole
from agentic_boilerplate.domain.tester_manual_test_workflow import (
    ManualTestBugPlan,
    ManualTestExecutionResult,
    ManualTestResultStatus,
    ManualTestWorkflowError,
    ManualTestWorkflowIssue,
    bug_plan_for_failed_manual_test,
    require_valid_manual_test_execution_result,
)


FAILED_TEST_STORY_STATUS = "DEV COMPLETED"
RETEST_PASSED_STORY_STATUS = "TEST COMPLETED"
BUG_RELATED_LABEL = "bug-related"
HAS_LINKED_BUG_LABEL = "has-linked-bug"
BUG_LINK_TYPE = "Blocks"
BUG_LINK_OUTWARD = "blocks"
DEFAULT_RESOLVED_BUG_STATUSES = ("Done", "Resolved", "Closed", "ACCEPTED/DONE")


@dataclass(frozen=True)
class StoryReturnPlan:
    """Jira updates applied to a story after failed manual testing."""

    story_key: str
    target_status: str
    labels_to_add: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class LinkedBugPlan:
    """Bug creation and linking plan for a failed manual test."""

    bug: ManualTestBugPlan
    link_type: str
    outward_relationship: str
    assignee_agent: str
    assignment_reason: str


@dataclass(frozen=True)
class ReworkAssignmentPlan:
    """Developer rework assignment created from failed testing."""

    story_key: str
    bug_keys: tuple[str, ...]
    developer_agent: str
    assignment_reason: str
    failed_acceptance_criteria: tuple[str, ...]
    retest_required: bool = True


@dataclass(frozen=True)
class StoryReworkSnapshot:
    """Story state inspected by the scheduler or Developer Agent."""

    story_key: str
    story_status: str
    labels: tuple[str, ...]
    linked_bugs: tuple["LinkedBugStatus", ...]
    failed_acceptance_criteria: tuple[str, ...] = ()
    original_developer_agent: str = ""


@dataclass(frozen=True)
class LinkedBugStatus:
    """Status snapshot for a Bug linked to a story under retest."""

    bug_key: str
    status: str
    retested: bool = False


@dataclass(frozen=True)
class RetestGateDecision:
    """Decision for whether a story can return to TEST COMPLETED."""

    story_key: str
    can_move_to_test_completed: bool
    target_status: str
    blockers: tuple[str, ...]
    labels_to_remove: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReworkCandidateDecision:
    """Decision for whether a story should be picked up for bug rework."""

    story_key: str
    is_candidate: bool
    unresolved_bug_keys: tuple[str, ...]
    reasons: tuple[str, ...]
    assignment: ReworkAssignmentPlan | None = None


@dataclass(frozen=True)
class FailedTestReworkPlan:
    """Complete workflow plan emitted when manual testing fails."""

    story_return: StoryReturnPlan
    linked_bug: LinkedBugPlan
    rework_assignment: ReworkAssignmentPlan


@dataclass(frozen=True)
class FailedTestBugSignature:
    """Stable duplicate-detection key for one failed test signature."""

    story_key: str
    test_issue_key: str
    failed_acceptance_criteria: tuple[str, ...]

    @property
    def value(self) -> str:
        criteria = "|".join(_normalize_signature_part(item) for item in self.failed_acceptance_criteria)
        return (
            f"{_normalize_signature_part(self.story_key)}:"
            f"{_normalize_signature_part(self.test_issue_key)}:"
            f"{criteria}"
        )


@dataclass(frozen=True)
class FailedTestReworkHandoffPlan:
    """Failed-test Jira-effect plan plus durable Developer rework handoff."""

    rework_plan: FailedTestReworkPlan
    signature: FailedTestBugSignature
    selected_bug_key: str
    handoff_decision: RoleHandoffTriggerDecision

    @property
    def handoff_message(self) -> AgentMessage | None:
        return self.handoff_decision.message


def build_failed_test_rework_plan(
    result: ManualTestExecutionResult,
    *,
    original_developer_agent: str = "",
    fallback_developer_agent: str = "",
    bug_key: str = "",
) -> FailedTestReworkPlan:
    """Build the failed-test handoff plan for Tester and Developer Agents."""

    require_valid_manual_test_execution_result(result)
    if result.status != ManualTestResultStatus.FAILED:
        raise ManualTestWorkflowError(
            [ManualTestWorkflowIssue("status", "Failed-test rework requires a failed manual test result.")]
        )

    bug = bug_plan_for_failed_manual_test(result, create_bug=True)
    if bug is None:
        raise ManualTestWorkflowError([ManualTestWorkflowIssue("bug", "Failed manual testing must create a bug plan.")])

    assignee_agent, assignment_reason = select_rework_developer(
        original_developer_agent=original_developer_agent,
        fallback_developer_agent=fallback_developer_agent,
    )
    bug_keys = (bug_key,) if bug_key else ()
    story_return = StoryReturnPlan(
        story_key=result.story_key,
        target_status=FAILED_TEST_STORY_STATUS,
        labels_to_add=(BUG_RELATED_LABEL, HAS_LINKED_BUG_LABEL),
        reason="manual-test-failed",
    )
    linked_bug = LinkedBugPlan(
        bug=bug,
        link_type=BUG_LINK_TYPE,
        outward_relationship=BUG_LINK_OUTWARD,
        assignee_agent=assignee_agent,
        assignment_reason=assignment_reason,
    )
    rework_assignment = ReworkAssignmentPlan(
        story_key=result.story_key,
        bug_keys=bug_keys,
        developer_agent=assignee_agent,
        assignment_reason=assignment_reason,
        failed_acceptance_criteria=result.failed_acceptance_criteria,
    )
    return FailedTestReworkPlan(
        story_return=story_return,
        linked_bug=linked_bug,
        rework_assignment=rework_assignment,
    )


def failed_test_bug_signature(result: ManualTestExecutionResult) -> FailedTestBugSignature:
    """Build the stable duplicate key used to reuse an existing failed-test Bug."""

    require_valid_manual_test_execution_result(result)
    if result.status != ManualTestResultStatus.FAILED:
        raise ManualTestWorkflowError(
            [ManualTestWorkflowIssue("status", "Failed-test bug signatures require a failed result.")]
        )
    return FailedTestBugSignature(
        story_key=result.story_key,
        test_issue_key=result.test_issue_key,
        failed_acceptance_criteria=result.failed_acceptance_criteria,
    )


def select_failed_test_bug_key(
    result: ManualTestExecutionResult,
    existing_bug_keys_by_signature: dict[str, str] | None = None,
) -> str:
    """Return an existing Bug key when the same failed-test signature was already recorded."""

    signature = failed_test_bug_signature(result).value
    return (existing_bug_keys_by_signature or {}).get(signature, "").strip()


def build_failed_test_rework_handoff_plan(
    result: ManualTestExecutionResult,
    trigger_input: RoleHandoffTriggerInput,
    *,
    original_developer_agent: str = "",
    fallback_developer_agent: str = "",
    existing_bug_keys_by_signature: dict[str, str] | None = None,
    created_bug_key: str = "",
    retest_scope: str = "",
) -> FailedTestReworkHandoffPlan:
    """Build the failed-test Jira plan and durable Developer rework handoff together."""

    selected_bug_key = select_failed_test_bug_key(result, existing_bug_keys_by_signature) or created_bug_key.strip()
    rework_plan = build_failed_test_rework_plan(
        result,
        original_developer_agent=original_developer_agent,
        fallback_developer_agent=fallback_developer_agent,
        bug_key=selected_bug_key,
    )
    signature = failed_test_bug_signature(result)
    artifact_values = dict(trigger_input.artifact_values or {})
    artifact_values.update(
        {
            "linked_bug": selected_bug_key or rework_plan.linked_bug.bug.summary,
            "failed_test_evidence": result.evidence_path or trigger_input.evidence_path,
            "bug_related_labels": ",".join(rework_plan.story_return.labels_to_add),
            "retest_scope": retest_scope.strip() or f"{result.story_key} and linked failed acceptance criteria",
        }
    )
    payload = dict(trigger_input.payload or {})
    payload.update(
        {
            "failed_test_signature": signature.value,
            "selected_bug_key": selected_bug_key,
            "story_return_status": rework_plan.story_return.target_status,
            "labels_to_add": rework_plan.story_return.labels_to_add,
            "failed_acceptance_criteria": result.failed_acceptance_criteria,
            "developer_agent": rework_plan.rework_assignment.developer_agent,
            "assignment_reason": rework_plan.rework_assignment.assignment_reason,
        }
    )
    handoff_input = replace(
        trigger_input,
        current_status="IN TESTING",
        event=StoryPathEvent.TESTING_FAILED,
        actor=StoryPathRole.TESTER,
        target_status=FAILED_TEST_STORY_STATUS,
        artifact_values=artifact_values,
        payload=payload,
    )
    return FailedTestReworkHandoffPlan(
        rework_plan=rework_plan,
        signature=signature,
        selected_bug_key=selected_bug_key,
        handoff_decision=build_role_handoff_trigger_message(handoff_input),
    )


def select_rework_developer(
    *,
    original_developer_agent: str = "",
    fallback_developer_agent: str = "",
) -> tuple[str, str]:
    """Select the developer agent for rework and record why."""

    if original_developer_agent.strip():
        return original_developer_agent.strip(), "original-developer-agent"
    if fallback_developer_agent.strip():
        return fallback_developer_agent.strip(), "fallback-eligible-developer-agent"
    return "", "scheduler-assignment-required"


def evaluate_retest_gate(
    story_key: str,
    linked_bugs: Sequence[LinkedBugStatus],
    *,
    bug_related: bool = True,
    resolved_statuses: Sequence[str] = DEFAULT_RESOLVED_BUG_STATUSES,
) -> RetestGateDecision:
    """Evaluate whether a story with failed-test bugs may move to TEST COMPLETED."""

    if not story_key.strip():
        raise ManualTestWorkflowError([ManualTestWorkflowIssue("story_key", "Value is required.")])
    normalized_resolved = {status.casefold() for status in resolved_statuses}
    blockers: list[str] = []
    if bug_related and not linked_bugs:
        blockers.append("Story is marked bug-related but has no linked Bug status snapshots.")
    for bug in linked_bugs:
        if not bug.bug_key.strip():
            blockers.append("Linked Bug key is required.")
            continue
        if bug.status.casefold() not in normalized_resolved:
            blockers.append(f"{bug.bug_key} is not resolved: {bug.status}")
        elif not bug.retested:
            blockers.append(f"{bug.bug_key} is resolved but not retested.")

    can_move = not blockers
    return RetestGateDecision(
        story_key=story_key,
        can_move_to_test_completed=can_move,
        target_status=RETEST_PASSED_STORY_STATUS if can_move else FAILED_TEST_STORY_STATUS,
        blockers=tuple(blockers),
        labels_to_remove=(BUG_RELATED_LABEL, HAS_LINKED_BUG_LABEL) if can_move else (),
    )


def unresolved_linked_bug_keys(
    linked_bugs: Sequence[LinkedBugStatus],
    *,
    resolved_statuses: Sequence[str] = DEFAULT_RESOLVED_BUG_STATUSES,
) -> tuple[str, ...]:
    """Return linked Bug keys that still require developer rework."""

    normalized_resolved = {status.casefold() for status in resolved_statuses}
    return tuple(
        bug.bug_key
        for bug in linked_bugs
        if bug.bug_key.strip() and bug.status.casefold() not in normalized_resolved
    )


def detect_rework_candidate(
    snapshot: StoryReworkSnapshot,
    *,
    fallback_developer_agent: str = "",
    resolved_statuses: Sequence[str] = DEFAULT_RESOLVED_BUG_STATUSES,
) -> ReworkCandidateDecision:
    """Detect stories that must be picked up for bug rework before new work."""

    if not snapshot.story_key.strip():
        raise ManualTestWorkflowError([ManualTestWorkflowIssue("story_key", "Value is required.")])

    reasons: list[str] = []
    labels = {label.casefold() for label in snapshot.labels}
    if snapshot.story_status.casefold() != FAILED_TEST_STORY_STATUS.casefold():
        reasons.append(f"Story status is {snapshot.story_status}, not {FAILED_TEST_STORY_STATUS}.")
    if BUG_RELATED_LABEL not in labels and HAS_LINKED_BUG_LABEL not in labels:
        reasons.append("Story does not have a bug-related marker label.")

    unresolved_bugs = unresolved_linked_bug_keys(snapshot.linked_bugs, resolved_statuses=resolved_statuses)
    if not unresolved_bugs:
        reasons.append("Story has no unresolved linked Bugs.")

    if reasons:
        return ReworkCandidateDecision(
            story_key=snapshot.story_key,
            is_candidate=False,
            unresolved_bug_keys=unresolved_bugs,
            reasons=tuple(reasons),
        )

    developer_agent, assignment_reason = select_rework_developer(
        original_developer_agent=snapshot.original_developer_agent,
        fallback_developer_agent=fallback_developer_agent,
    )
    assignment = ReworkAssignmentPlan(
        story_key=snapshot.story_key,
        bug_keys=unresolved_bugs,
        developer_agent=developer_agent,
        assignment_reason=assignment_reason,
        failed_acceptance_criteria=snapshot.failed_acceptance_criteria,
    )
    return ReworkCandidateDecision(
        story_key=snapshot.story_key,
        is_candidate=True,
        unresolved_bug_keys=unresolved_bugs,
        reasons=("unresolved-linked-bug-rework",),
        assignment=assignment,
    )


def render_rework_assignment_note(plan: ReworkAssignmentPlan) -> str:
    """Render a Jira-safe rework assignment note."""

    lines = [
        f"Developer rework pickup for {plan.story_key}.",
        f"Assignment reason: {plan.assignment_reason}",
        f"Developer agent: {plan.developer_agent or 'scheduler must assign'}",
        f"Retest required: {'yes' if plan.retest_required else 'no'}",
    ]
    if plan.bug_keys:
        lines.extend(["", "Linked Bugs:"])
        lines.extend(f"- {bug_key}" for bug_key in plan.bug_keys)
    if plan.failed_acceptance_criteria:
        lines.extend(["", "Failed acceptance criteria:"])
        lines.extend(f"- {criterion}" for criterion in plan.failed_acceptance_criteria)
    return "\n".join(lines).strip()


def render_failed_test_handoff_comment(plan: FailedTestReworkPlan) -> str:
    """Render the Tester Agent handoff comment for failed manual testing."""

    lines = [
        f"Manual testing failed for {plan.story_return.story_key}.",
        "",
        f"Move story to: {plan.story_return.target_status}",
        f"Add labels: {', '.join(plan.story_return.labels_to_add)}",
        f"Bug link: {plan.linked_bug.link_type} / {plan.linked_bug.outward_relationship}",
        f"Bug summary: {plan.linked_bug.bug.summary}",
        "",
        plan.linked_bug.bug.description,
        "",
        render_rework_assignment_note(plan.rework_assignment),
    ]
    return "\n".join(lines).strip()


def render_failed_test_rework_handoff_note(plan: FailedTestReworkHandoffPlan) -> str:
    """Render the durable Developer pickup note for a failed-test rework handoff."""

    lines = [
        f"Failed-test Developer rework handoff for {plan.rework_plan.story_return.story_key}.",
        "",
        f"Failure signature: {plan.signature.value}",
        f"Selected Bug: {plan.selected_bug_key or 'create or link from bug plan'}",
        f"Move story to: {plan.rework_plan.story_return.target_status}",
        f"Add labels: {', '.join(plan.rework_plan.story_return.labels_to_add)}",
        f"Developer agent: {plan.rework_plan.rework_assignment.developer_agent or 'scheduler must assign'}",
        f"Assignment reason: {plan.rework_plan.rework_assignment.assignment_reason}",
        f"Handoff allowed: {'yes' if plan.handoff_decision.allowed else 'no'}",
    ]
    if plan.handoff_message:
        lines.extend(
            [
                f"Message id: {plan.handoff_message.id}",
                f"Message type: {plan.handoff_message.message_type.value}",
                f"Target role: {plan.handoff_message.target_role.value if plan.handoff_message.target_role else ''}",
            ]
        )
    if plan.handoff_decision.blockers:
        lines.extend(["", "Handoff blockers:"])
        lines.extend(f"- {blocker}" for blocker in plan.handoff_decision.blockers)
    return "\n".join(lines).strip()


def _normalize_signature_part(value: str) -> str:
    return " ".join(value.strip().casefold().split())
