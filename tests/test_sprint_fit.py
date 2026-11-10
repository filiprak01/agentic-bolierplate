from agentic_boilerplate import domain
from agentic_boilerplate.domain.sprint_fit import (
    SprintFitCapacity,
    SprintFitError,
    SprintFitWarningType,
    build_sprint_fit_plan,
    complexity_warning_points,
    scope_issue_from_complexity,
    sprint_scope_labels,
)
from agentic_boilerplate.domain.story_complexity import ComplexityLevel


def release_scope_with_issues(
    issues: tuple[domain.ScopeIssue, ...],
) -> domain.ReleaseScope:
    ring = domain.create_sprint_ring(
        number=6,
        name="MVP S6 Scheduling",
        capacity_target="one Codex Plus working window",
        goal="Deliver scheduler foundations.",
        included_issues=issues,
    )
    return domain.create_release_scope(
        key="MVP-REL-1",
        name="MVP Release 1",
        release_version="1.0.0",
        description="MVP Release 1 spans multiple sprint rings.",
        created_at="2026-06-21T21:20:00Z",
        sprint_rings=(ring,),
    )


def test_planner_records_coherent_scope_and_fit_decision() -> None:
    scope = release_scope_with_issues(
        (
            scope_issue_from_complexity(
                key="AGENT-37",
                title="Release scope model",
                issue_type="Story",
                complexity=ComplexityLevel.C3,
            ),
            scope_issue_from_complexity(
                key="AGENT-38",
                title="Sprint fit planner",
                issue_type="Story",
                complexity=ComplexityLevel.C3,
            ),
        )
    )

    plan = build_sprint_fit_plan(
        scope,
        sprint_ring_number=6,
        coherent_deliverable_scope="Scheduler planning foundation",
        capacity=SprintFitCapacity(
            codex_window="Codex Plus 5h window",
            max_complexity_points=8,
            max_story_count=3,
        ),
        release_label="release-mvp",
    )

    assert plan.coherent_deliverable_scope == "Scheduler planning foundation"
    assert plan.codex_window == "Codex Plus 5h window"
    assert plan.story_count == 2
    assert plan.complexity_total == 6
    assert plan.likely_fits_codex_window is True
    assert plan.warnings == ()


def test_complexity_levels_map_to_numeric_warning_points() -> None:
    assert complexity_warning_points(ComplexityLevel.C1) == 1
    assert complexity_warning_points(ComplexityLevel.C2) == 2
    assert complexity_warning_points(ComplexityLevel.C3) == 3
    assert complexity_warning_points(ComplexityLevel.C4) == 5


def test_planner_warns_without_splitting_when_guidelines_are_exceeded() -> None:
    scope = release_scope_with_issues(
        (
            scope_issue_from_complexity(
                key="AGENT-37",
                title="Release scope model",
                issue_type="Story",
                complexity=ComplexityLevel.C3,
            ),
            scope_issue_from_complexity(
                key="AGENT-38",
                title="Sprint fit planner",
                issue_type="Story",
                complexity=ComplexityLevel.C3,
            ),
            scope_issue_from_complexity(
                key="AGENT-39",
                title="Dependency eligibility",
                issue_type="Story",
                complexity=ComplexityLevel.C3,
            ),
        )
    )

    plan = build_sprint_fit_plan(
        scope,
        sprint_ring_number=6,
        coherent_deliverable_scope="Scheduler planning foundation",
        capacity=SprintFitCapacity(
            codex_window="Codex Plus 5h window",
            max_complexity_points=6,
            max_story_count=2,
        ),
        release_label="release-mvp",
    )

    assert plan.likely_fits_codex_window is False
    assert plan.story_count == 3
    assert plan.complexity_total == 9
    assert tuple(warning.warning_type for warning in plan.warnings) == (
        SprintFitWarningType.COMPLEXITY_LIMIT,
        SprintFitWarningType.STORY_COUNT_LIMIT,
    )
    assert len(plan.issue_label_plans) == 3


def test_capacity_override_keeps_warnings_and_marks_plan_as_fit() -> None:
    scope = release_scope_with_issues(
        (
            scope_issue_from_complexity(
                key="AGENT-37",
                title="Release scope model",
                issue_type="Story",
                complexity=ComplexityLevel.C3,
            ),
            scope_issue_from_complexity(
                key="AGENT-38",
                title="Sprint fit planner",
                issue_type="Story",
                complexity=ComplexityLevel.C3,
            ),
        )
    )

    plan = build_sprint_fit_plan(
        scope,
        sprint_ring_number=6,
        coherent_deliverable_scope="Scheduler planning foundation",
        capacity=SprintFitCapacity(
            codex_window="Codex Plus 5h window",
            max_complexity_points=3,
            max_story_count=1,
        ),
        release_label="release-mvp",
        allow_capacity_override=True,
        override_reason="PO wants to keep the coherent scheduler slice together.",
    )

    assert plan.likely_fits_codex_window is True
    assert len(plan.warnings) == 2
    assert plan.override_reason == "PO wants to keep the coherent scheduler slice together."


def test_capacity_override_requires_reason() -> None:
    scope = release_scope_with_issues(
        (
            scope_issue_from_complexity(
                key="AGENT-37",
                title="Release scope model",
                issue_type="Story",
                complexity=ComplexityLevel.C3,
            ),
        )
    )

    try:
        build_sprint_fit_plan(
            scope,
            sprint_ring_number=6,
            coherent_deliverable_scope="Scheduler planning foundation",
            capacity=SprintFitCapacity(
                codex_window="Codex Plus 5h window",
                max_complexity_points=3,
                max_story_count=1,
            ),
            release_label="release-mvp",
            allow_capacity_override=True,
        )
    except SprintFitError as error:
        assert "override_reason is required" in str(error)
    else:
        raise AssertionError("Expected missing override reason to fail")


def test_capacity_limits_must_be_positive_integers() -> None:
    scope = release_scope_with_issues(
        (
            scope_issue_from_complexity(
                key="AGENT-37",
                title="Release scope model",
                issue_type="Story",
                complexity=ComplexityLevel.C3,
            ),
        )
    )

    try:
        build_sprint_fit_plan(
            scope,
            sprint_ring_number=6,
            coherent_deliverable_scope="Scheduler planning foundation",
            capacity=SprintFitCapacity(
                codex_window="Codex Plus 5h window",
                max_complexity_points=True,
                max_story_count=1,
            ),
            release_label="release-mvp",
        )
    except SprintFitError as error:
        assert "capacity.max_complexity_points must be a positive integer" in str(error)
    else:
        raise AssertionError("Expected boolean capacity limit to fail")


def test_sprint_scope_labels_include_release_and_sprint_metadata() -> None:
    labels = sprint_scope_labels(
        release_label="release-mvp",
        sprint_ring_number=6,
        capacity_warning=True,
    )

    assert labels == (
        "release-mvp",
        "sprint-ring-06",
        "mvp-sprint-06",
        "sprint-fit-warning",
    )


def test_sprint_fit_public_api_exports_are_available() -> None:
    assert domain.SprintFitCapacity is SprintFitCapacity
    assert domain.SprintFitWarningType is SprintFitWarningType
    assert domain.build_sprint_fit_plan is build_sprint_fit_plan
    assert domain.complexity_warning_points is complexity_warning_points
    assert domain.sprint_scope_labels is sprint_scope_labels
