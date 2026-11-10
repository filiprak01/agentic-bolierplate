"""Tester Agent rules for stacked pull request testing."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum

from agentic_boilerplate.domain.tester_manual_test_workflow import (
    ManualTestBugPlan,
    ManualTestExecutionResult,
    ManualTestWorkflowError,
    ManualTestWorkflowIssue,
    bug_plan_for_failed_manual_test,
)


class StackedTestingAvailability(str, Enum):
    """Tester Agent availability classification for a stacked PR story."""

    TESTABLE_NOW = "testable-now"
    WAIT_FOR_LOWER_LAYER = "wait-for-lower-layer"
    WAIT_FOR_MERGE = "wait-for-merge"
    STALE_RETEST_REQUIRED = "stale-retest-required"
    BLOCKED_NEEDS_PO = "blocked-needs-po"


class StackedTestEvidenceFinality(str, Enum):
    """Whether stacked PR test evidence can count for release acceptance."""

    FINAL = "final"
    PROVISIONAL = "provisional"
    STALE = "stale"


@dataclass(frozen=True)
class StackedTestingContext:
    """Inputs used to classify whether Tester Agent can test a stacked story."""

    story_key: str
    stack_id: str
    stack_layer: int
    branch_name: str
    base_sha: str
    head_sha: str
    acceptance_criteria: tuple[str, ...]
    environment_name: str = ""
    preview_url: str = ""
    stack_testable_before_merge: bool = False
    stable_branch_or_preview_available: bool = False
    lower_layers_passed: bool = True
    merged_to_main_or_release: bool = False
    lower_layer_recorded_head_sha: str = ""
    lower_layer_current_head_sha: str = ""


@dataclass(frozen=True)
class StackedTestingDecision:
    """Tester Agent decision for one stacked PR story."""

    story_key: str
    availability: StackedTestingAvailability
    evidence_finality: StackedTestEvidenceFinality
    blockers: tuple[str, ...] = field(default_factory=tuple)
    required_actions: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class StackedTestEvidenceRecord:
    """Durable stacked testing evidence metadata."""

    story_key: str
    test_issue_key: str
    stack_id: str
    stack_layer: int
    branch_name: str
    base_sha: str
    head_sha: str
    environment_name: str
    acceptance_criteria_covered: tuple[str, ...]
    finality: StackedTestEvidenceFinality
    preview_url: str = ""
    evidence_path: str = ""
    stale_reason: str = ""


@dataclass(frozen=True)
class StackedBugMetadata:
    """Stack metadata that must be included on bugs found during stacked PR testing."""

    story_key: str
    test_issue_key: str
    stack_id: str
    stack_layer: int
    branch_name: str
    base_sha: str
    head_sha: str
    evidence_path: str = ""
    preview_url: str = ""


def evaluate_stacked_testing_availability(context: StackedTestingContext) -> StackedTestingDecision:
    """Classify if Tester Agent can test a stacked story now."""

    issues = _validate_stacked_testing_context(context)
    if issues:
        return StackedTestingDecision(
            story_key=context.story_key.strip(),
            availability=StackedTestingAvailability.BLOCKED_NEEDS_PO,
            evidence_finality=StackedTestEvidenceFinality.PROVISIONAL,
            blockers=tuple(f"{issue.field}: {issue.message}" for issue in issues),
            required_actions=("Ask Product Owner or Orchestrator to provide missing stacked testing context.",),
        )

    if _lower_layer_changed(context):
        return StackedTestingDecision(
            story_key=context.story_key.strip(),
            availability=StackedTestingAvailability.STALE_RETEST_REQUIRED,
            evidence_finality=StackedTestEvidenceFinality.STALE,
            blockers=("Lower stack layer changed after this evidence was produced.",),
            required_actions=("Retest after Developer Agent rebases or refreshes the stacked layer.",),
        )

    if context.merged_to_main_or_release:
        return StackedTestingDecision(
            story_key=context.story_key.strip(),
            availability=StackedTestingAvailability.TESTABLE_NOW,
            evidence_finality=StackedTestEvidenceFinality.FINAL,
        )

    if not context.stack_testable_before_merge:
        return StackedTestingDecision(
            story_key=context.story_key.strip(),
            availability=StackedTestingAvailability.WAIT_FOR_MERGE,
            evidence_finality=StackedTestEvidenceFinality.PROVISIONAL,
            required_actions=("Wait for merge to main or release branch before functional testing.",),
        )

    if not context.lower_layers_passed:
        return StackedTestingDecision(
            story_key=context.story_key.strip(),
            availability=StackedTestingAvailability.WAIT_FOR_LOWER_LAYER,
            evidence_finality=StackedTestEvidenceFinality.PROVISIONAL,
            required_actions=("Wait for lower stacked layers to pass review/testing.",),
        )

    if not context.stable_branch_or_preview_available:
        return StackedTestingDecision(
            story_key=context.story_key.strip(),
            availability=StackedTestingAvailability.BLOCKED_NEEDS_PO,
            evidence_finality=StackedTestEvidenceFinality.PROVISIONAL,
            blockers=("Early stacked testing requires a stable branch or preview environment.",),
            required_actions=("Ask Product Owner or Orchestrator to confirm the preview/testing environment.",),
        )

    return StackedTestingDecision(
        story_key=context.story_key.strip(),
        availability=StackedTestingAvailability.TESTABLE_NOW,
        evidence_finality=StackedTestEvidenceFinality.PROVISIONAL,
        required_actions=("Record evidence as provisional until the story is merged and retested or confirmed.",),
    )


def build_stacked_test_evidence_record(
    *,
    context: StackedTestingContext,
    test_issue_key: str,
    decision: StackedTestingDecision,
    evidence_path: str = "",
) -> StackedTestEvidenceRecord:
    """Create durable stacked testing evidence metadata."""

    if decision.availability != StackedTestingAvailability.TESTABLE_NOW:
        raise ManualTestWorkflowError(
            [
                ManualTestWorkflowIssue(
                    "availability",
                    "Stacked test evidence can be created only when the story is testable now.",
                )
            ]
        )
    _require_text_or_raise("test_issue_key", test_issue_key)
    return StackedTestEvidenceRecord(
        story_key=context.story_key.strip(),
        test_issue_key=test_issue_key.strip(),
        stack_id=context.stack_id.strip(),
        stack_layer=context.stack_layer,
        branch_name=context.branch_name.strip(),
        base_sha=context.base_sha.strip(),
        head_sha=context.head_sha.strip(),
        environment_name=context.environment_name.strip() or "not set",
        preview_url=context.preview_url.strip(),
        acceptance_criteria_covered=tuple(criterion.strip() for criterion in context.acceptance_criteria),
        finality=decision.evidence_finality,
        evidence_path=evidence_path.strip(),
    )


def mark_stacked_evidence_stale(
    record: StackedTestEvidenceRecord,
    *,
    stale_reason: str,
) -> StackedTestEvidenceRecord:
    """Return a record that no longer counts for release acceptance."""

    _require_text_or_raise("stale_reason", stale_reason)
    return StackedTestEvidenceRecord(
        story_key=record.story_key,
        test_issue_key=record.test_issue_key,
        stack_id=record.stack_id,
        stack_layer=record.stack_layer,
        branch_name=record.branch_name,
        base_sha=record.base_sha,
        head_sha=record.head_sha,
        environment_name=record.environment_name,
        acceptance_criteria_covered=record.acceptance_criteria_covered,
        finality=StackedTestEvidenceFinality.STALE,
        preview_url=record.preview_url,
        evidence_path=record.evidence_path,
        stale_reason=stale_reason.strip(),
    )


def stacked_evidence_records_for_regression(
    records: Sequence[StackedTestEvidenceRecord],
    *,
    include_provisional_with_po_approval: bool = False,
) -> tuple[StackedTestEvidenceRecord, ...]:
    """Return stacked evidence that may feed release regression manifests."""

    selected: list[StackedTestEvidenceRecord] = []
    for record in records:
        if record.finality == StackedTestEvidenceFinality.FINAL:
            selected.append(record)
        elif include_provisional_with_po_approval and record.finality == StackedTestEvidenceFinality.PROVISIONAL:
            selected.append(record)
    return tuple(selected)


def bug_plan_for_failed_stacked_test(
    result: ManualTestExecutionResult,
    metadata: StackedBugMetadata,
    *,
    create_bug: bool,
) -> ManualTestBugPlan | None:
    """Create a failed-test bug plan with required stacked PR metadata."""

    bug_plan = bug_plan_for_failed_manual_test(result, create_bug=create_bug)
    if bug_plan is None:
        return None
    _require_text_or_raise("story_key", metadata.story_key)
    _require_text_or_raise("test_issue_key", metadata.test_issue_key)
    _require_text_or_raise("stack_id", metadata.stack_id)
    _require_text_or_raise("branch_name", metadata.branch_name)
    _require_text_or_raise("base_sha", metadata.base_sha)
    _require_text_or_raise("head_sha", metadata.head_sha)
    if result.story_key != metadata.story_key:
        raise ManualTestWorkflowError(
            [
                ManualTestWorkflowIssue(
                    "story_key",
                    "Stacked bug metadata story key must match the failed test result story key.",
                )
            ]
        )
    if result.test_issue_key != metadata.test_issue_key:
        raise ManualTestWorkflowError(
            [
                ManualTestWorkflowIssue(
                    "test_issue_key",
                    "Stacked bug metadata Test issue key must match the failed test result Test issue key.",
                )
            ]
        )
    stack_lines = [
        "",
        "Stacked PR metadata:",
        f"- Stack ID: {metadata.stack_id}",
        f"- Layer: {metadata.stack_layer}",
        f"- Branch: {metadata.branch_name}",
        f"- Base SHA: {metadata.base_sha}",
        f"- Head SHA: {metadata.head_sha}",
    ]
    if metadata.preview_url:
        stack_lines.append(f"- Preview: {metadata.preview_url}")
    if metadata.evidence_path:
        stack_lines.append(f"- Evidence: {metadata.evidence_path}")
    return ManualTestBugPlan(
        summary=bug_plan.summary,
        description=bug_plan.description + "\n" + "\n".join(stack_lines),
        story_key=bug_plan.story_key,
        test_issue_key=bug_plan.test_issue_key,
        failed_acceptance_criteria=bug_plan.failed_acceptance_criteria,
    )


def stacked_test_evidence_record_to_dict(record: StackedTestEvidenceRecord) -> dict[str, object]:
    """Convert stacked test evidence into JSON-compatible durable data."""

    return {
        "story_key": record.story_key,
        "test_issue_key": record.test_issue_key,
        "stack_id": record.stack_id,
        "stack_layer": record.stack_layer,
        "branch_name": record.branch_name,
        "base_sha": record.base_sha,
        "head_sha": record.head_sha,
        "environment_name": record.environment_name,
        "preview_url": record.preview_url,
        "acceptance_criteria_covered": list(record.acceptance_criteria_covered),
        "finality": record.finality.value,
        "evidence_path": record.evidence_path,
        "stale_reason": record.stale_reason,
    }


def _validate_stacked_testing_context(context: StackedTestingContext) -> list[ManualTestWorkflowIssue]:
    issues: list[ManualTestWorkflowIssue] = []
    _require_text(issues, "story_key", context.story_key)
    _require_text(issues, "stack_id", context.stack_id)
    _require_text(issues, "branch_name", context.branch_name)
    _require_text(issues, "base_sha", context.base_sha)
    _require_text(issues, "head_sha", context.head_sha)
    if context.stack_layer < 1:
        issues.append(ManualTestWorkflowIssue("stack_layer", "Stack layer must be 1 or greater."))
    if not context.acceptance_criteria:
        issues.append(
            ManualTestWorkflowIssue(
                "acceptance_criteria",
                "At least one acceptance criterion is required for stacked testing.",
            )
        )
    if context.stack_testable_before_merge and not context.merged_to_main_or_release:
        if not context.environment_name.strip() and not context.preview_url.strip():
            issues.append(
                ManualTestWorkflowIssue(
                    "environment",
                    "Early stacked testing requires an environment name or preview URL.",
                )
            )
    return issues


def _lower_layer_changed(context: StackedTestingContext) -> bool:
    return (
        bool(context.lower_layer_recorded_head_sha.strip())
        and bool(context.lower_layer_current_head_sha.strip())
        and context.lower_layer_recorded_head_sha.strip() != context.lower_layer_current_head_sha.strip()
    )


def _require_text(issues: list[ManualTestWorkflowIssue], field: str, value: str) -> None:
    if not value.strip():
        issues.append(ManualTestWorkflowIssue(field, "Value is required."))


def _require_text_or_raise(field: str, value: str) -> None:
    if not value.strip():
        raise ManualTestWorkflowError([ManualTestWorkflowIssue(field, "Value is required.")])
