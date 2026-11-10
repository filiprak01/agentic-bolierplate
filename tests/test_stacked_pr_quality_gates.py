import pytest

from agentic_boilerplate.domain import (
    StackedQualityCheckResult,
    StackedQualityCheckScope,
    StackedQualityCheckStatus,
    StackedQualityCheckType,
    StackedQualityFailureImpact,
    StackedQualityGateContext,
    StackedQualityGateError,
    StackedQualityGateMode,
    build_stacked_quality_gate_policy,
    classify_stacked_quality_failure_impact,
    evaluate_stacked_quality_gate,
    render_stacked_quality_gate_summary,
)


def test_layer_policy_requires_minimum_checks_for_every_stacked_pr_layer() -> None:
    policy = build_stacked_quality_gate_policy(_layer_context())
    check_types = {requirement.check_type for requirement in policy.layer_required_checks}

    assert policy.gate_mode is StackedQualityGateMode.FALLBACK_BRANCH_CHAIN
    assert StackedQualityCheckType.FORMAT_LINT in check_types
    assert StackedQualityCheckType.UNIT_CHANGED_MODULES in check_types
    assert StackedQualityCheckType.METADATA_VALIDATION in check_types
    assert StackedQualityCheckType.SECURITY_STATIC in check_types


def test_integrated_policy_requires_broader_checks_before_stack_merge() -> None:
    policy = build_stacked_quality_gate_policy(
        StackedQualityGateContext(
            **{
                **_layer_context().__dict__,
                "requires_integrated_checks": True,
            }
        )
    )
    integrated_types = {requirement.check_type for requirement in policy.integrated_required_checks}

    assert StackedQualityCheckType.BROADER_UNIT_INTEGRATION in integrated_types
    assert StackedQualityCheckType.STACK_SMOKE_REGRESSION in integrated_types
    assert StackedQualityCheckType.BRANCH_PROTECTION in integrated_types


def test_merge_queue_mode_requires_compatible_branch_protection() -> None:
    fallback = build_stacked_quality_gate_policy(
        StackedQualityGateContext(
            **{
                **_layer_context().__dict__,
                "requires_integrated_checks": True,
                "merge_queue_enabled": True,
                "branch_protection_supports_merge_queue": False,
            }
        )
    )
    queued = build_stacked_quality_gate_policy(
        StackedQualityGateContext(
            **{
                **_layer_context().__dict__,
                "requires_integrated_checks": True,
                "merge_queue_enabled": True,
                "branch_protection_supports_merge_queue": True,
            }
        )
    )

    assert fallback.gate_mode is StackedQualityGateMode.FALLBACK_BRANCH_CHAIN
    assert fallback.merge_queue_supported is False
    assert queued.gate_mode is StackedQualityGateMode.MERGE_QUEUE_ENABLED
    assert queued.merge_queue_supported is True
    assert any(
        requirement.check_type == StackedQualityCheckType.MERGE_QUEUE_COMPATIBILITY
        for requirement in queued.integrated_required_checks
    )


def test_gate_blocks_when_required_layer_evidence_is_missing_from_jira() -> None:
    policy = build_stacked_quality_gate_policy(_layer_context())
    results = tuple(
        _passed_result(requirement.check_type, requirement.scope)
        for requirement in policy.layer_required_checks
    )
    results = (
        *results[:-1],
        StackedQualityCheckResult(
            check_type=policy.layer_required_checks[-1].check_type,
            scope=policy.layer_required_checks[-1].scope,
            status=StackedQualityCheckStatus.PASSED,
            evidence_path="data/agent-logs/AGENT-693/metadata.md",
            jira_visible=False,
        ),
    )

    decision = evaluate_stacked_quality_gate(policy, results)

    assert decision.ready is False
    assert any("not visible from Jira" in blocker for blocker in decision.blockers)


def test_gate_reports_layer_local_failed_checks_without_invalidating_upper_layers() -> None:
    policy = build_stacked_quality_gate_policy(_layer_context())
    results = tuple(
        _passed_result(requirement.check_type, requirement.scope)
        for requirement in policy.layer_required_checks
    )
    failed_lint = StackedQualityCheckResult(
        check_type=StackedQualityCheckType.FORMAT_LINT,
        scope=StackedQualityCheckScope.LAYER_LOCAL,
        status=StackedQualityCheckStatus.FAILED,
        evidence_path="data/agent-logs/AGENT-693/lint.md",
    )

    decision = evaluate_stacked_quality_gate(policy, (failed_lint, *results[1:]))

    assert decision.ready is False
    assert decision.layer_local_failed_checks == (StackedQualityCheckType.FORMAT_LINT,)
    assert decision.upper_layer_invalidating_checks == ()
    assert (
        classify_stacked_quality_failure_impact(failed_lint)
        is StackedQualityFailureImpact.LAYER_ONLY
    )


def test_integrated_failed_check_invalidates_upper_layers() -> None:
    policy = build_stacked_quality_gate_policy(
        StackedQualityGateContext(
            **{
                **_layer_context().__dict__,
                "requires_integrated_checks": True,
            }
        )
    )
    failed_integration = StackedQualityCheckResult(
        check_type=StackedQualityCheckType.BROADER_UNIT_INTEGRATION,
        scope=StackedQualityCheckScope.INTEGRATED_STACK,
        status=StackedQualityCheckStatus.FAILED,
        evidence_path="data/agent-logs/AGENT-693/integration.md",
    )
    results = tuple(
        failed_integration
        if requirement.check_type == StackedQualityCheckType.BROADER_UNIT_INTEGRATION
        else _passed_result(requirement.check_type, requirement.scope)
        for requirement in (*policy.layer_required_checks, *policy.integrated_required_checks)
    )

    decision = evaluate_stacked_quality_gate(policy, results)
    summary = render_stacked_quality_gate_summary(decision)

    assert decision.ready is False
    assert decision.upper_layer_invalidating_checks == (
        StackedQualityCheckType.BROADER_UNIT_INTEGRATION,
    )
    assert "Upper-layer invalidating checks" in summary


def test_gate_ready_when_all_required_checks_pass_with_visible_evidence() -> None:
    policy = build_stacked_quality_gate_policy(
        StackedQualityGateContext(
            **{
                **_layer_context().__dict__,
                "requires_integrated_checks": True,
                "merge_queue_enabled": True,
                "branch_protection_supports_merge_queue": True,
            }
        )
    )
    results = tuple(
        _passed_result(requirement.check_type, requirement.scope)
        for requirement in (*policy.layer_required_checks, *policy.integrated_required_checks)
    )

    decision = evaluate_stacked_quality_gate(policy, results)

    assert decision.ready is True
    assert decision.mode is StackedQualityGateMode.MERGE_QUEUE_ENABLED
    assert render_stacked_quality_gate_summary(decision).startswith("Stacked PR quality gate for AGENT-693: ready.")


def test_quality_gate_context_requires_changed_paths() -> None:
    with pytest.raises(StackedQualityGateError) as exc:
        build_stacked_quality_gate_policy(
            StackedQualityGateContext(
                **{
                    **_layer_context().__dict__,
                    "changed_paths": (),
                }
            )
        )

    assert "changed_paths" in str(exc.value)


def _layer_context() -> StackedQualityGateContext:
    return StackedQualityGateContext(
        story_key="AGENT-693",
        stack_id="r12-s7-stack-core",
        stack_layer=2,
        changed_paths=(
            "src/agentic_boilerplate/domain/stacked_pr_quality_gates.py",
            "src/agentic_boilerplate/security/policy.py",
        ),
        security_sensitive_paths=("src/agentic_boilerplate/security",),
    )


def _passed_result(
    check_type: StackedQualityCheckType,
    scope: StackedQualityCheckScope,
) -> StackedQualityCheckResult:
    return StackedQualityCheckResult(
        check_type=check_type,
        scope=scope,
        status=StackedQualityCheckStatus.PASSED,
        evidence_path=f"data/agent-logs/AGENT-693/{check_type.value}.md",
        jira_visible=True,
    )
