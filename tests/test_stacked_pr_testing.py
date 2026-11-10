import pytest

from agentic_boilerplate.domain import (
    ManualTestExecutionResult,
    ManualTestResultStatus,
    ManualTestWorkflowError,
    StackedBugMetadata,
    StackedTestEvidenceFinality,
    StackedTestingAvailability,
    StackedTestingContext,
    bug_plan_for_failed_stacked_test,
    build_stacked_test_evidence_record,
    evaluate_stacked_testing_availability,
    mark_stacked_evidence_stale,
    stacked_evidence_records_for_regression,
    stacked_test_evidence_record_to_dict,
)


def test_stacked_testing_classifies_default_pre_merge_story_as_wait_for_merge() -> None:
    decision = evaluate_stacked_testing_availability(
        StackedTestingContext(
            **{
                **_stacked_context().__dict__,
                "stack_testable_before_merge": False,
                "merged_to_main_or_release": False,
            }
        )
    )

    assert decision.availability is StackedTestingAvailability.WAIT_FOR_MERGE
    assert decision.evidence_finality is StackedTestEvidenceFinality.PROVISIONAL
    assert "Wait for merge" in decision.required_actions[0]


def test_stacked_testing_waits_for_lower_layer_before_parallel_testing() -> None:
    decision = evaluate_stacked_testing_availability(
        StackedTestingContext(
            **{
                **_stacked_context().__dict__,
                "stack_testable_before_merge": True,
                "stable_branch_or_preview_available": True,
                "lower_layers_passed": False,
            }
        )
    )

    assert decision.availability is StackedTestingAvailability.WAIT_FOR_LOWER_LAYER
    assert decision.evidence_finality is StackedTestEvidenceFinality.PROVISIONAL


def test_stacked_testing_allows_provisional_early_testing_with_stable_preview() -> None:
    context = StackedTestingContext(
        **{
            **_stacked_context().__dict__,
            "stack_testable_before_merge": True,
            "stable_branch_or_preview_available": True,
        }
    )

    decision = evaluate_stacked_testing_availability(context)
    evidence = build_stacked_test_evidence_record(
        context=context,
        test_issue_key="AGENT-951",
        decision=decision,
        evidence_path="data/agent-logs/AGENT-691/test-evidence.md",
    )

    payload = stacked_test_evidence_record_to_dict(evidence)

    assert decision.availability is StackedTestingAvailability.TESTABLE_NOW
    assert evidence.finality is StackedTestEvidenceFinality.PROVISIONAL
    assert payload["stack_id"] == "r12-s7-stack-core"
    assert payload["base_sha"] == "base-sha"
    assert payload["head_sha"] == "head-sha"
    assert payload["acceptance_criteria_covered"] == ["AC 1", "AC 2"]


def test_stacked_testing_after_merge_produces_final_evidence() -> None:
    context = StackedTestingContext(
        **{
            **_stacked_context().__dict__,
            "merged_to_main_or_release": True,
        }
    )

    decision = evaluate_stacked_testing_availability(context)
    evidence = build_stacked_test_evidence_record(
        context=context,
        test_issue_key="AGENT-951",
        decision=decision,
    )

    assert decision.availability is StackedTestingAvailability.TESTABLE_NOW
    assert evidence.finality is StackedTestEvidenceFinality.FINAL


def test_stacked_testing_marks_evidence_stale_when_lower_layer_changes() -> None:
    decision = evaluate_stacked_testing_availability(
        StackedTestingContext(
            **{
                **_stacked_context().__dict__,
                "lower_layer_recorded_head_sha": "old-lower",
                "lower_layer_current_head_sha": "new-lower",
            }
        )
    )

    assert decision.availability is StackedTestingAvailability.STALE_RETEST_REQUIRED
    assert decision.evidence_finality is StackedTestEvidenceFinality.STALE

    fresh = build_stacked_test_evidence_record(
        context=StackedTestingContext(
            **{
                **_stacked_context().__dict__,
                "merged_to_main_or_release": True,
            }
        ),
        test_issue_key="AGENT-951",
        decision=evaluate_stacked_testing_availability(
            StackedTestingContext(
                **{
                    **_stacked_context().__dict__,
                    "merged_to_main_or_release": True,
                }
            )
        ),
    )
    stale = mark_stacked_evidence_stale(fresh, stale_reason="Lower layer AGENT-690 changed.")

    assert stale.finality is StackedTestEvidenceFinality.STALE
    assert stale.stale_reason == "Lower layer AGENT-690 changed."


def test_regression_selection_excludes_provisional_and_stale_evidence_by_default() -> None:
    context = _stacked_context()
    final_decision = evaluate_stacked_testing_availability(
        StackedTestingContext(**{**context.__dict__, "merged_to_main_or_release": True})
    )
    provisional_decision = evaluate_stacked_testing_availability(
        StackedTestingContext(
            **{
                **context.__dict__,
                "stack_testable_before_merge": True,
                "stable_branch_or_preview_available": True,
            }
        )
    )
    final = build_stacked_test_evidence_record(
        context=StackedTestingContext(**{**context.__dict__, "merged_to_main_or_release": True}),
        test_issue_key="AGENT-951",
        decision=final_decision,
    )
    provisional = build_stacked_test_evidence_record(
        context=StackedTestingContext(
            **{
                **context.__dict__,
                "stack_testable_before_merge": True,
                "stable_branch_or_preview_available": True,
            }
        ),
        test_issue_key="AGENT-952",
        decision=provisional_decision,
    )
    stale = mark_stacked_evidence_stale(final, stale_reason="Lower layer changed.")

    default_records = stacked_evidence_records_for_regression((final, provisional, stale))
    po_approved_records = stacked_evidence_records_for_regression(
        (final, provisional, stale),
        include_provisional_with_po_approval=True,
    )

    assert default_records == (final,)
    assert po_approved_records == (final, provisional)


def test_failed_stacked_testing_bug_plan_contains_stack_metadata() -> None:
    result = ManualTestExecutionResult(
        story_key="AGENT-691",
        test_issue_key="AGENT-951",
        status=ManualTestResultStatus.FAILED,
        tester_role="tester",
        executed_at="2026-08-13T14:00:00Z",
        test_execution_key="AGENT-952",
        failed_acceptance_criteria=("AC 3",),
    )
    metadata = StackedBugMetadata(
        story_key="AGENT-691",
        test_issue_key="AGENT-951",
        stack_id="r12-s7-stack-core",
        stack_layer=2,
        branch_name="feature/AGENT-691-tester-stacked-pr-workflow",
        base_sha="base-sha",
        head_sha="head-sha",
        evidence_path="data/agent-logs/AGENT-691/test-evidence.md",
    )

    bug_plan = bug_plan_for_failed_stacked_test(result, metadata, create_bug=True)

    assert bug_plan is not None
    assert "Stacked PR metadata:" in bug_plan.description
    assert "Stack ID: r12-s7-stack-core" in bug_plan.description
    assert "Head SHA: head-sha" in bug_plan.description


def test_failed_stacked_testing_bug_metadata_must_match_result() -> None:
    result = ManualTestExecutionResult(
        story_key="AGENT-691",
        test_issue_key="AGENT-951",
        status=ManualTestResultStatus.FAILED,
        tester_role="tester",
        executed_at="2026-08-13T14:00:00Z",
        test_execution_key="AGENT-952",
        failed_acceptance_criteria=("AC 3",),
    )
    metadata = StackedBugMetadata(
        story_key="AGENT-999",
        test_issue_key="AGENT-951",
        stack_id="r12-s7-stack-core",
        stack_layer=2,
        branch_name="feature/AGENT-691-tester-stacked-pr-workflow",
        base_sha="base-sha",
        head_sha="head-sha",
    )

    with pytest.raises(ManualTestWorkflowError) as exc:
        bug_plan_for_failed_stacked_test(result, metadata, create_bug=True)

    assert "story key must match" in str(exc.value)


def test_stacked_testing_missing_preview_context_blocks_for_po() -> None:
    decision = evaluate_stacked_testing_availability(
        StackedTestingContext(
            **{
                **_stacked_context().__dict__,
                "stack_testable_before_merge": True,
                "stable_branch_or_preview_available": False,
                "environment_name": "",
                "preview_url": "",
            }
        )
    )

    assert decision.availability is StackedTestingAvailability.BLOCKED_NEEDS_PO
    assert "environment" in decision.blockers[0]


def test_stacked_evidence_requires_testable_decision() -> None:
    with pytest.raises(ManualTestWorkflowError) as exc:
        build_stacked_test_evidence_record(
            context=_stacked_context(),
            test_issue_key="AGENT-951",
            decision=evaluate_stacked_testing_availability(_stacked_context()),
        )

    assert "availability" in str(exc.value)


def _stacked_context() -> StackedTestingContext:
    return StackedTestingContext(
        story_key="AGENT-691",
        stack_id="r12-s7-stack-core",
        stack_layer=2,
        branch_name="feature/AGENT-691-tester-stacked-pr-workflow",
        base_sha="base-sha",
        head_sha="head-sha",
        acceptance_criteria=("AC 1", "AC 2"),
        environment_name="local-preview",
        preview_url="http://localhost:5173/preview/AGENT-691",
    )
