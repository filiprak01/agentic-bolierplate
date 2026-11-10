from agentic_boilerplate.domain.sprint_acceptance_gate import (
    GateBlockerKind,
    evaluate_dependency_unblock,
    evaluate_regression_or_release_preparation_gate,
    evaluate_scheduler_assignment_gate,
    render_gate_decision_log,
    PrerequisiteGateInput,
)
from agentic_boilerplate.storage.sprint_acceptance_gate import write_gate_decision_log
from datetime import datetime, timezone


def test_prerequisite_unblocks_after_merge_test_completion_and_no_bugs() -> None:
    decision = evaluate_dependency_unblock(
        PrerequisiteGateInput(
            issue_key="AGENT-39",
            status="TEST COMPLETED",
            merged_to_main=True,
            tester_validated=True,
        )
    )

    assert decision.passed is True
    assert decision.blockers == ()


def test_prerequisite_blocks_when_not_merged_not_tested_or_buggy() -> None:
    decision = evaluate_dependency_unblock(
        PrerequisiteGateInput(
            issue_key="AGENT-39",
            status="DEV COMPLETED",
            merged_to_main=False,
            tester_validated=False,
            unresolved_bug_keys=("AGENT-99",),
        )
    )

    assert decision.passed is False
    assert {blocker.kind for blocker in decision.blockers} == {
        GateBlockerKind.NOT_MERGED_TO_MAIN,
        GateBlockerKind.TESTER_NOT_VALIDATED,
        GateBlockerKind.STATUS_NOT_TECHNICALLY_COMPLETE,
        GateBlockerKind.UNRESOLVED_BLOCKING_BUG,
    }


def test_scheduler_does_not_require_po_acceptance_for_technical_dependencies() -> None:
    decision = evaluate_scheduler_assignment_gate(
        issue_key="AGENT-41",
        prerequisites=(
            PrerequisiteGateInput(
                issue_key="AGENT-37",
                status="TEST COMPLETED",
                merged_to_main=True,
                tester_validated=True,
            ),
        ),
    )

    assert decision.passed is True
    assert "without waiting for sprint-level PO acceptance" in decision.reasons[0]


def test_scheduler_requires_po_acceptance_when_explicitly_requested() -> None:
    decision = evaluate_scheduler_assignment_gate(
        issue_key="AGENT-41",
        dependent_status="TEST COMPLETED",
        po_acceptance_required=True,
        prerequisites=(
            PrerequisiteGateInput(
                issue_key="AGENT-37",
                status="TEST COMPLETED",
                merged_to_main=True,
                tester_validated=True,
            ),
        ),
    )

    assert decision.passed is False
    assert decision.blockers[0].kind is GateBlockerKind.PO_ACCEPTANCE_REQUIRED


def test_regression_and_release_preparation_require_po_scope_acceptance() -> None:
    blocked = evaluate_regression_or_release_preparation_gate(
        scope_key="Sprint 6",
        po_scope_accepted=False,
    )
    allowed = evaluate_regression_or_release_preparation_gate(
        scope_key="Sprint 6",
        po_scope_accepted=True,
    )

    assert blocked.passed is False
    assert blocked.blockers[0].kind is GateBlockerKind.PO_SCOPE_NOT_ACCEPTED
    assert allowed.passed is True


def test_gate_decision_log_records_reasons_and_blockers() -> None:
    decision = evaluate_regression_or_release_preparation_gate(
        scope_key="Sprint 6",
        po_scope_accepted=False,
    )

    log = render_gate_decision_log(decision)

    assert "Gate Decision - Sprint 6" in log
    assert "Passed: no" in log
    assert "po_scope_not_accepted" in log


def test_gate_decision_log_can_be_persisted(tmp_path) -> None:
    decision = evaluate_scheduler_assignment_gate(
        issue_key="AGENT-41",
        prerequisites=(
            PrerequisiteGateInput(
                issue_key="AGENT-131",
                status="TEST COMPLETED",
                merged_to_main=True,
                tester_validated=True,
            ),
        ),
    )

    path = write_gate_decision_log(
        decision,
        tmp_path,
        created_at=datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc),
    )

    assert path.name == "AGENT-41-scheduler_assignment-20260622T120000Z.md"
    assert "Passed: yes" in path.read_text(encoding="utf-8")
