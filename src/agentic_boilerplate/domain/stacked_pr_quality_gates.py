"""CI and quality gate policy for stacked pull requests."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum


class StackedQualityCheckScope(str, Enum):
    """Scope of a quality check in a stacked PR flow."""

    LAYER_LOCAL = "layer-local"
    INTEGRATED_STACK = "integrated-stack"


class StackedQualityCheckType(str, Enum):
    """Supported stacked PR quality checks."""

    FORMAT_LINT = "format-lint"
    UNIT_CHANGED_MODULES = "unit-changed-modules"
    SECURITY_STATIC = "security-static"
    METADATA_VALIDATION = "metadata-validation"
    BROADER_UNIT_INTEGRATION = "broader-unit-integration"
    STACK_SMOKE_REGRESSION = "stack-smoke-regression"
    BRANCH_PROTECTION = "branch-protection"
    MERGE_QUEUE_COMPATIBILITY = "merge-queue-compatibility"


class StackedQualityCheckStatus(str, Enum):
    """Observed status for one quality check."""

    PASSED = "passed"
    FAILED = "failed"
    PENDING = "pending"
    SKIPPED = "skipped"


class StackedQualityFailureImpact(str, Enum):
    """Impact of a failed stacked PR check."""

    LAYER_ONLY = "layer-only"
    INVALIDATES_UPPER_LAYERS = "invalidates-upper-layers"


class StackedQualityGateMode(str, Enum):
    """Repository capability mode for stacked PR gates."""

    FALLBACK_BRANCH_CHAIN = "fallback-branch-chain"
    MERGE_QUEUE_ENABLED = "merge-queue-enabled"


@dataclass(frozen=True)
class StackedQualityCheckRequirement:
    """One required quality check for a stacked PR layer or integrated stack."""

    check_type: StackedQualityCheckType
    scope: StackedQualityCheckScope
    required: bool = True
    reason: str = ""


@dataclass(frozen=True)
class StackedQualityCheckResult:
    """Observed check result with evidence visibility."""

    check_type: StackedQualityCheckType
    scope: StackedQualityCheckScope
    status: StackedQualityCheckStatus
    evidence_path: str = ""
    evidence_url: str = ""
    jira_visible: bool = True


@dataclass(frozen=True)
class StackedQualityGateContext:
    """Context that decides whether integrated stack checks are required."""

    story_key: str
    stack_id: str
    stack_layer: int
    changed_paths: tuple[str, ...]
    security_sensitive_paths: tuple[str, ...] = ()
    requires_integrated_checks: bool = False
    branch_protection_enabled: bool = True
    merge_queue_enabled: bool = False
    branch_protection_supports_merge_queue: bool = False


@dataclass(frozen=True)
class StackedQualityGatePolicy:
    """Required checks and repository capability mode for stacked PRs."""

    story_key: str
    stack_id: str
    stack_layer: int
    gate_mode: StackedQualityGateMode
    layer_required_checks: tuple[StackedQualityCheckRequirement, ...]
    integrated_required_checks: tuple[StackedQualityCheckRequirement, ...] = field(default_factory=tuple)
    branch_protection_required: bool = True
    merge_queue_supported: bool = False


@dataclass(frozen=True)
class StackedQualityGateDecision:
    """Quality gate readiness for review and merge."""

    story_key: str
    ready: bool
    mode: StackedQualityGateMode
    blockers: tuple[str, ...] = field(default_factory=tuple)
    layer_local_failed_checks: tuple[StackedQualityCheckType, ...] = field(default_factory=tuple)
    upper_layer_invalidating_checks: tuple[StackedQualityCheckType, ...] = field(default_factory=tuple)


class StackedQualityGateError(ValueError):
    """Raised when stacked PR quality gate inputs are invalid."""


def build_stacked_quality_gate_policy(context: StackedQualityGateContext) -> StackedQualityGatePolicy:
    """Build minimum required checks for one stacked PR context."""

    _validate_context(context)
    layer_checks = [
        StackedQualityCheckRequirement(
            StackedQualityCheckType.FORMAT_LINT,
            StackedQualityCheckScope.LAYER_LOCAL,
            reason="Formatting and linting must pass for every stacked PR layer.",
        ),
        StackedQualityCheckRequirement(
            StackedQualityCheckType.UNIT_CHANGED_MODULES,
            StackedQualityCheckScope.LAYER_LOCAL,
            reason="Unit tests touching changed modules must pass for every layer.",
        ),
        StackedQualityCheckRequirement(
            StackedQualityCheckType.METADATA_VALIDATION,
            StackedQualityCheckScope.LAYER_LOCAL,
            reason="Stack metadata must be valid and visible before review approval.",
        ),
    ]
    if _touches_security_sensitive_path(context):
        layer_checks.append(
            StackedQualityCheckRequirement(
                StackedQualityCheckType.SECURITY_STATIC,
                StackedQualityCheckScope.LAYER_LOCAL,
                reason="Security/static checks are required for security-sensitive changes.",
            )
        )

    integrated_checks: list[StackedQualityCheckRequirement] = []
    if context.requires_integrated_checks:
        integrated_checks.extend(
            [
                StackedQualityCheckRequirement(
                    StackedQualityCheckType.BROADER_UNIT_INTEGRATION,
                    StackedQualityCheckScope.INTEGRATED_STACK,
                    reason="Merged lower layers or merge groups need broader unit/integration coverage.",
                ),
                StackedQualityCheckRequirement(
                    StackedQualityCheckType.STACK_SMOKE_REGRESSION,
                    StackedQualityCheckScope.INTEGRATED_STACK,
                    reason="Stack-level smoke or regression-candidate checks catch integration risk.",
                ),
                StackedQualityCheckRequirement(
                    StackedQualityCheckType.BRANCH_PROTECTION,
                    StackedQualityCheckScope.INTEGRATED_STACK,
                    reason="Branch protection must remain active for stack merges.",
                ),
            ]
        )
        if context.merge_queue_enabled and context.branch_protection_supports_merge_queue:
            integrated_checks.append(
                StackedQualityCheckRequirement(
                    StackedQualityCheckType.MERGE_QUEUE_COMPATIBILITY,
                    StackedQualityCheckScope.INTEGRATED_STACK,
                    reason="Merge queue compatibility is required before queued stack merge.",
                )
            )

    merge_queue_supported = context.merge_queue_enabled and context.branch_protection_supports_merge_queue
    mode = (
        StackedQualityGateMode.MERGE_QUEUE_ENABLED
        if merge_queue_supported
        else StackedQualityGateMode.FALLBACK_BRANCH_CHAIN
    )
    return StackedQualityGatePolicy(
        story_key=context.story_key.strip(),
        stack_id=context.stack_id.strip(),
        stack_layer=context.stack_layer,
        gate_mode=mode,
        layer_required_checks=tuple(layer_checks),
        integrated_required_checks=tuple(integrated_checks),
        branch_protection_required=context.branch_protection_enabled,
        merge_queue_supported=merge_queue_supported,
    )


def evaluate_stacked_quality_gate(
    policy: StackedQualityGatePolicy,
    results: Sequence[StackedQualityCheckResult],
) -> StackedQualityGateDecision:
    """Evaluate required check results and evidence visibility."""

    _validate_policy(policy)
    result_by_key = {(result.check_type, result.scope): result for result in results}
    blockers: list[str] = []
    layer_failures: list[StackedQualityCheckType] = []
    upper_invalidating_failures: list[StackedQualityCheckType] = []

    for requirement in (*policy.layer_required_checks, *policy.integrated_required_checks):
        if not requirement.required:
            continue
        result = result_by_key.get((requirement.check_type, requirement.scope))
        if result is None:
            blockers.append(f"Missing required check: {requirement.check_type.value}.")
            continue
        blockers.extend(_result_blockers(result))
        if result.status == StackedQualityCheckStatus.FAILED:
            impact = classify_stacked_quality_failure_impact(result)
            if impact == StackedQualityFailureImpact.LAYER_ONLY:
                layer_failures.append(result.check_type)
            else:
                upper_invalidating_failures.append(result.check_type)

    if policy.branch_protection_required and policy.integrated_required_checks and not any(
        requirement.check_type == StackedQualityCheckType.BRANCH_PROTECTION
        for requirement in policy.integrated_required_checks
    ):
        blockers.append("Branch protection compatibility must be documented before final stack merge.")

    return StackedQualityGateDecision(
        story_key=policy.story_key,
        ready=not blockers,
        mode=policy.gate_mode,
        blockers=tuple(blockers),
        layer_local_failed_checks=tuple(layer_failures),
        upper_layer_invalidating_checks=tuple(upper_invalidating_failures),
    )


def classify_stacked_quality_failure_impact(
    result: StackedQualityCheckResult,
) -> StackedQualityFailureImpact:
    """Classify whether a failed check blocks only one layer or upper layers too."""

    if result.scope == StackedQualityCheckScope.INTEGRATED_STACK:
        return StackedQualityFailureImpact.INVALIDATES_UPPER_LAYERS
    if result.check_type in {
        StackedQualityCheckType.METADATA_VALIDATION,
        StackedQualityCheckType.BRANCH_PROTECTION,
        StackedQualityCheckType.MERGE_QUEUE_COMPATIBILITY,
    }:
        return StackedQualityFailureImpact.INVALIDATES_UPPER_LAYERS
    return StackedQualityFailureImpact.LAYER_ONLY


def render_stacked_quality_gate_summary(decision: StackedQualityGateDecision) -> str:
    """Render Jira-visible quality gate readiness summary."""

    lines = [
        f"Stacked PR quality gate for {decision.story_key}: {'ready' if decision.ready else 'blocked'}.",
        f"Mode: {decision.mode.value}",
    ]
    if decision.blockers:
        lines.extend(["", "Blockers:"])
        lines.extend(f"- {blocker}" for blocker in decision.blockers)
    if decision.layer_local_failed_checks:
        lines.extend(["", "Layer-local failed checks:"])
        lines.extend(f"- {check.value}" for check in decision.layer_local_failed_checks)
    if decision.upper_layer_invalidating_checks:
        lines.extend(["", "Upper-layer invalidating checks:"])
        lines.extend(f"- {check.value}" for check in decision.upper_layer_invalidating_checks)
    return "\n".join(lines).strip()


def _result_blockers(result: StackedQualityCheckResult) -> tuple[str, ...]:
    blockers: list[str] = []
    if result.status != StackedQualityCheckStatus.PASSED:
        blockers.append(f"Required check {result.check_type.value} is {result.status.value}.")
    if not result.evidence_path.strip() and not result.evidence_url.strip():
        blockers.append(f"Required check {result.check_type.value} has no evidence link.")
    if not result.jira_visible:
        blockers.append(f"Required check {result.check_type.value} is not visible from Jira.")
    return tuple(blockers)


def _validate_context(context: StackedQualityGateContext) -> None:
    if not context.story_key.strip():
        raise StackedQualityGateError("story_key is required")
    if not context.stack_id.strip():
        raise StackedQualityGateError("stack_id is required")
    if context.stack_layer < 1:
        raise StackedQualityGateError("stack_layer must be 1 or greater")
    if not context.changed_paths:
        raise StackedQualityGateError("changed_paths is required")


def _validate_policy(policy: StackedQualityGatePolicy) -> None:
    if not policy.story_key.strip():
        raise StackedQualityGateError("story_key is required")
    if not policy.stack_id.strip():
        raise StackedQualityGateError("stack_id is required")
    if policy.stack_layer < 1:
        raise StackedQualityGateError("stack_layer must be 1 or greater")
    if not policy.layer_required_checks:
        raise StackedQualityGateError("layer_required_checks is required")


def _touches_security_sensitive_path(context: StackedQualityGateContext) -> bool:
    sensitive_prefixes = tuple(path.strip() for path in context.security_sensitive_paths if path.strip())
    if not sensitive_prefixes:
        return False
    return any(path.startswith(sensitive_prefixes) for path in context.changed_paths)
