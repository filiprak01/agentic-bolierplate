from agentic_boilerplate.domain import (
    SprintDependencyIssue,
    SprintDependencyLink,
    evaluate_recursive_sprint_dependency_coscheduling,
    render_sprint_dependency_coscheduling_result,
)


def test_direct_unresolved_blocker_outside_sprint_creates_planning_error() -> None:
    result = evaluate_recursive_sprint_dependency_coscheduling(
        sprint_label="mvp-sprint-09",
        proposed_issue_keys=("AGENT-55",),
        issues=(
            SprintDependencyIssue("AGENT-55", "READY TO START", ("mvp-sprint-09",)),
            SprintDependencyIssue("AGENT-85", "READY TO START", ()),
        ),
        links=(SprintDependencyLink(blocker_key="AGENT-85", dependent_key="AGENT-55"),),
    )

    assert not result.is_valid
    assert result.errors[0].missing_blocker_key == "AGENT-85"
    assert result.errors[0].dependency_chain == ("AGENT-55", "AGENT-85")
    assert result.correction_plan.required_issue_keys == ("AGENT-85",)


def test_recursive_blocker_chain_requires_blockers_of_blockers() -> None:
    result = evaluate_recursive_sprint_dependency_coscheduling(
        sprint_label="mvp-sprint-09",
        proposed_issue_keys=("AGENT-55",),
        issues=(
            SprintDependencyIssue("AGENT-55", "READY TO START", ("mvp-sprint-09",)),
            SprintDependencyIssue("AGENT-86", "READY TO START", ("mvp-sprint-09",)),
            SprintDependencyIssue("AGENT-85", "READY TO START", ()),
        ),
        links=(
            SprintDependencyLink(blocker_key="AGENT-86", dependent_key="AGENT-55"),
            SprintDependencyLink(blocker_key="AGENT-85", dependent_key="AGENT-86"),
        ),
    )

    assert not result.is_valid
    assert result.errors[0].dependency_chain == ("AGENT-55", "AGENT-86", "AGENT-85")
    assert result.correction_plan.required_issue_keys == ("AGENT-85",)


def test_completed_blockers_do_not_need_to_be_scheduled() -> None:
    result = evaluate_recursive_sprint_dependency_coscheduling(
        sprint_label="mvp-sprint-09",
        proposed_issue_keys=("AGENT-55",),
        issues=(
            SprintDependencyIssue("AGENT-55", "READY TO START", ("mvp-sprint-09",)),
            SprintDependencyIssue("AGENT-85", "TEST COMPLETED", ()),
        ),
        links=(SprintDependencyLink(blocker_key="AGENT-85", dependent_key="AGENT-55"),),
    )

    assert result.is_valid
    assert result.correction_plan.required_issue_keys == ()


def test_merged_blockers_do_not_need_to_be_scheduled() -> None:
    result = evaluate_recursive_sprint_dependency_coscheduling(
        sprint_label="mvp-sprint-09",
        proposed_issue_keys=("AGENT-55",),
        issues=(
            SprintDependencyIssue("AGENT-55", "READY TO START", ("mvp-sprint-09",)),
            SprintDependencyIssue("AGENT-85", "DEV COMPLETED", (), merged_to_main=True),
        ),
        links=(SprintDependencyLink(blocker_key="AGENT-85", dependent_key="AGENT-55"),),
    )

    assert result.is_valid
    assert result.correction_plan.required_issue_keys == ()


def test_mixed_sprint_labels_count_as_co_scheduled_when_label_matches() -> None:
    result = evaluate_recursive_sprint_dependency_coscheduling(
        sprint_label="mvp-sprint-09",
        proposed_issue_keys=("AGENT-55",),
        issues=(
            SprintDependencyIssue("AGENT-55", "READY TO START", ("mvp-sprint-09",)),
            SprintDependencyIssue("AGENT-85", "READY TO START", ("mvp-sprint-08", "mvp-sprint-09")),
        ),
        links=(SprintDependencyLink(blocker_key="AGENT-85", dependent_key="AGENT-55"),),
    )

    assert result.is_valid
    assert "AGENT-85" in result.planned_issue_keys
    assert result.execution_order.index("AGENT-85") < result.execution_order.index("AGENT-55")


def test_missing_blocker_snapshot_is_reported_as_required_prerequisite() -> None:
    result = evaluate_recursive_sprint_dependency_coscheduling(
        sprint_label="mvp-sprint-09",
        proposed_issue_keys=("AGENT-55",),
        issues=(SprintDependencyIssue("AGENT-55", "READY TO START", ("mvp-sprint-09",)),),
        links=(SprintDependencyLink(blocker_key="AGENT-999", dependent_key="AGENT-55"),),
    )

    assert not result.is_valid
    assert result.correction_plan.required_issue_keys == ("AGENT-999",)


def test_render_result_lists_blocking_errors_and_correction_plan() -> None:
    result = evaluate_recursive_sprint_dependency_coscheduling(
        sprint_label="mvp-sprint-09",
        proposed_issue_keys=("AGENT-55",),
        issues=(
            SprintDependencyIssue("AGENT-55", "READY TO START", ("mvp-sprint-09",)),
            SprintDependencyIssue("AGENT-86", "READY TO START", ("mvp-sprint-09",)),
            SprintDependencyIssue("AGENT-85", "READY TO START", ()),
        ),
        links=(
            SprintDependencyLink(blocker_key="AGENT-86", dependent_key="AGENT-55"),
            SprintDependencyLink(blocker_key="AGENT-85", dependent_key="AGENT-86"),
        ),
    )

    note = render_sprint_dependency_coscheduling_result(result)

    assert "Result: blocked" in note
    assert "## Execution Order" in note
    assert "1. AGENT-86" in note
    assert "2. AGENT-55" in note
    assert "AGENT-55 -> AGENT-86 -> AGENT-85" in note
    assert "Add or complete these prerequisite issues" in note
    assert "- AGENT-85" in note
