from dataclasses import replace
from pathlib import Path

from agentic_boilerplate.domain import (
    AgentAssignment,
    AgentRole,
    AssignmentPaths,
    AssignmentStatus,
    AssignmentWorkspacePlan,
    CodexLimitObservationSource,
    CodexLimitWindowAvailability,
    CodexLimitWindowStatus,
    SharedDurablePath,
    WorkspaceProvisioningMode,
    build_single_pool_codex_limit_availability_record,
)
from agentic_boilerplate.runtime import (
    HostCheckoutState,
    HostCodexLimitRefreshEvidence,
    HostCodexPreflightIssueKind,
    HostCodexPreflightRequest,
    HostPathMapping,
    HostScopeState,
    evaluate_host_codex_preflight,
    render_host_codex_preflight_decision,
)


def test_preflight_allows_fresh_app_server_limits_and_isolated_checkout(tmp_path: Path) -> None:
    request = _request(tmp_path)

    decision = evaluate_host_codex_preflight(request)

    assert decision.allowed is True
    assert decision.issues == ()
    assert decision.limit_gate is not None
    assert decision.limit_gate.allowed is True
    assert decision.limit_observation_id == "availability-good"
    assert decision.limit_observation_source == "codex_app_server"
    assert decision.host_workspace_path.endswith("workspaces/AGENT-965/developer")
    assert "Host Codex preflight: allowed" in render_host_codex_preflight_decision(decision)


def test_preflight_blocks_wrong_repository_project_branch_issue_and_role(tmp_path: Path) -> None:
    request = _request(tmp_path)
    changed = replace(
        request,
        checkout=replace(
            request.checkout,
            repository="OtherOrg/other-repo",
            branch_name="feature/AGENT-999-wrong-branch",
            project_id="other-project",
            jira_project_key="OTHER",
            jira_issue_key="AGENT-999",
            role=AgentRole.TESTER,
        ),
        scope=replace(request.scope, jira_issue_key="AGENT-999", role=AgentRole.TESTER),
    )

    decision = evaluate_host_codex_preflight(changed)

    assert decision.allowed is False
    assert _kinds(decision) >= {
        HostCodexPreflightIssueKind.REPOSITORY_MISMATCH,
        HostCodexPreflightIssueKind.BRANCH_MISMATCH,
        HostCodexPreflightIssueKind.PROJECT_MISMATCH,
        HostCodexPreflightIssueKind.JIRA_PROJECT_MISMATCH,
        HostCodexPreflightIssueKind.ISSUE_MISMATCH,
        HostCodexPreflightIssueKind.ROLE_MISMATCH,
    }


def test_preflight_blocks_absent_checkout_path_escape_and_source_reuse(tmp_path: Path) -> None:
    request = _request(tmp_path)
    missing = replace(
        request,
        workspace_plan=replace(request.workspace_plan, workspace_path="/workspaces/missing/developer"),
    )
    escaped = replace(
        request,
        workspace_plan=replace(request.workspace_plan, workspace_path="/workspaces/../../escaped"),
    )
    reused = replace(
        request,
        workspace_plan=replace(request.workspace_plan, workspace_path="/source"),
        path_mappings=(*request.path_mappings, HostPathMapping("/source", str(tmp_path / "source"))),
    )

    assert HostCodexPreflightIssueKind.CHECKOUT_MISSING in _kinds(evaluate_host_codex_preflight(missing))
    assert HostCodexPreflightIssueKind.PATH_ESCAPE in _kinds(evaluate_host_codex_preflight(escaped))
    assert HostCodexPreflightIssueKind.SOURCE_CHECKOUT_REUSED in _kinds(evaluate_host_codex_preflight(reused))


def test_preflight_blocks_missing_mapping_and_output_escape(tmp_path: Path) -> None:
    request = _request(tmp_path)
    changed_assignment = replace(
        request.assignment,
        paths=replace(
            request.assignment.paths,
            output_path="/unknown/result.json",
            codex_job_path="/durable/../outside/job.json",
        ),
    )

    decision = evaluate_host_codex_preflight(replace(request, assignment=changed_assignment))

    assert decision.allowed is False
    assert _kinds(decision) >= {
        HostCodexPreflightIssueKind.MISSING_PATH_MAPPING,
        HostCodexPreflightIssueKind.OUTPUT_PATH_OUTSIDE_ROOT,
    }


def test_preflight_blocks_revoked_eligibility_bugs_design_po_context_and_foreign_lock(tmp_path: Path) -> None:
    request = _request(tmp_path)
    changed = replace(
        request,
        scope=replace(
            request.scope,
            status="FUNNEL",
            unresolved_dependency_keys=("AGENT-123",),
            blocking_bug_keys=("AGENT-456",),
            po_blocker_ids=("po-question-1",),
            ui_design_required=True,
            accepted_ui_design_reference="",
            context_revision_current=False,
            context_revision="ctx-old",
            assignment_lock_owner="worker-other",
            expected_worker_id="worker-1",
        ),
    )

    decision = evaluate_host_codex_preflight(changed)

    assert decision.allowed is False
    assert _kinds(decision) >= {
        HostCodexPreflightIssueKind.STATUS_NOT_ELIGIBLE,
        HostCodexPreflightIssueKind.DEPENDENCIES_UNRESOLVED,
        HostCodexPreflightIssueKind.BLOCKING_BUGS,
        HostCodexPreflightIssueKind.PO_BLOCKERS,
        HostCodexPreflightIssueKind.UI_DESIGN_NOT_ACCEPTED,
        HostCodexPreflightIssueKind.STALE_CONTEXT,
        HostCodexPreflightIssueKind.FOREIGN_LOCK,
    }


def test_preflight_blocks_missing_non_app_server_or_stale_quota_refresh(tmp_path: Path) -> None:
    request = _request(tmp_path)
    no_refresh = replace(
        request,
        limit_refresh=replace(request.limit_refresh, refreshed_this_attempt=False),
    )
    operator_refresh = replace(
        request,
        limit_refresh=replace(request.limit_refresh, source=CodexLimitObservationSource.OPERATOR),
    )
    stale_record = _limit_record("availability-stale", observed_at="2026-09-12T10:00:00Z", remaining=90)
    stale = replace(
        request,
        limit_refresh=HostCodexLimitRefreshEvidence(
            record=stale_record,
            observation_id="availability-stale",
            observed_at="2026-09-12T10:00:00Z",
            source=CodexLimitObservationSource.CODEX_APP_SERVER,
            account_scope_id="chatgpt-primary",
            bucket_id="codex",
        ),
    )

    assert HostCodexPreflightIssueKind.LIMIT_REFRESH_MISSING in _kinds(
        evaluate_host_codex_preflight(no_refresh)
    )
    assert HostCodexPreflightIssueKind.LIMIT_SOURCE_UNSUPPORTED in _kinds(
        evaluate_host_codex_preflight(operator_refresh)
    )
    assert HostCodexPreflightIssueKind.LIMIT_GATE_CLOSED in _kinds(evaluate_host_codex_preflight(stale))


def _request(tmp_path: Path) -> HostCodexPreflightRequest:
    workspaces = tmp_path / "workspaces"
    workspace = workspaces / "AGENT-965" / "developer"
    durable = tmp_path / "durable"
    source = tmp_path / "source"
    for path in (workspace, durable, source):
        path.mkdir(parents=True, exist_ok=True)
    (workspace / ".git").mkdir(exist_ok=True)
    (source / ".git").mkdir(exist_ok=True)

    assignment = AgentAssignment(
        id="assignment-AGENT-965",
        jira_issue_key="AGENT-965",
        role=AgentRole.DEVELOPER,
        status=AssignmentStatus.QUEUED,
        paths=AssignmentPaths(
            context_pack_path="/durable/context-packs/AGENT-965/context.json",
            codex_job_path="/durable/codex-jobs/AGENT-965/job.json",
            output_path="/durable/codex-results/AGENT-965/result.json",
            evidence_path="/durable/agent-logs/AGENT-965/evidence.md",
        ),
        branch_name="feature/AGENT-965-host-execution-preflight",
        project_id="agentic-boilerplate",
        project_name="Agentic Boilerplate",
        project_root=str(source),
        repository="example-org/agentic-boilerplate",
        jira_project_key="AGENT",
        created_at="2026-09-12T11:50:00Z",
        updated_at="2026-09-12T11:50:00Z",
    )
    plan = AssignmentWorkspacePlan(
        assignment_id=assignment.id,
        jira_issue_key=assignment.jira_issue_key,
        role=assignment.role,
        mode=WorkspaceProvisioningMode.GIT_WORKTREE,
        workspace_path="/workspaces/AGENT-965/developer",
        source_repo_root=str(source),
        repository=assignment.repository,
        branch_name=assignment.branch_name,
        base_branch="main",
        shared_durable_paths=(
            SharedDurablePath("po-inbox", "/durable/po-inbox"),
            SharedDurablePath("agent-logs", "/durable/agent-logs"),
            SharedDurablePath("agent-state", "/durable/agent-state"),
            SharedDurablePath("codex-limits", "/durable/codex-limits"),
            SharedDurablePath("codex-jobs", "/durable/codex-jobs"),
            SharedDurablePath("codex-results", "/durable/codex-results"),
            SharedDurablePath("context-packs", "/durable/context-packs"),
        ),
        commands=(),
        issues=(),
    )
    return HostCodexPreflightRequest(
        assignment=assignment,
        workspace_plan=plan,
        checkout=HostCheckoutState(
            repository=assignment.repository,
            branch_name=assignment.branch_name,
            project_id=assignment.project_id,
            jira_project_key=assignment.jira_project_key,
            jira_issue_key=assignment.jira_issue_key,
            role=assignment.role,
            source_repo_root=str(source),
        ),
        scope=HostScopeState(
            jira_issue_key=assignment.jira_issue_key,
            jira_project_key=assignment.jira_project_key,
            project_id=assignment.project_id,
            role=assignment.role,
            status="READY TO START",
            accepted_ui_design_reference="not-required",
            context_revision_current=True,
            context_revision="ctx-1",
            assignment_lock_owner="worker-1",
            expected_worker_id="worker-1",
            assignment_reference="assignment-AGENT-965",
            po_inbox_reference="",
        ),
        limit_refresh=HostCodexLimitRefreshEvidence(
            record=_limit_record("availability-good", observed_at="2026-09-12T11:50:00Z", remaining=90),
            observation_id="availability-good",
            observed_at="2026-09-12T11:50:00Z",
            source=CodexLimitObservationSource.CODEX_APP_SERVER,
            account_scope_id="chatgpt-primary",
            bucket_id="codex",
        ),
        path_mappings=(
            HostPathMapping("/workspaces", str(workspaces), "workspaces"),
            HostPathMapping("/durable", str(durable), "durable"),
        ),
        permitted_output_roots=(str(durable),),
        now="2026-09-12T11:51:00Z",
        limit_stale_after_seconds=300,
    )


def _limit_record(record_id: str, *, observed_at: str, remaining: int):
    window = CodexLimitWindowAvailability(
        status=CodexLimitWindowStatus.AVAILABLE,
        remaining_percent=remaining,
        reset_at="2026-09-19T11:50:00Z",
        observation_source=CodexLimitObservationSource.CODEX_APP_SERVER,
        observed_at=observed_at,
        window_id="primary",
        label="Codex primary",
        bucket_id="codex",
        window_name="primary",
        window_duration_minutes=10080,
    )
    return build_single_pool_codex_limit_availability_record(
        record_id=record_id,
        pool=window,
        account_scope_id="chatgpt-primary",
    )


def _kinds(decision):
    return {issue.kind for issue in decision.issues}
