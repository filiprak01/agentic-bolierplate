from agentic_boilerplate.domain import (
    DefinitionOfReadyBlockerKind,
    DefinitionOfReadyInput,
    evaluate_definition_of_ready,
    render_definition_of_ready_explanation,
)


def test_definition_of_ready_passes_when_required_assignment_context_exists() -> None:
    decision = evaluate_definition_of_ready(_ready_input())

    assert decision.ready is True
    assert decision.blockers == ()
    assert "AGENT-681 is READY TO START with executable context." in decision.reasons


def test_definition_of_ready_blocks_missing_context_design_repo_and_limits() -> None:
    decision = evaluate_definition_of_ready(
        DefinitionOfReadyInput(
            **{
                **_ready_input().__dict__,
                "context_pack_path": "",
                "target_repositories": (),
                "target_workspace_path": "",
                "limit_state_fresh": False,
                "ui_facing": True,
                "accepted_design_reference": "",
                "design_dependency_key": "",
            }
        )
    )

    kinds = {blocker.kind for blocker in decision.blockers}

    assert decision.ready is False
    assert DefinitionOfReadyBlockerKind.MISSING_CONTEXT_PACK in kinds
    assert DefinitionOfReadyBlockerKind.MISSING_TARGET_REPOSITORY in kinds
    assert DefinitionOfReadyBlockerKind.MISSING_TARGET_WORKSPACE in kinds
    assert DefinitionOfReadyBlockerKind.STALE_LIMIT_STATE in kinds
    assert DefinitionOfReadyBlockerKind.MISSING_DESIGN_REFERENCE in kinds
    assert DefinitionOfReadyBlockerKind.MISSING_DESIGN_DEPENDENCY in kinds


def test_definition_of_ready_requires_release_sprint_status_and_acceptance_criteria() -> None:
    decision = evaluate_definition_of_ready(
        DefinitionOfReadyInput(
            **{
                **_ready_input().__dict__,
                "status": "FUNNEL",
                "labels": ("release-1-2-0",),
                "sprint_name": "",
                "acceptance_criteria": (),
            }
        )
    )

    kinds = {blocker.kind for blocker in decision.blockers}

    assert DefinitionOfReadyBlockerKind.STATUS_NOT_READY in kinds
    assert DefinitionOfReadyBlockerKind.MISSING_RELEASE_OR_SPRINT in kinds
    assert DefinitionOfReadyBlockerKind.MISSING_ACCEPTANCE_CRITERIA in kinds


def test_definition_of_ready_blocks_unresolved_dependencies_bugs_and_setup() -> None:
    decision = evaluate_definition_of_ready(
        DefinitionOfReadyInput(
            **{
                **_ready_input().__dict__,
                "dependency_gate_passed": False,
                "unresolved_dependency_keys": ("AGENT-683",),
                "unresolved_linked_bug_keys": ("AGENT-900",),
                "setup_validation_passed": False,
            }
        )
    )

    blockers = {blocker.kind: blocker.related_keys for blocker in decision.blockers}

    assert blockers[DefinitionOfReadyBlockerKind.UNRESOLVED_DEPENDENCY] == ("AGENT-683",)
    assert blockers[DefinitionOfReadyBlockerKind.UNRESOLVED_LINKED_BUG] == ("AGENT-900",)
    assert DefinitionOfReadyBlockerKind.MISSING_SETUP_VALIDATION in blockers


def test_definition_of_ready_requires_multi_repo_change_map() -> None:
    decision = evaluate_definition_of_ready(
        DefinitionOfReadyInput(
            **{
                **_ready_input().__dict__,
                "target_repositories": ("process-repo", "target-project"),
                "repository_change_map": (),
            }
        )
    )

    assert decision.ready is False
    assert DefinitionOfReadyBlockerKind.MISSING_MULTI_REPO_CHANGE_MAP in {b.kind for b in decision.blockers}


def test_definition_of_ready_explanation_is_po_visible() -> None:
    decision = evaluate_definition_of_ready(
        DefinitionOfReadyInput(
            **{
                **_ready_input().__dict__,
                "limit_state_fresh": False,
            }
        )
    )

    explanation = render_definition_of_ready_explanation(decision)

    assert "# Definition of Ready - AGENT-681" in explanation
    assert "- Ready: no" in explanation
    assert "stale_limit_state" in explanation
    assert "Codex limit state must be fresh" in explanation


def _ready_input() -> DefinitionOfReadyInput:
    return DefinitionOfReadyInput(
        issue_key="AGENT-681",
        issue_type="Story",
        status="READY TO START",
        labels=("release-1-2-0", "sprint-r12-s1"),
        sprint_name="R1.2 S1 Foundation",
        acceptance_criteria=("The gate returns machine-readable pass/fail reasons.",),
        context_pack_path="data/context-packs/AGENT-681/context-pack.json",
        role_route="role-orchestrator",
        model="gpt-5.5",
        reasoning="high",
        target_repositories=("example-org/agentic-boilerplate",),
        target_workspace_path="/home/user/business/agentic-bolierplate-agent681",
        dependency_gate_passed=True,
        setup_validation_passed=True,
        limit_state_fresh=True,
    )
