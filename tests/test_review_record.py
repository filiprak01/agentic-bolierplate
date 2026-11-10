from dataclasses import replace

import pytest

from agentic_boilerplate.domain import (
    AgentRole,
    ReasoningLevel,
    ReviewDecision,
    ReviewFinding,
    ReviewFindingKind,
    ReviewFindingSeverity,
    ReviewFindingStatus,
    ReviewModelRouting,
    ReviewRecord,
    ReviewRecordError,
    ReviewRequestedChange,
    ReviewScope,
    ReviewScopeMode,
    find_repeated_review_findings,
    is_conflict_finding,
    review_finding_fingerprint,
    review_record_from_dict,
    review_record_to_dict,
    require_valid_review_record,
)
from agentic_boilerplate.storage import (
    FileReviewRecordStore,
    InvalidReviewRecordIdError,
    ReviewRecordAlreadyExistsError,
    ReviewRecordNotFoundError,
)


def test_review_record_captures_findings_requested_changes_scope_and_routing() -> None:
    record = _review_record()

    assert require_valid_review_record(record) == record
    assert record.scope.mode == ReviewScopeMode.DIFF_FIRST
    assert record.routing.model == "gpt-5.5"
    assert record.routing.reasoning == ReasoningLevel.MEDIUM
    assert record.findings[0].kind == ReviewFindingKind.MAINTAINABILITY
    assert record.requested_changes[0].finding_id == "finding-001"


def test_review_record_round_trips_through_json_compatible_data() -> None:
    record = _review_record()

    restored = review_record_from_dict(review_record_to_dict(record))

    assert restored == record


def test_expanded_context_review_requires_reason_and_paths() -> None:
    record = replace(
        _review_record(),
        scope=ReviewScope(
            mode=ReviewScopeMode.EXPANDED_CONTEXT,
            changed_files=("src/app.py",),
        ),
    )

    with pytest.raises(ReviewRecordError) as exc:
        require_valid_review_record(record)

    assert "scope.expansion_reason" in str(exc.value)
    assert "scope.expanded_context_paths" in str(exc.value)


def test_repeated_review_findings_are_detected_by_stable_fingerprint() -> None:
    previous = _review_record()
    current = replace(
        _review_record(record_id="review-002"),
        findings=(
            ReviewFinding(
                id="finding-002",
                title="Extract duplicate branch-name formatting",
                description="Same issue found again.",
                kind=ReviewFindingKind.MAINTAINABILITY,
                severity=ReviewFindingSeverity.MEDIUM,
                file_path="src/agentic_boilerplate/domain/developer_branch_workflow.py",
                line=42,
            ),
        ),
        requested_changes=(),
    )

    repeated = find_repeated_review_findings(current, (previous,))

    assert len(repeated) == 1
    assert repeated[0].previous_record_id == "review-001"
    assert repeated[0].previous_finding_id == "finding-001"
    assert repeated[0].fingerprint == review_finding_fingerprint(previous.findings[0])


def test_wont_fix_previous_findings_do_not_repeat() -> None:
    previous = replace(
        _review_record(),
        findings=(replace(_review_record().findings[0], status=ReviewFindingStatus.WONT_FIX),),
    )
    current = replace(_review_record(record_id="review-002"), requested_changes=())

    assert find_repeated_review_findings(current, (previous,)) == ()


def test_conflict_findings_are_review_findings_not_bugs() -> None:
    finding = ReviewFinding(
        id="conflict-001",
        title="Merge conflict in workflow file",
        description="Developer branch must rebase before review can continue.",
        kind=ReviewFindingKind.CONFLICT,
        severity=ReviewFindingSeverity.BLOCKING,
        file_path="src/agentic_boilerplate/domain/developer_pr_workflow.py",
    )

    assert is_conflict_finding(finding) is True
    finding_data = review_record_to_dict(replace(_review_record(), findings=(finding,), requested_changes=()))[
        "findings"
    ][0]
    assert finding_data["kind"] == ReviewFindingKind.CONFLICT.value
    assert "bug_issue_key" not in finding_data


def test_file_review_record_store_creates_reads_lists_and_updates(tmp_path) -> None:
    store = FileReviewRecordStore(tmp_path)
    record = _review_record()

    location = store.create(record)
    updated = replace(record, final_decision=ReviewDecision.APPROVED, updated_at="2026-07-03T16:20:00Z")
    store.write(updated)

    assert location.path == tmp_path / "review-001" / "review-record.json"
    assert store.read("review-001") == updated
    assert store.list_records() == (updated,)


def test_file_review_record_store_rejects_duplicate_missing_and_unsafe_ids(tmp_path) -> None:
    store = FileReviewRecordStore(tmp_path)
    record = _review_record()

    store.create(record)

    with pytest.raises(ReviewRecordAlreadyExistsError):
        store.create(record)
    with pytest.raises(InvalidReviewRecordIdError):
        store.read("../unsafe")
    with pytest.raises(ReviewRecordNotFoundError):
        store.read("missing")


def _review_record(record_id: str = "review-001") -> ReviewRecord:
    finding = ReviewFinding(
        id="finding-001",
        title="Extract duplicate branch-name formatting",
        description="Branch-name formatting is duplicated and should reuse the existing helper.",
        kind=ReviewFindingKind.MAINTAINABILITY,
        severity=ReviewFindingSeverity.MEDIUM,
        file_path="src/agentic_boilerplate/domain/developer_branch_workflow.py",
        line=42,
    )
    requested_change = ReviewRequestedChange(
        id="change-001",
        finding_id="finding-001",
        request="Use the shared branch-name helper before approval.",
    )
    return ReviewRecord(
        id=record_id,
        jira_issue_key="AGENT-47",
        pull_request_url="https://github.com/example-org/agentic-boilerplate/pull/47",
        pull_request_number=47,
        head_branch="feature/AGENT-47-review-record-finding-tracker",
        base_branch="main",
        head_sha="abc1234",
        reviewer=AgentRole.REVIEW,
        scope=ReviewScope(
            mode=ReviewScopeMode.DIFF_FIRST,
            changed_files=("src/agentic_boilerplate/domain/developer_branch_workflow.py",),
            related_tests=("tests/test_developer_branch_workflow.py",),
        ),
        routing=ReviewModelRouting(
            model="gpt-5.5",
            reasoning=ReasoningLevel.MEDIUM,
            speed="normal",
            rationale="Diff-first checklist review with no security or architecture expansion.",
        ),
        final_decision=ReviewDecision.CHANGES_REQUESTED,
        created_at="2026-07-03T16:00:00Z",
        updated_at="2026-07-03T16:10:00Z",
        findings=(finding,),
        requested_changes=(requested_change,),
    )
