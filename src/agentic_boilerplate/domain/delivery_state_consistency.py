"""Jira/GitHub/testing delivery state consistency guard."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum


ACCEPTED_DONE_STATUSES = ("ACCEPTED/DONE", "Accepted/Done")
TEST_COMPLETED_STATUSES = ("TEST COMPLETED", "Test Completed")
PRE_TESTING_STATUSES = (
    "READY TO START",
    "Ready to start",
    "IN PROGRESS",
    "In Progress",
)
EXPECTED_STATUS_AFTER_MERGE = "DEV COMPLETED"


class DeliveryStateConsistencyError(ValueError):
    """Raised when delivery-state consistency input is invalid."""


class PullRequestState(str, Enum):
    """Relevant pull request lifecycle states."""

    MISSING = "missing"
    OPEN = "open"
    MERGED = "merged"
    CLOSED_UNMERGED = "closed-unmerged"


class ReviewApprovalState(str, Enum):
    """Relevant review states for sprint closure consistency."""

    MISSING = "missing"
    PENDING = "pending"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes-requested"
    BLOCKED = "blocked"


class DeliveryStateConsistencyFindingType(str, Enum):
    """Supported delivery-state consistency findings."""

    ACCEPTED_BEFORE_MERGE = "accepted-before-merge"
    ACCEPTED_WITHOUT_REVIEW_APPROVAL = "accepted-without-review-approval"
    ACCEPTED_WITHOUT_TEST_COMPLETION = "accepted-without-test-completion"
    ACCEPTED_WITHOUT_TEST_EVIDENCE = "accepted-without-test-evidence"
    ACCEPTED_WITHOUT_PO_BATCH_ACCEPTANCE = "accepted-without-po-batch-acceptance"
    TEST_COMPLETED_BEFORE_MERGE = "test-completed-before-merge"
    TEST_COMPLETED_WITHOUT_EVIDENCE = "test-completed-without-evidence"
    MERGED_BUT_JIRA_NOT_ADVANCED = "merged-but-jira-not-advanced"
    MERGED_WITHOUT_APPROVED_REVIEW = "merged-without-approved-review"


@dataclass(frozen=True)
class DeliveryWorkItemState:
    """Collected delivery state for one Story or Bug."""

    issue_key: str
    summary: str
    issue_type: str
    jira_status: str
    pull_request_state: PullRequestState
    pull_request_url: str = ""
    review_state: ReviewApprovalState = ReviewApprovalState.MISSING
    tester_validation_passed: bool = False
    test_evidence_paths: tuple[str, ...] = ()
    po_batch_accepted: bool = False
    documented_blocker: str = ""
    documented_blocker_approved: bool = False


@dataclass(frozen=True)
class DeliveryStateConsistencyFinding:
    """One blocking mismatch between Jira, GitHub, review, test, and PO state."""

    issue_key: str
    finding_type: DeliveryStateConsistencyFindingType
    message: str
    actual_status: str
    expected_status: str
    pull_request_url: str = ""
    missing_evidence: tuple[str, ...] = ()
    recommended_transition: str = ""


@dataclass(frozen=True)
class DeliveryStateConsistencyReport:
    """Sprint-level consistency result used before regression or closure."""

    sprint_name: str
    closure_issue_key: str
    checked_issue_count: int
    findings: tuple[DeliveryStateConsistencyFinding, ...]
    ready_issue_keys: tuple[str, ...]

    @property
    def has_blockers(self) -> bool:
        return bool(self.findings)

    @property
    def allowed_to_close(self) -> bool:
        return not self.has_blockers


def evaluate_delivery_state_consistency(
    *,
    sprint_name: str,
    work_items: Sequence[DeliveryWorkItemState],
    closure_issue_key: str = "",
) -> DeliveryStateConsistencyReport:
    """Evaluate Story/Bug state drift before sprint regression or closure."""

    if not sprint_name.strip():
        raise DeliveryStateConsistencyError("sprint_name is required.")
    findings: list[DeliveryStateConsistencyFinding] = []
    ready_issue_keys: list[str] = []
    for item in work_items:
        _validate_work_item(item)
        item_findings = _find_mismatches(item)
        findings.extend(item_findings)
        if not item_findings:
            ready_issue_keys.append(item.issue_key)

    return DeliveryStateConsistencyReport(
        sprint_name=sprint_name.strip(),
        closure_issue_key=closure_issue_key.strip(),
        checked_issue_count=len(work_items),
        findings=tuple(findings),
        ready_issue_keys=tuple(ready_issue_keys),
    )


def render_delivery_state_consistency_report(report: DeliveryStateConsistencyReport) -> str:
    """Render a durable Markdown report for Product Owner and release manager review."""

    lines = [
        f"# Delivery State Consistency - {report.sprint_name}",
        "",
        f"- Closure issue: {report.closure_issue_key or 'not provided'}",
        f"- Checked issues: {report.checked_issue_count}",
        f"- Allowed to close: {'yes' if report.allowed_to_close else 'no'}",
        "",
        "## Blocking Findings",
    ]
    if report.findings:
        for finding in report.findings:
            lines.extend(
                [
                    f"- {finding.issue_key}: {finding.finding_type.value}",
                    f"  - Message: {finding.message}",
                    f"  - Actual status: {finding.actual_status}",
                    f"  - Expected status: {finding.expected_status}",
                    f"  - PR: {finding.pull_request_url or 'not provided'}",
                    f"  - Missing evidence: {', '.join(finding.missing_evidence) or 'none'}",
                    f"  - Recommended transition: {finding.recommended_transition or 'none'}",
                ]
            )
    else:
        lines.append("- None")

    lines.extend(["", "## Clean Issues"])
    if report.ready_issue_keys:
        lines.extend(f"- {issue_key}" for issue_key in report.ready_issue_keys)
    else:
        lines.append("- None")
    return "\n".join(lines) + "\n"


def render_delivery_state_consistency_jira_comment(report: DeliveryStateConsistencyReport) -> str:
    """Render a concise Jira comment for sprint regression or closure Tasks."""

    if report.allowed_to_close:
        return (
            f"Delivery state consistency guard passed for {report.sprint_name}.\n\n"
            f"Checked issues: {report.checked_issue_count}\n"
            f"Blocking findings: 0"
        )
    lines = [
        f"Delivery state consistency guard blocked closure for {report.sprint_name}.",
        "",
        f"Checked issues: {report.checked_issue_count}",
        f"Blocking findings: {len(report.findings)}",
        "",
        "Required follow-up:",
    ]
    for finding in report.findings:
        recommendation = finding.recommended_transition or finding.expected_status
        lines.append(f"- {finding.issue_key}: {finding.message} Recommended: {recommendation}.")
    return "\n".join(lines).strip()


def _find_mismatches(item: DeliveryWorkItemState) -> tuple[DeliveryStateConsistencyFinding, ...]:
    if item.documented_blocker.strip() and item.documented_blocker_approved:
        return ()

    findings: list[DeliveryStateConsistencyFinding] = []
    accepted = _matches(item.jira_status, ACCEPTED_DONE_STATUSES)
    test_completed = _matches(item.jira_status, TEST_COMPLETED_STATUSES)
    pre_testing = _matches(item.jira_status, PRE_TESTING_STATUSES)
    merged = item.pull_request_state == PullRequestState.MERGED
    review_approved = item.review_state == ReviewApprovalState.APPROVED
    has_evidence = bool(item.test_evidence_paths)

    if accepted:
        if not merged:
            findings.append(
                _finding(
                    item,
                    DeliveryStateConsistencyFindingType.ACCEPTED_BEFORE_MERGE,
                    "Story/Bug is accepted before the linked pull request is merged.",
                    expected_status="TEST COMPLETED until Product Owner acceptance can be recorded.",
                    missing_evidence=("merged pull request",),
                    recommended_transition="Return to TEST COMPLETED or IN TESTING until merge/testing is verified.",
                )
            )
        if not review_approved:
            findings.append(
                _finding(
                    item,
                    DeliveryStateConsistencyFindingType.ACCEPTED_WITHOUT_REVIEW_APPROVAL,
                    "Story/Bug is accepted without an approved review record.",
                    expected_status="TEST COMPLETED after approved review and tester validation.",
                    missing_evidence=("approved review record",),
                )
            )
        if not item.tester_validation_passed:
            findings.append(
                _finding(
                    item,
                    DeliveryStateConsistencyFindingType.ACCEPTED_WITHOUT_TEST_COMPLETION,
                    "Story/Bug is accepted before tester validation reached TEST COMPLETED.",
                    expected_status="TEST COMPLETED before Product Owner acceptance.",
                    missing_evidence=("tester validation pass",),
                    recommended_transition="Return to IN TESTING until tester validation is complete.",
                )
            )
        if not has_evidence:
            findings.append(
                _finding(
                    item,
                    DeliveryStateConsistencyFindingType.ACCEPTED_WITHOUT_TEST_EVIDENCE,
                    "Story/Bug is accepted without durable test evidence.",
                    expected_status="TEST COMPLETED with test evidence before Product Owner acceptance.",
                    missing_evidence=("test evidence path",),
                )
            )
        if not item.po_batch_accepted:
            findings.append(
                _finding(
                    item,
                    DeliveryStateConsistencyFindingType.ACCEPTED_WITHOUT_PO_BATCH_ACCEPTANCE,
                    "Story/Bug is accepted without recorded Product Owner batch acceptance.",
                    expected_status="TEST COMPLETED until Product Owner batch acceptance is recorded.",
                    missing_evidence=("Product Owner batch acceptance record",),
                    recommended_transition="Record PO acceptance or return to TEST COMPLETED.",
                )
            )

    if test_completed:
        if not merged:
            findings.append(
                _finding(
                    item,
                    DeliveryStateConsistencyFindingType.TEST_COMPLETED_BEFORE_MERGE,
                    "Story/Bug is TEST COMPLETED before the linked pull request is merged.",
                    expected_status="DEV COMPLETED after review merge, then IN TESTING when tester starts.",
                    missing_evidence=("merged pull request",),
                )
            )
        if not has_evidence:
            findings.append(
                _finding(
                    item,
                    DeliveryStateConsistencyFindingType.TEST_COMPLETED_WITHOUT_EVIDENCE,
                    "Story/Bug is TEST COMPLETED without durable test evidence.",
                    expected_status="TEST COMPLETED with durable evidence.",
                    missing_evidence=("test evidence path",),
                )
            )

    if merged and pre_testing:
        findings.append(
            _finding(
                item,
                DeliveryStateConsistencyFindingType.MERGED_BUT_JIRA_NOT_ADVANCED,
                "Linked pull request is merged while Jira still shows a pre-testing status.",
                expected_status=EXPECTED_STATUS_AFTER_MERGE,
                recommended_transition=EXPECTED_STATUS_AFTER_MERGE,
            )
        )
    if merged and not review_approved:
        findings.append(
            _finding(
                item,
                DeliveryStateConsistencyFindingType.MERGED_WITHOUT_APPROVED_REVIEW,
                "Linked pull request is merged without an approved review record.",
                expected_status="DEV COMPLETED after approved review merge.",
                missing_evidence=("approved review record",),
            )
        )

    return tuple(findings)


def _finding(
    item: DeliveryWorkItemState,
    finding_type: DeliveryStateConsistencyFindingType,
    message: str,
    *,
    expected_status: str,
    missing_evidence: tuple[str, ...] = (),
    recommended_transition: str = "",
) -> DeliveryStateConsistencyFinding:
    return DeliveryStateConsistencyFinding(
        issue_key=item.issue_key,
        finding_type=finding_type,
        message=message,
        actual_status=item.jira_status,
        expected_status=expected_status,
        pull_request_url=item.pull_request_url,
        missing_evidence=missing_evidence,
        recommended_transition=recommended_transition,
    )


def _matches(value: str, options: Sequence[str]) -> bool:
    normalized = value.strip().casefold()
    return any(normalized == option.strip().casefold() for option in options)


def _validate_work_item(item: DeliveryWorkItemState) -> None:
    if not item.issue_key.strip():
        raise DeliveryStateConsistencyError("issue_key is required.")
    if not item.issue_type.strip():
        raise DeliveryStateConsistencyError(f"{item.issue_key}: issue_type is required.")
    if not item.jira_status.strip():
        raise DeliveryStateConsistencyError(f"{item.issue_key}: jira_status is required.")
