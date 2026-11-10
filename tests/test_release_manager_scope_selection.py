from agentic_boilerplate.domain import (
    AgentRole,
    PreviousTestOutcome,
    ReleaseManagerIssueCandidate,
    ReleaseManagerScopeSelectionError,
    build_release_manager_scope_selection,
    release_manager_scope_selection_from_dict,
    release_manager_scope_selection_to_dict,
    render_release_manager_scope_selection,
)


def test_release_manager_selects_ready_unblocked_assignable_issues() -> None:
    selection = build_release_manager_scope_selection(
        release_scope_key="MVP-R1",
        sprint_ring_number=9,
        candidates=(
            _candidate("AGENT-52", complexity_points=3),
            _candidate("AGENT-53", complexity_points=2, worker_role=AgentRole.TESTER),
        ),
        release_label="release-mvp",
        release_version="1.0.0",
        sprint_label="mvp-sprint-09",
        sprint_ring_label="sprint-ring-09",
        max_complexity_points=6,
        max_story_count=3,
        rationale="Release Manager picked the coherent MVP release workflow slice.",
    )

    assert selection.selected_issue_keys == ("AGENT-52", "AGENT-53")
    assert selection.rejected == ()
    assert selection.complexity_total == 5
    assert selection.story_count == 2
    assert selection.po_approval_required is True
    assert [plan.issue_key for plan in selection.metadata_plans] == ["AGENT-52", "AGENT-53"]
    assert {plan.sprint_label for plan in selection.metadata_plans} == {"mvp-sprint-09"}
    assert [decision.worker_role for decision in selection.assignment_decisions] == [
        AgentRole.DEVELOPER,
        AgentRole.TESTER,
    ]
    assert all(decision.assignable for decision in selection.assignment_decisions)


def test_release_manager_rejects_ineligible_issues_with_visible_reasons() -> None:
    selection = build_release_manager_scope_selection(
        release_scope_key="MVP-R1",
        sprint_ring_number=9,
        candidates=(
            _candidate("AGENT-52", status="FUNNEL"),
            _candidate(
                "AGENT-53",
                dependency_eligible=False,
                dependency_reasons=("AGENT-52 is not TEST COMPLETED.",),
            ),
            _candidate("AGENT-54", previous_test_outcome=PreviousTestOutcome.FAILED),
            _candidate("AGENT-55", worker_available=False),
        ),
        release_label="release-mvp",
        release_version="1.0.0",
        sprint_label="mvp-sprint-09",
        sprint_ring_label="sprint-ring-09",
        max_complexity_points=8,
        max_story_count=4,
        rationale="Release Manager rejects stories that are not eligible for implementation.",
    )

    assert selection.selected_issue_keys == ()
    assert {item.issue_key: item.reason for item in selection.rejected} == {
        "AGENT-52": "Issue is not READY TO START.",
        "AGENT-53": "Issue has unresolved prerequisites. AGENT-52 is not TEST COMPLETED.",
        "AGENT-54": "Previous test outcome blocks release scope: failed.",
        "AGENT-55": "No available worker for required role.",
    }


def test_release_manager_enforces_story_count_and_complexity_capacity() -> None:
    selection = build_release_manager_scope_selection(
        release_scope_key="MVP-R1",
        sprint_ring_number=9,
        candidates=(
            _candidate("AGENT-52", complexity_points=3),
            _candidate("AGENT-53", complexity_points=3),
            _candidate("AGENT-54", complexity_points=1),
        ),
        release_label="release-mvp",
        release_version="1.0.0",
        sprint_label="mvp-sprint-09",
        sprint_ring_label="sprint-ring-09",
        max_complexity_points=5,
        max_story_count=2,
        rationale="Release Manager keeps the sprint inside the configured Codex window.",
    )

    assert selection.selected_issue_keys == ("AGENT-52", "AGENT-54")
    assert {item.issue_key: item.reason for item in selection.rejected} == {
        "AGENT-53": "Complexity total would exceed capacity.",
    }
    assert selection.complexity_total == 4


def test_release_manager_records_story_count_capacity_rejection() -> None:
    selection = build_release_manager_scope_selection(
        release_scope_key="MVP-R1",
        sprint_ring_number=9,
        candidates=(
            _candidate("AGENT-52", complexity_points=1),
            _candidate("AGENT-53", complexity_points=1),
        ),
        release_label="release-mvp",
        release_version="1.0.0",
        sprint_label="mvp-sprint-09",
        sprint_ring_label="sprint-ring-09",
        max_complexity_points=5,
        max_story_count=1,
        rationale="Release Manager keeps a one-story smoke slice.",
    )

    assert selection.selected_issue_keys == ("AGENT-52",)
    assert {item.issue_key: item.reason for item in selection.rejected} == {
        "AGENT-53": "Story count would exceed capacity.",
    }


def test_release_manager_selection_round_trips_and_renders_evidence() -> None:
    selection = build_release_manager_scope_selection(
        release_scope_key="MVP-R1",
        sprint_ring_number=9,
        candidates=(_candidate("AGENT-52", complexity_points=3),),
        release_label="release-mvp",
        release_version="1.0.0",
        sprint_label="mvp-sprint-09",
        sprint_ring_label="sprint-ring-09",
        max_complexity_points=5,
        max_story_count=2,
        rationale="Release Manager picked the release scope selector.",
    )

    restored = release_manager_scope_selection_from_dict(
        release_manager_scope_selection_to_dict(selection)
    )
    rendered = render_release_manager_scope_selection(restored)

    assert restored == selection
    assert "# Release Manager Scope Selection - MVP-R1" in rendered
    assert "- AGENT-52" in rendered
    assert "- PO approval required: yes" in rendered


def test_release_manager_requires_positive_capacity_limits() -> None:
    try:
        build_release_manager_scope_selection(
            release_scope_key="MVP-R1",
            sprint_ring_number=9,
            candidates=(),
            release_label="release-mvp",
            release_version="1.0.0",
            sprint_label="mvp-sprint-09",
            sprint_ring_label="sprint-ring-09",
            max_complexity_points=0,
            max_story_count=1,
            rationale="Invalid capacity.",
        )
    except ReleaseManagerScopeSelectionError as error:
        assert "max_complexity_points must be a positive integer" in str(error)
    else:
        raise AssertionError("Expected invalid capacity to fail")


def _candidate(
    issue_key: str,
    *,
    status: str = "READY TO START",
    complexity_points: int = 2,
    worker_role: AgentRole = AgentRole.DEVELOPER,
    dependency_eligible: bool = True,
    worker_available: bool = True,
    previous_test_outcome: PreviousTestOutcome = PreviousTestOutcome.PASSED,
    dependency_reasons: tuple[str, ...] = (),
) -> ReleaseManagerIssueCandidate:
    return ReleaseManagerIssueCandidate(
        issue_key=issue_key,
        title=f"{issue_key} candidate",
        issue_type="Story",
        status=status,
        complexity_points=complexity_points,
        worker_role=worker_role,
        dependency_eligible=dependency_eligible,
        worker_available=worker_available,
        previous_test_outcome=previous_test_outcome,
        dependency_reasons=dependency_reasons,
    )
