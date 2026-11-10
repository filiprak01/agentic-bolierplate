from agentic_boilerplate.domain import (
    AgentRole,
    AssignmentLockDecision,
    AssignmentLockStatus,
    AssignmentStatus,
    CodexLimitGateDecision,
    CodexLimitRecommendedAction,
    DefinitionOfReadyInput,
    GateBlocker,
    GateBlockerKind,
    GateDecision,
    GateDecisionType,
    ReleaseScope,
    ScopeIssue,
    SprintRing,
    evaluate_definition_of_ready,
)
from agentic_boilerplate.domain.dependency_eligibility import build_dependency_graph_audit
from agentic_boilerplate.integrations.jira import JiraIssueDependencyLinks
from agentic_boilerplate.scheduler.approved_scope_assignment import (
    SchedulerRejectionKind,
    SchedulerIssueCandidate,
    build_approved_scope_assignment_plan,
    build_scheduler_fallback_plan,
    persist_assignment_plan,
    render_scheduler_fallback_plan,
    scheduler_fallback_plan_to_dict,
)
from agentic_boilerplate.scheduler import build_approved_scope_assignment_plan as exported_assignment_plan
from agentic_boilerplate.storage import FileAgentAssignmentStore


def test_scheduler_assigns_only_ready_in_scope_unblocked_issues() -> None:
    plan = build_approved_scope_assignment_plan(
        _release_scope(),
        sprint_ring_number=6,
        candidates=(
            _candidate("AGENT-41", status="READY TO START", dependency_passed=True),
            _candidate("AGENT-42", status="FUNNEL", dependency_passed=True),
            _candidate("AGENT-99", status="READY TO START", dependency_passed=True),
            _candidate("AGENT-131", status="READY TO START", dependency_passed=False),
        ),
        created_at="2026-06-22T19:30:00Z",
    )

    assert [assignment.jira_issue_key for assignment in plan.assignments] == ["AGENT-41"]
    assert plan.assignments[0].status is AssignmentStatus.QUEUED
    assert {rejected.issue_key: rejected.reason for rejected in plan.rejected} == {
        "AGENT-42": "Issue is not READY TO START.",
        "AGENT-99": "Issue is outside the approved sprint ring.",
        "AGENT-131": "Issue has unresolved prerequisites.",
    }


def test_scheduler_skips_definition_of_ready_failure_and_assigns_next_eligible_story() -> None:
    blocked = _candidate(
        "AGENT-41",
        status="READY TO START",
        dependency_passed=True,
        definition_of_ready=evaluate_definition_of_ready(
            DefinitionOfReadyInput(
                **{
                    **_definition_ready_input("AGENT-41").__dict__,
                    "context_pack_path": "",
                }
            )
        ),
    )
    eligible = _candidate(
        "AGENT-131",
        status="READY TO START",
        dependency_passed=True,
        definition_of_ready=evaluate_definition_of_ready(_definition_ready_input("AGENT-131")),
    )

    plan = build_approved_scope_assignment_plan(
        _release_scope(),
        sprint_ring_number=6,
        candidates=(blocked, eligible),
        created_at="2026-06-22T19:30:00Z",
    )

    assert [assignment.jira_issue_key for assignment in plan.assignments] == ["AGENT-131"]
    assert plan.rejected[0].issue_key == "AGENT-41"
    assert "Definition of Ready failed" in plan.rejected[0].reason
    assert "missing_context_pack" in plan.rejected[0].reason


def test_scheduler_rejects_dependency_graph_cycles_before_assignment() -> None:
    audit = build_dependency_graph_audit(
        (
            JiraIssueDependencyLinks(issue_key="AGENT-41", blockers=("AGENT-131",)),
            JiraIssueDependencyLinks(issue_key="AGENT-131", blockers=("AGENT-41",)),
        )
    )

    plan = build_approved_scope_assignment_plan(
        _release_scope(),
        sprint_ring_number=6,
        candidates=(
            _candidate("AGENT-41", status="READY TO START", dependency_passed=True),
            _candidate("AGENT-131", status="READY TO START", dependency_passed=True),
        ),
        created_at="2026-06-22T19:30:00Z",
        dependency_graph_audit=audit,
    )

    assert plan.assignments == ()
    assert {rejected.issue_key: rejected.kind for rejected in plan.rejected} == {
        "AGENT-41": SchedulerRejectionKind.DEPENDENCY_GRAPH_BLOCKED,
        "AGENT-131": SchedulerRejectionKind.DEPENDENCY_GRAPH_BLOCKED,
    }
    assert all("Dependency graph audit" in rejected.reason for rejected in plan.rejected)
    assert all(rejected.details for rejected in plan.rejected)


def test_scheduler_rejects_candidate_without_definition_of_ready_decision() -> None:
    plan = build_approved_scope_assignment_plan(
        _release_scope(),
        sprint_ring_number=6,
        candidates=(
            _candidate(
                "AGENT-41",
                status="READY TO START",
                dependency_passed=True,
                definition_of_ready=None,
            ),
        ),
        created_at="2026-06-22T19:30:00Z",
    )

    assert plan.assignments == ()
    assert plan.rejected[0].reason == "Definition of Ready decision is missing."


def test_scheduler_fallback_assigns_next_same_role_story_when_dependency_blocks_preferred() -> None:
    plan = build_scheduler_fallback_plan(
        _release_scope(),
        sprint_ring_number=6,
        preferred_issue_key="AGENT-41",
        candidates=(
            _candidate("AGENT-41", status="READY TO START", dependency_passed=False),
            _candidate("AGENT-131", status="READY TO START", dependency_passed=True),
        ),
        created_at="2026-08-10T02:40:00Z",
    )

    assert plan.selected_assignment is not None
    assert plan.selected_assignment.jira_issue_key == "AGENT-131"
    assert plan.fallback_used is True
    assert plan.paused_reason == ""
    assert plan.skipped[0].issue_key == "AGENT-41"
    assert plan.skipped[0].kind is SchedulerRejectionKind.DEPENDENCY_BLOCKED


def test_scheduler_fallback_skips_po_block_and_records_inbox_state() -> None:
    plan = build_scheduler_fallback_plan(
        _release_scope(),
        sprint_ring_number=6,
        preferred_issue_key="AGENT-41",
        candidates=(
            _candidate(
                "AGENT-41",
                status="READY TO START",
                dependency_passed=True,
                po_inbox_item_id="po-question-1",
                po_block_reason="Product Owner must choose an implementation path.",
            ),
            _candidate("AGENT-131", status="READY TO START", dependency_passed=True),
        ),
        created_at="2026-08-10T02:40:00Z",
    )

    assert plan.selected_assignment is not None
    assert plan.selected_assignment.jira_issue_key == "AGENT-131"
    assert plan.skipped[0].kind is SchedulerRejectionKind.PO_BLOCKED
    assert plan.skipped[0].details == (
        "po-question-1",
        "Product Owner must choose an implementation path.",
    )


def test_scheduler_fallback_skips_limit_block_and_pauses_when_nothing_else_can_run() -> None:
    plan = build_scheduler_fallback_plan(
        _release_scope(),
        sprint_ring_number=6,
        preferred_issue_key="AGENT-41",
        candidates=(
            _candidate(
                "AGENT-41",
                status="READY TO START",
                dependency_passed=True,
                codex_limit_gate=CodexLimitGateDecision(
                    allowed=False,
                    action=CodexLimitRecommendedAction.WAIT,
                    reason="Primary quota window is too close to exhaustion.",
                    resume_after="2026-08-10T07:00:00Z",
                ),
            ),
            _candidate("AGENT-131", status="FUNNEL", dependency_passed=True),
        ),
        created_at="2026-08-10T02:40:00Z",
    )

    assert plan.selected_assignment is None
    assert plan.fallback_used is False
    assert "No eligible READY TO START issue" in plan.paused_reason
    assert [rejected.kind for rejected in plan.skipped] == [
        SchedulerRejectionKind.CODEX_LIMIT_BLOCKED,
        SchedulerRejectionKind.STATUS_NOT_READY,
    ]


def test_scheduler_fallback_respects_assignment_locks() -> None:
    plan = build_scheduler_fallback_plan(
        _release_scope(),
        sprint_ring_number=6,
        preferred_issue_key="AGENT-41",
        candidates=(
            _candidate(
                "AGENT-41",
                status="READY TO START",
                dependency_passed=True,
                assignment_lock=AssignmentLockDecision(
                    jira_issue_key="AGENT-41",
                    worker_session_id="scheduler-2",
                    allowed=False,
                    status=AssignmentLockStatus.BLOCKED,
                    reasons=("Active lock is held by scheduler-1 for AGENT-41.",),
                ),
            ),
            _candidate("AGENT-131", status="READY TO START", dependency_passed=True),
        ),
        created_at="2026-08-10T02:40:00Z",
    )

    assert plan.selected_assignment is not None
    assert plan.selected_assignment.jira_issue_key == "AGENT-131"
    assert plan.skipped[0].kind is SchedulerRejectionKind.ASSIGNMENT_LOCKED
    assert "Active lock is held" in plan.skipped[0].reason


def test_scheduler_fallback_pauses_when_preferred_story_is_missing_without_role_context() -> None:
    plan = build_scheduler_fallback_plan(
        _release_scope(),
        sprint_ring_number=6,
        preferred_issue_key="AGENT-41",
        candidates=(_candidate("AGENT-131", status="READY TO START", dependency_passed=True),),
        created_at="2026-08-10T02:40:00Z",
    )

    assert plan.selected_assignment is None
    assert plan.skipped[0].kind is SchedulerRejectionKind.MISSING_PREFERRED
    assert plan.paused_reason == "Preferred issue was not present and no preferred role was provided."


def test_scheduler_fallback_can_use_explicit_role_when_preferred_story_is_missing() -> None:
    plan = build_scheduler_fallback_plan(
        _release_scope(),
        sprint_ring_number=6,
        preferred_issue_key="AGENT-41",
        preferred_role=AgentRole.SCHEDULER,
        candidates=(_candidate("AGENT-131", status="READY TO START", dependency_passed=True),),
        created_at="2026-08-10T02:40:00Z",
    )

    assert plan.selected_assignment is not None
    assert plan.selected_assignment.jira_issue_key == "AGENT-131"
    assert plan.fallback_used is True
    assert plan.skipped[0].kind is SchedulerRejectionKind.MISSING_PREFERRED


def test_scheduler_fallback_rendering_records_blocked_state_and_selected_work() -> None:
    plan = build_scheduler_fallback_plan(
        _release_scope(),
        sprint_ring_number=6,
        preferred_issue_key="AGENT-41",
        candidates=(
            _candidate(
                "AGENT-41",
                status="READY TO START",
                dependency_passed=True,
                po_inbox_item_id="po-question-1",
                po_block_reason="Product Owner must choose an implementation path.",
            ),
            _candidate("AGENT-131", status="READY TO START", dependency_passed=True),
        ),
        created_at="2026-08-10T02:40:00Z",
    )

    rendered = render_scheduler_fallback_plan(plan)
    payload = scheduler_fallback_plan_to_dict(plan)

    assert "Selected issue: AGENT-131" in rendered
    assert "AGENT-41: po_blocked" in rendered
    assert "po-question-1" in rendered
    assert payload["preferred_issue_key"] == "AGENT-41"
    assert payload["selected_assignment"]["jira_issue_key"] == "AGENT-131"
    assert payload["skipped"][0]["kind"] == "po_blocked"


def test_scheduler_fallback_rendering_records_pause_when_no_story_is_available() -> None:
    plan = build_scheduler_fallback_plan(
        _release_scope(),
        sprint_ring_number=6,
        preferred_issue_key="AGENT-41",
        candidates=(
            _candidate("AGENT-41", status="READY TO START", dependency_passed=False),
            _candidate("AGENT-131", status="FUNNEL", dependency_passed=True),
        ),
        created_at="2026-08-10T02:40:00Z",
    )

    rendered = render_scheduler_fallback_plan(plan)
    payload = scheduler_fallback_plan_to_dict(plan)

    assert "Selected issue: None" in rendered
    assert "Paused reason: No eligible READY TO START issue" in rendered
    assert payload["selected_assignment"] is None
    assert payload["paused_reason"].startswith("No eligible READY TO START issue")


def test_scheduler_can_assign_out_of_scope_only_with_po_override() -> None:
    without_override = build_approved_scope_assignment_plan(
        _release_scope(),
        sprint_ring_number=6,
        candidates=(_candidate("AGENT-99", status="READY TO START", dependency_passed=True),),
        created_at="2026-06-22T19:30:00Z",
    )
    with_override = build_approved_scope_assignment_plan(
        _release_scope(),
        sprint_ring_number=6,
        candidates=(_candidate("AGENT-99", status="READY TO START", dependency_passed=True),),
        created_at="2026-06-22T19:30:00Z",
        allow_out_of_scope_override=True,
        override_reason="PO approved urgent scheduling correction.",
    )

    assert without_override.assignments == ()
    assert with_override.assignments[0].jira_issue_key == "AGENT-99"
    assert with_override.override_reason == "PO approved urgent scheduling correction."


def test_scheduler_assignment_plan_persists_durable_records(tmp_path) -> None:
    store = FileAgentAssignmentStore(tmp_path)
    plan = build_approved_scope_assignment_plan(
        _release_scope(),
        sprint_ring_number=6,
        candidates=(_candidate("AGENT-41", status="READY TO START", dependency_passed=True),),
        created_at="2026-06-22T19:30:00Z",
    )

    persisted = persist_assignment_plan(plan, store)

    assert persisted == plan.assignments
    restored = store.read_assignment("assignment-AGENT-41")
    assert restored.jira_issue_key == "AGENT-41"
    assert restored.paths.context_pack_path == "data/context-packs/AGENT-41/context.json"


def test_scheduler_exports_assignment_workflow() -> None:
    assert exported_assignment_plan is build_approved_scope_assignment_plan


def _release_scope() -> ReleaseScope:
    return ReleaseScope(
        key="MVP-R1",
        name="MVP Release 1",
        release_version="1.0.0",
        description="MVP release scope",
        created_at="2026-06-22T19:00:00Z",
        sprint_rings=(
            SprintRing(
                number=6,
                name="Sprint 6",
                capacity_target="one Codex Plus window",
                complexity_total=6,
                included_issues=(
                    ScopeIssue(
                        key="AGENT-41",
                        title="Scheduler approved scope assignment workflow",
                        issue_type="Story",
                        complexity_points=3,
                        status="READY TO START",
                    ),
                    ScopeIssue(
                        key="AGENT-131",
                        title="Sprint acceptance and dependency gate workflow",
                        issue_type="Story",
                        complexity_points=3,
                        status="READY TO START",
                    ),
                ),
            ),
        ),
    )


def _candidate(
    issue_key: str,
    *,
    status: str,
    dependency_passed: bool,
    definition_of_ready="default",
    role: AgentRole = AgentRole.SCHEDULER,
    po_inbox_item_id: str = "",
    po_block_reason: str = "",
    assignment_lock: AssignmentLockDecision | None = None,
    codex_limit_gate: CodexLimitGateDecision | None = None,
    conflict_reason: str = "",
    unresolved_linked_bug_keys: tuple[str, ...] = (),
) -> SchedulerIssueCandidate:
    if definition_of_ready == "default":
        definition_of_ready = evaluate_definition_of_ready(
            DefinitionOfReadyInput(
                **{
                    **_definition_ready_input(issue_key).__dict__,
                    "status": status,
                }
            )
        )
    return SchedulerIssueCandidate(
        issue_key=issue_key,
        title=f"{issue_key} candidate",
        status=status,
        role=role,
        dependency_gate=GateDecision(
            decision_type=GateDecisionType.SCHEDULER_ASSIGNMENT,
            issue_key=issue_key,
            passed=dependency_passed,
            blockers=()
            if dependency_passed
            else (
                GateBlocker(
                    kind=GateBlockerKind.STATUS_NOT_TECHNICALLY_COMPLETE,
                    issue_key="AGENT-1",
                    message="Prerequisite not technically complete.",
                ),
            ),
            reasons=("ok",) if dependency_passed else ("blocked",),
        ),
        context_pack_path=f"data/context-packs/{issue_key}/context.json",
        codex_job_path=f"data/codex-jobs/{issue_key}/job.json",
        output_path=f"data/codex-results/{issue_key}/result.json",
        branch_name=f"feature/{issue_key.lower()}",
        definition_of_ready=definition_of_ready,
        assignment_lock=assignment_lock,
        codex_limit_gate=codex_limit_gate,
        po_inbox_item_id=po_inbox_item_id,
        po_block_reason=po_block_reason,
        conflict_reason=conflict_reason,
        unresolved_linked_bug_keys=unresolved_linked_bug_keys,
    )


def _definition_ready_input(issue_key: str) -> DefinitionOfReadyInput:
    return DefinitionOfReadyInput(
        issue_key=issue_key,
        issue_type="Story",
        status="READY TO START",
        labels=("release-1-2-0", "sprint-r12-s6"),
        sprint_name="Sprint 6",
        acceptance_criteria=("Story is ready for assignment.",),
        context_pack_path=f"data/context-packs/{issue_key}/context.json",
        role_route="role-scheduler",
        model="gpt-5.4",
        reasoning="high",
        target_repositories=("example-org/agentic-boilerplate",),
        target_workspace_path="/workspace/agentic-bolierplate",
    )