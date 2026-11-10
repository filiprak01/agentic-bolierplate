from agentic_boilerplate.domain import (
    ReleaseE2EAgileTestPlanError,
    ReleaseE2ETestStepMode,
    build_default_mvp_release_e2e_gate,
    build_default_mvp_release_e2e_scenarios,
    build_release_e2e_execution_plan,
    build_release_e2e_scenario_map,
    build_release_e2e_test_case_plans,
    release_e2e_test_case_description,
    render_release_e2e_execution_plan,
)


def _scenario_map():
    return build_release_e2e_scenario_map(
        release_key="MVP-R1",
        release_version="1.0.0",
        generated_at="2026-07-07T08:00:00Z",
        implementation_scope_status="scope complete",
        scenarios=build_default_mvp_release_e2e_scenarios(),
        release_gate=build_default_mvp_release_e2e_gate(
            release_key="MVP-R1",
            release_version="1.0.0",
            gate_issue_key="AGENT-357",
        ),
    )


def test_builds_test_case_for_each_release_e2e_scenario() -> None:
    test_cases = build_release_e2e_test_case_plans(_scenario_map())

    assert len(test_cases) == 4
    assert {case.scenario_id for case in test_cases} == {
        "REL-E2E-001",
        "REL-E2E-002",
        "REL-E2E-003",
        "REL-E2E-004",
    }
    assert all(case.preconditions for case in test_cases)
    assert all(case.steps for case in test_cases)
    assert all(case.expected_result for case in test_cases)
    assert all(case.owner_role for case in test_cases)
    assert all(case.evidence_expectation for case in test_cases)


def test_release_e2e_test_cases_use_release_labels_and_manual_only_default() -> None:
    test_cases = build_release_e2e_test_case_plans(_scenario_map())

    for test_case in test_cases:
        assert "release-regression" in test_case.labels
        assert "release-e2e" in test_case.labels
        assert "manual-only" in test_case.labels
        assert {step.mode for step in test_case.steps} == {ReleaseE2ETestStepMode.MANUAL_ONLY}


def test_automated_capable_scenarios_are_visible_in_steps_and_labels() -> None:
    test_cases = build_release_e2e_test_case_plans(
        _scenario_map(),
        automated_capable_scenario_ids=("REL-E2E-001",),
    )
    automated_case = next(case for case in test_cases if case.scenario_id == "REL-E2E-001")

    assert "automated-capable" in automated_case.labels
    assert {step.mode for step in automated_case.steps} == {ReleaseE2ETestStepMode.AUTOMATED_CAPABLE}


def test_execution_plan_groups_e2e_test_cases_for_po_review() -> None:
    test_cases = build_release_e2e_test_case_plans(_scenario_map())
    plan = build_release_e2e_execution_plan(
        release_key="MVP-R1",
        release_version="1.0.0",
        execution_name="MVP Release 1 E2E",
        overview_issue_key="AGENT-357",
        test_cases=test_cases,
    )

    rendered = render_release_e2e_execution_plan(plan)

    assert plan.po_review_required is True
    assert "AGENT-357" in rendered
    assert "REL-E2E-001" in rendered
    assert "manual-only" in rendered


def test_test_case_description_contains_agiletest_visible_fields() -> None:
    test_case = build_release_e2e_test_case_plans(_scenario_map())[0]
    description = release_e2e_test_case_description(test_case)

    assert "Preconditions:" in description
    assert "Steps:" in description
    assert "Expected result:" in description
    assert "Evidence expectation:" in description
    assert "Owner role:" in description


def test_execution_plan_requires_test_cases() -> None:
    try:
        build_release_e2e_execution_plan(
            release_key="MVP-R1",
            release_version="1.0.0",
            execution_name="MVP Release 1 E2E",
            overview_issue_key="AGENT-357",
            test_cases=(),
        )
    except ReleaseE2EAgileTestPlanError as error:
        assert "test_cases is required" in str(error)
    else:
        raise AssertionError("ReleaseE2EAgileTestPlanError was not raised")
