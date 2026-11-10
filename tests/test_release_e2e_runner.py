from agentic_boilerplate.domain import (
    ReleaseE2EEnvironmentCheckStatus,
    ReleaseE2EScenarioExecution,
    ReleaseE2EScenarioExecutionMode,
    ReleaseE2EScenarioResult,
    build_default_mvp_release_e2e_gate,
    build_default_mvp_release_e2e_scenarios,
    build_default_release_e2e_environment_checklist,
    build_release_e2e_execution_report,
    build_release_e2e_scenario_map,
    failed_release_e2e_scenarios,
    render_release_e2e_execution_report,
)
from agentic_boilerplate.storage import write_release_e2e_execution_report


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


def test_environment_checklist_verifies_required_release_inputs() -> None:
    checklist = build_default_release_e2e_environment_checklist(
        project_key="AGENT",
        target_project_path="/workspace/sample",
        jira_configured=True,
        github_configured=True,
        confluence_configured=True,
        agiletest_configured=True,
        durable_storage_configured=True,
        local_services_ready=True,
        sample_target_ready=True,
    )

    assert checklist.ready is True
    categories = {check.category for check in checklist.checks}
    assert {"local-services", "credentials", "durable-volumes", "target-project"}.issubset(categories)


def test_environment_checklist_blocks_execution_when_required_config_missing() -> None:
    checklist = build_default_release_e2e_environment_checklist(
        project_key="AGENT",
        target_project_path="/workspace/sample",
        jira_configured=True,
        github_configured=False,
        confluence_configured=True,
        agiletest_configured=False,
        durable_storage_configured=True,
        local_services_ready=True,
        sample_target_ready=True,
    )

    failed = [check for check in checklist.checks if check.status is ReleaseE2EEnvironmentCheckStatus.FAILED]

    assert checklist.ready is False
    assert {check.name for check in failed} == {"GitHub configuration", "AgileTest configuration"}


def test_runner_marks_release_scenarios_manual_only_without_live_integrations() -> None:
    checklist = build_default_release_e2e_environment_checklist(
        project_key="AGENT",
        target_project_path="/workspace/sample",
        jira_configured=True,
        github_configured=True,
        confluence_configured=True,
        agiletest_configured=True,
        durable_storage_configured=True,
        local_services_ready=True,
        sample_target_ready=True,
    )

    report = build_release_e2e_execution_report(
        scenario_map=_scenario_map(),
        generated_at="2026-07-07T09:00:00Z",
        target_project_key="AGENT",
        checklist=checklist,
    )

    assert report.production_data_required is False
    assert {execution.mode for execution in report.executions} == {ReleaseE2EScenarioExecutionMode.MANUAL_ONLY}
    assert {execution.result for execution in report.executions} == {ReleaseE2EScenarioResult.NOT_RUN}


def test_runner_records_scenario_level_pass_fail_and_bug_links() -> None:
    checklist = build_default_release_e2e_environment_checklist(
        project_key="AGENT",
        target_project_path="/workspace/sample",
        jira_configured=True,
        github_configured=True,
        confluence_configured=True,
        agiletest_configured=True,
        durable_storage_configured=True,
        local_services_ready=True,
        sample_target_ready=True,
    )

    report = build_release_e2e_execution_report(
        scenario_map=_scenario_map(),
        generated_at="2026-07-07T09:00:00Z",
        target_project_key="AGENT",
        checklist=checklist,
        execution_overrides=(
            ReleaseE2EScenarioExecution(
                scenario_id="REL-E2E-001",
                title="Approved backlog and sprint scope become eligible worker assignments",
                mode=ReleaseE2EScenarioExecutionMode.AUTOMATED,
                result=ReleaseE2EScenarioResult.PASSED,
                evidence_path="data/agent-logs/REL-E2E-001.md",
            ),
            ReleaseE2EScenarioExecution(
                scenario_id="REL-E2E-002",
                title="Developer implementation, review, merge, and PR visibility complete as one flow",
                mode=ReleaseE2EScenarioExecutionMode.MANUAL_ONLY,
                result=ReleaseE2EScenarioResult.FAILED,
                evidence_path="data/agent-logs/REL-E2E-002.md",
                bug_keys=("AGENT-999",),
            ),
        ),
    )

    failed = failed_release_e2e_scenarios(report)

    assert report.passed is False
    assert failed[0].scenario_id == "REL-E2E-002"
    assert failed[0].bug_keys == ("AGENT-999",)


def test_runner_writes_durable_execution_report(tmp_path) -> None:
    checklist = build_default_release_e2e_environment_checklist(
        project_key="AGENT",
        target_project_path="/workspace/sample",
        jira_configured=True,
        github_configured=True,
        confluence_configured=True,
        agiletest_configured=True,
        durable_storage_configured=True,
        local_services_ready=True,
        sample_target_ready=True,
    )
    report = build_release_e2e_execution_report(
        scenario_map=_scenario_map(),
        generated_at="2026-07-07T09:00:00Z",
        target_project_key="AGENT",
        checklist=checklist,
    )

    path = write_release_e2e_execution_report(report, tmp_path)
    rendered = render_release_e2e_execution_report(report)

    assert path.name == "mvp-r1-e2e-execution.md"
    assert "Production data required: no" in rendered
    assert "REL-E2E-001" in path.read_text(encoding="utf-8")
