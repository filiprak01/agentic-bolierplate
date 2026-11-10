"""Jira status transition policy for review and testing workflows."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from agentic_boilerplate.domain.tester_bug_retest_workflow import (
    BUG_RELATED_LABEL,
    FAILED_TEST_STORY_STATUS,
    HAS_LINKED_BUG_LABEL,
    RETEST_PASSED_STORY_STATUS,
)


DEV_COMPLETED_STATUS = FAILED_TEST_STORY_STATUS
IN_TESTING_STATUS = "IN TESTING"
TEST_COMPLETED_STATUS = RETEST_PASSED_STORY_STATUS
PO_ACCEPTED_STATUS = "ACCEPTED/DONE"
DEFAULT_SUBTASK_DONE_STATUS = "ACCEPTED/DONE"
TEST_CASE_DEFAULT_STATUS = "FUNNEL"


class JiraWorkflowIssueType(str, Enum):
    """Issue types covered by the transition policy."""

    STORY = "Story"
    BUG = "Bug"
    TEST = "Test"
    SUBTASK = "Subtask"


class JiraWorkflowActor(str, Enum):
    """Actors that may request workflow transitions."""

    DEVELOPER = "developer"
    REVIEW = "review"
    TESTER = "tester"
    PRODUCT_OWNER = "product-owner"
    RELEASE_MANAGER = "release-manager"
    STORY_AGENT = "story-agent"


@dataclass(frozen=True)
class JiraStatusTransitionRequest:
    """Requested Jira status transition with the evidence flags needed by policy."""

    issue_key: str
    issue_type: JiraWorkflowIssueType
    current_status: str
    target_status: str
    actor: JiraWorkflowActor
    merged_to_main: bool = False
    review_passed: bool = False
    tests_passed: bool | None = None
    linked_bug_keys: tuple[str, ...] = ()
    unresolved_linked_bug_keys: tuple[str, ...] = ()
    retested_bug_keys: tuple[str, ...] = ()
    linked_test_case_keys: tuple[str, ...] = ()
    test_case_coverage_ready: bool | None = None
    one_time_validation_labeled: bool = False
    one_time_validation_explained: bool = False
    developer_validation_passed: bool = False
    po_approved: bool = False
    explicit_testing_subtask: bool = False


@dataclass(frozen=True)
class JiraStatusTransitionDecision:
    """Allowed or blocked status transition decision."""

    issue_key: str
    allowed: bool
    target_status: str
    blockers: tuple[str, ...] = ()
    labels_to_add: tuple[str, ...] = ()
    labels_to_remove: tuple[str, ...] = ()


def decide_jira_status_transition(request: JiraStatusTransitionRequest) -> JiraStatusTransitionDecision:
    """Decide whether the requested review/testing transition is allowed."""

    blockers = _common_transition_blockers(request)
    target = _normalize_status(request.target_status)
    issue_type = request.issue_type

    if issue_type == JiraWorkflowIssueType.TEST:
        blockers.extend(_test_issue_blockers(request))
    elif target == _normalize_status(IN_TESTING_STATUS):
        blockers.extend(_in_testing_blockers(request))
    elif target == _normalize_status(TEST_COMPLETED_STATUS):
        blockers.extend(_test_completed_blockers(request))
    elif target == _normalize_status(DEV_COMPLETED_STATUS):
        blockers.extend(_dev_completed_blockers(request))
    elif target == _normalize_status(PO_ACCEPTED_STATUS):
        blockers.extend(_accepted_done_blockers(request))
    else:
        blockers.append(f"Unsupported target status: {request.target_status}")

    allowed = not blockers
    labels_to_add: tuple[str, ...] = ()
    labels_to_remove: tuple[str, ...] = ()
    if allowed and target == _normalize_status(DEV_COMPLETED_STATUS) and request.tests_passed is False:
        labels_to_add = (BUG_RELATED_LABEL, HAS_LINKED_BUG_LABEL)
    if allowed and target == _normalize_status(TEST_COMPLETED_STATUS):
        labels_to_remove = (BUG_RELATED_LABEL, HAS_LINKED_BUG_LABEL)

    return JiraStatusTransitionDecision(
        issue_key=request.issue_key,
        allowed=allowed,
        target_status=request.target_status,
        blockers=tuple(blockers),
        labels_to_add=labels_to_add,
        labels_to_remove=labels_to_remove,
    )


def closest_subtask_done_status(available_statuses: Sequence[str]) -> str:
    """Return the closest done-like status for developer subtasks."""

    if not available_statuses:
        return DEFAULT_SUBTASK_DONE_STATUS
    normalized = {_normalize_status(status): status for status in available_statuses}
    for preferred in (PO_ACCEPTED_STATUS, "Accepted/Done", "Done", "Closed"):
        status = normalized.get(_normalize_status(preferred))
        if status:
            return status
    return DEFAULT_SUBTASK_DONE_STATUS


def render_jira_status_transition_decision(decision: JiraStatusTransitionDecision) -> str:
    """Render a concise Jira note for transition decisions."""

    lines = [
        f"Transition decision for {decision.issue_key}: {'allowed' if decision.allowed else 'blocked'}",
        f"Target status: {decision.target_status}",
    ]
    if decision.labels_to_add:
        lines.append(f"Labels to add: {', '.join(decision.labels_to_add)}")
    if decision.labels_to_remove:
        lines.append(f"Labels to remove: {', '.join(decision.labels_to_remove)}")
    if decision.blockers:
        lines.extend(["", "Blockers:"])
        lines.extend(f"- {blocker}" for blocker in decision.blockers)
    return "\n".join(lines).strip()


def _common_transition_blockers(request: JiraStatusTransitionRequest) -> list[str]:
    blockers: list[str] = []
    if not request.issue_key.strip():
        blockers.append("Issue key is required.")
    if not request.current_status.strip():
        blockers.append("Current status is required.")
    if not request.target_status.strip():
        blockers.append("Target status is required.")
    return blockers


def _test_issue_blockers(request: JiraStatusTransitionRequest) -> list[str]:
    blockers: list[str] = []
    if _normalize_status(request.target_status) != _normalize_status(TEST_CASE_DEFAULT_STATUS):
        blockers.append("Jira Test issues remain in FUNNEL; execution pass/fail belongs to Test Execution records.")
    return blockers


def _in_testing_blockers(request: JiraStatusTransitionRequest) -> list[str]:
    blockers: list[str] = []
    if request.actor != JiraWorkflowActor.TESTER:
        blockers.append("Only Tester Agent moves merged work to IN TESTING.")
    if request.issue_type not in (JiraWorkflowIssueType.STORY, JiraWorkflowIssueType.BUG):
        blockers.append("Only Story or Bug issues move to IN TESTING through tester workflow.")
    if _normalize_status(request.current_status) != _normalize_status(DEV_COMPLETED_STATUS):
        blockers.append("Tester starts only from DEV COMPLETED after review merge handoff.")
    if not request.merged_to_main:
        blockers.append("Work must be merged to main before IN TESTING.")
    if not request.review_passed:
        blockers.append("Review must pass before IN TESTING.")
    return blockers


def _test_completed_blockers(request: JiraStatusTransitionRequest) -> list[str]:
    blockers: list[str] = []
    if request.actor != JiraWorkflowActor.TESTER:
        blockers.append("Only Tester Agent moves work to TEST COMPLETED.")
    if request.issue_type == JiraWorkflowIssueType.SUBTASK and not request.explicit_testing_subtask:
        blockers.append("Development subtasks do not move to TEST COMPLETED.")
    elif request.issue_type not in (
        JiraWorkflowIssueType.STORY,
        JiraWorkflowIssueType.BUG,
        JiraWorkflowIssueType.SUBTASK,
    ):
        blockers.append("Only Story, Bug, or explicit testing Subtask issues can move to TEST COMPLETED.")
    if request.tests_passed is not True:
        blockers.append("Passing tester validation is required for TEST COMPLETED.")
    if request.unresolved_linked_bug_keys:
        blockers.append(
            "Linked Bugs must be resolved and retested before TEST COMPLETED: "
            + ", ".join(request.unresolved_linked_bug_keys)
        )
    missing_retests = tuple(
        bug_key for bug_key in request.linked_bug_keys if bug_key not in set(request.retested_bug_keys)
    )
    if missing_retests:
        blockers.append("Linked Bugs must be retested before TEST COMPLETED: " + ", ".join(missing_retests))
    if request.one_time_validation_labeled:
        if not request.one_time_validation_explained:
            blockers.append(
                "One-time-validation stories may skip reusable Test Case creation only when evidence explains why."
            )
        return blockers
    if not request.linked_test_case_keys:
        blockers.append("At least one linked AgileTest-style Test Case is required before TEST COMPLETED.")
    if request.test_case_coverage_ready is not True:
        blockers.append(
            "Linked Test Case coverage must include scenario steps or automated coverage mapping before TEST COMPLETED."
        )
    return blockers


def _dev_completed_blockers(request: JiraStatusTransitionRequest) -> list[str]:
    blockers: list[str] = []
    if request.actor != JiraWorkflowActor.TESTER:
        blockers.append("Only Tester Agent returns failed testing to DEV COMPLETED.")
    if request.issue_type not in (JiraWorkflowIssueType.STORY, JiraWorkflowIssueType.BUG):
        blockers.append("Only Story or Bug issues return to DEV COMPLETED from failed testing.")
    if request.tests_passed is not False:
        blockers.append("Failed tester validation is required to return work to DEV COMPLETED.")
    if not request.linked_bug_keys:
        blockers.append("Failed testing must create or link at least one Bug.")
    return blockers


def _accepted_done_blockers(request: JiraStatusTransitionRequest) -> list[str]:
    blockers: list[str] = []
    if request.issue_type == JiraWorkflowIssueType.SUBTASK:
        if request.actor != JiraWorkflowActor.DEVELOPER:
            blockers.append("Developer subtasks are completed by Developer Agent after developer validation.")
        if not request.developer_validation_passed:
            blockers.append("Developer validation must pass before subtask done.")
        return blockers
    if request.actor == JiraWorkflowActor.PRODUCT_OWNER:
        if not request.po_approved:
            blockers.append("PO approval flag is required for ACCEPTED/DONE.")
        return blockers
    if request.actor not in (JiraWorkflowActor.RELEASE_MANAGER, JiraWorkflowActor.STORY_AGENT):
        blockers.append("Only Product Owner, Release Manager, or Story Agent can move tested work to ACCEPTED/DONE.")
        return blockers
    if _normalize_status(request.current_status) != _normalize_status(TEST_COMPLETED_STATUS):
        blockers.append("Agent acceptance requires current status TEST COMPLETED.")
    if request.tests_passed is not True:
        blockers.append("Agent acceptance requires passing tester validation.")
    if request.unresolved_linked_bug_keys:
        blockers.append(
            "Agent acceptance requires no unresolved linked Bugs: " + ", ".join(request.unresolved_linked_bug_keys)
        )
    if not request.linked_test_case_keys and not (
        request.one_time_validation_labeled and request.one_time_validation_explained
    ):
        blockers.append("Agent acceptance requires linked Test Case coverage or explained one-time validation.")
    if request.test_case_coverage_ready is not True and not (
        request.one_time_validation_labeled and request.one_time_validation_explained
    ):
        blockers.append("Agent acceptance requires PO-visible Test Case coverage.")
    return blockers


def _normalize_status(status: str) -> str:
    return status.casefold().replace("/", " ").replace("_", " ").strip()
