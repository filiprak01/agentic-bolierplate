from agentic_boilerplate.domain import (
    ReleaseE2ECheckType,
    ReleaseE2EError,
    ReleaseE2EFailureSeverity,
    approve_release_e2e_scenario_map,
    build_default_mvp_release_e2e_gate,
    build_default_mvp_release_e2e_scenarios,
    build_release_e2e_scenario_map,
    release_blocking_failure_rules,
    render_release_e2e_scenario_map_markdown,
)
from agentic_boilerplate.storage import write_release_e2e_scenario_map


def test_default_mvp_release_e2e_map_covers_full_agent_workflow() -> None:
    scenarios = build_default_mvp_release_e2e_scenarios()
    gate = build_default_mvp_release_e2e_gate(
        release_key="MVP-R1",
        release_version="1.0.0",
        gate_issue_key="AGENT-357",
    )

    scenario_map = build_release_e2e_scenario_map(
        release_key="MVP-R1",
        release_version="1.0.0",
        generated_at="2026-07-07T08:00:00Z",
        implementation_scope_status="MVP implementation through process hardening accepted by PO.",
        scenarios=scenarios,
        release_gate=gate,
        excluded_checks=(
            "Unit tests are covered by implementation validation.",
            "Sprint regression checks are covered by sprint regression evidence.",
        ),
    )

    assert len(scenario_map.release_e2e_scenarios) == 4
    titles = {scenario.title for scenario in scenario_map.scenarios}
    assert any("Approved backlog" in title for title in titles)
    assert any("Developer implementation" in title for title in titles)
    assert any("Tester failure" in title for title in titles)
    assert any("Sprint regression evidence" in title for title in titles)


def test_release_e2e_scenarios_include_required_po_visible_fields() -> None:
    scenario = build_default_mvp_release_e2e_scenarios()[0]

    assert scenario.preconditions
    assert scenario.steps
    assert scenario.expected_result
    assert scenario.owner_role.value == "release-manager"
    assert scenario.evidence_type.value == "local-markdown"
    assert scenario.agiletest_test_case_expectation


def test_release_gate_defines_blocking_failures_and_bug_routing() -> None:
    gate = build_default_mvp_release_e2e_gate(
        release_key="MVP-R1",
        release_version="1.0.0",
        gate_issue_key="AGENT-357",
    )

    blocking_rules = release_blocking_failure_rules(gate)

    assert {rule.severity for rule in blocking_rules} == {
        ReleaseE2EFailureSeverity.BLOCKS_RELEASE,
        ReleaseE2EFailureSeverity.REQUIRES_PO_WAIVER,
    }
    assert all("Bug" in rule.bug_link_rule or "known limitation" in rule.bug_link_rule for rule in blocking_rules)


def test_scenario_map_distinguishes_release_e2e_from_lower_level_checks() -> None:
    scenarios = build_default_mvp_release_e2e_scenarios()
    gate = build_default_mvp_release_e2e_gate(
        release_key="MVP-R1",
        release_version="1.0.0",
        gate_issue_key="AGENT-357",
    )

    scenario_map = build_release_e2e_scenario_map(
        release_key="MVP-R1",
        release_version="1.0.0",
        generated_at="2026-07-07T08:00:00Z",
        implementation_scope_status="scope complete",
        scenarios=scenarios,
        release_gate=gate,
        excluded_checks=("Sprint regression is tracked separately.", "Unit and integration checks are lower-level."),
    )

    rendered = render_release_e2e_scenario_map_markdown(scenario_map)

    assert all(scenario.check_type is ReleaseE2ECheckType.RELEASE_E2E for scenario in scenario_map.scenarios)
    assert "Sprint regression is tracked separately." in rendered
    assert "Unit and integration checks are lower-level." in rendered


def test_scenario_map_requires_release_e2e_scenario() -> None:
    gate = build_default_mvp_release_e2e_gate(
        release_key="MVP-R1",
        release_version="1.0.0",
        gate_issue_key="AGENT-357",
    )

    try:
        build_release_e2e_scenario_map(
            release_key="MVP-R1",
            release_version="1.0.0",
            generated_at="2026-07-07T08:00:00Z",
            implementation_scope_status="scope complete",
            scenarios=(),
            release_gate=gate,
        )
    except ReleaseE2EError as error:
        assert "scenarios is required" in str(error)
    else:
        raise AssertionError("ReleaseE2EError was not raised")


def test_scenario_map_can_be_approved_and_written(tmp_path) -> None:
    scenarios = build_default_mvp_release_e2e_scenarios()
    gate = build_default_mvp_release_e2e_gate(
        release_key="MVP-R1",
        release_version="1.0.0",
        gate_issue_key="AGENT-357",
    )
    scenario_map = build_release_e2e_scenario_map(
        release_key="MVP-R1",
        release_version="1.0.0",
        generated_at="2026-07-07T08:00:00Z",
        implementation_scope_status="scope complete",
        scenarios=scenarios,
        release_gate=gate,
    )

    approved = approve_release_e2e_scenario_map(scenario_map, approved_by="PO")
    path = write_release_e2e_scenario_map(approved, tmp_path)

    assert "approved for release E2E by PO" in approved.implementation_scope_status
    assert path.name == "mvp-r1-e2e-scenario-map.md"
    assert "REL-E2E-001" in path.read_text(encoding="utf-8")
