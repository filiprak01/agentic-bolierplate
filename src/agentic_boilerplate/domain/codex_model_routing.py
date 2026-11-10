"""Codex model discovery and model/reasoning route decisions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from agentic_boilerplate.domain.codex_limit_availability import (
    DEFAULT_SHORT_WINDOW_STOP_THRESHOLD_PERCENT,
    CodexLimitAvailabilityRecord,
    CodexLimitRecommendedAction,
    CodexLimitWindowStatus,
    codex_limit_windows_for_display,
)
from agentic_boilerplate.domain.po_inbox import AgentRole
from agentic_boilerplate.domain.story_complexity import (
    DEFAULT_COMPLEXITY_ROUTING,
    DEFAULT_ROLE_ROUTING,
    ComplexityLevel,
    ComplexityRouting,
    ReasoningLevel,
    RoleRouting,
    RoutingSource,
)

SPARK_MODEL_ID = "gpt-5.3-codex-spark"
DEFAULT_MODEL_FALLBACK_ORDER = (
    "gpt-5.5",
    "gpt-5.4",
    "gpt-5.4-mini",
)
BACKBONE_ROLES = frozenset(
    {
        AgentRole.PRODUCT_PLANNING,
        AgentRole.ARCHITECTURE,
        AgentRole.SECURITY,
    }
)
DEFAULT_SPARK_ALLOWED_ROLES = frozenset(
    {
        AgentRole.TESTER,
        AgentRole.RELEASE_MANAGER,
        AgentRole.DOCS_CONFLUENCE,
        AgentRole.UI_UX,
        AgentRole.REVIEW,
    }
)
DEFAULT_SPARK_ALLOWED_COMPLEXITIES = frozenset(
    {
        ComplexityLevel.C1,
        ComplexityLevel.C2,
    }
)


class CodexModelRoutingStatus(str, Enum):
    """Outcome of a model route decision."""

    ALLOWED = "allowed"
    BLOCKED = "blocked"
    PO_SWITCH_REQUIRED = "po_switch_required"


class CodexModelRoutingError(ValueError):
    """Raised when model routing input cannot be interpreted safely."""


@dataclass(frozen=True)
class CodexModelCapability:
    """One model returned by Codex App Server `model/list`."""

    model_id: str
    display_name: str
    supported_reasoning_efforts: tuple[ReasoningLevel, ...]
    default_reasoning_effort: ReasoningLevel | None = None
    separate_limit_bucket_id: str = ""

    def supports(self, reasoning: ReasoningLevel) -> bool:
        """Return whether the model supports the requested reasoning effort."""

        return reasoning in self.supported_reasoning_efforts

    @property
    def is_spark(self) -> bool:
        """Return whether this capability represents the Spark model lane."""

        return is_spark_model(self.model_id, self.display_name)


@dataclass(frozen=True)
class CodexModelDiscoverySnapshot:
    """A normalized model inventory and related metered bucket ids."""

    snapshot_id: str
    observed_at: str
    models: tuple[CodexModelCapability, ...]
    limit_bucket_ids: tuple[str, ...] = ()

    @property
    def available_model_ids(self) -> tuple[str, ...]:
        """Return model ids in discovery order."""

        return tuple(model.model_id for model in self.models)

    def model_by_id(self, model_id: str) -> CodexModelCapability | None:
        """Return a discovered model by id."""

        normalized = model_id.strip()
        for model in self.models:
            if model.model_id == normalized:
                return model
        return None


@dataclass(frozen=True)
class CodexModelRouteConfig:
    """Configurable role/complexity routing matrix."""

    role_routes: Mapping[AgentRole, RoleRouting]
    complexity_routes: Mapping[ComplexityLevel, ComplexityRouting]
    fallback_model_order: tuple[str, ...] = DEFAULT_MODEL_FALLBACK_ORDER
    spark_enabled: bool = False
    spark_model_id: str = SPARK_MODEL_ID
    spark_allowed_roles: frozenset[AgentRole] = DEFAULT_SPARK_ALLOWED_ROLES
    spark_allowed_complexities: frozenset[ComplexityLevel] = DEFAULT_SPARK_ALLOWED_COMPLEXITIES
    limit_stop_threshold_percent: int = DEFAULT_SHORT_WINDOW_STOP_THRESHOLD_PERCENT


@dataclass(frozen=True)
class CodexModelRouteDecision:
    """Decision used before a Codex session or host runner spends quota."""

    status: CodexModelRoutingStatus
    role: AgentRole
    complexity: ComplexityLevel
    model_id: str
    reasoning: ReasoningLevel
    speed: str
    routing_source: RoutingSource
    reason: str
    rationale: str
    manual_switch_required: bool = False
    required_limit_bucket_id: str = ""
    available_model_ids: tuple[str, ...] = ()
    limit_bucket_ids: tuple[str, ...] = ()

    @property
    def allowed(self) -> bool:
        """Return whether work may start without more Product Owner action."""

        return self.status is CodexModelRoutingStatus.ALLOWED


def codex_model_capability_to_dict(model: CodexModelCapability) -> dict[str, Any]:
    """Serialize one model capability for evidence and diagnostics."""

    return {
        "model_id": model.model_id,
        "display_name": model.display_name,
        "supported_reasoning_efforts": [reasoning.value for reasoning in model.supported_reasoning_efforts],
        "default_reasoning_effort": model.default_reasoning_effort.value if model.default_reasoning_effort else None,
        "separate_limit_bucket_id": model.separate_limit_bucket_id,
        "is_spark": model.is_spark,
    }


def codex_model_discovery_snapshot_to_dict(snapshot: CodexModelDiscoverySnapshot) -> dict[str, Any]:
    """Serialize a model discovery snapshot."""

    return {
        "snapshot_id": snapshot.snapshot_id,
        "observed_at": snapshot.observed_at,
        "available_model_ids": list(snapshot.available_model_ids),
        "limit_bucket_ids": list(snapshot.limit_bucket_ids),
        "models": [codex_model_capability_to_dict(model) for model in snapshot.models],
    }


def codex_model_route_decision_to_dict(decision: CodexModelRouteDecision) -> dict[str, Any]:
    """Serialize a route decision for worker logs and Jira evidence."""

    return {
        "status": decision.status.value,
        "allowed": decision.allowed,
        "role": decision.role.value,
        "complexity": decision.complexity.value,
        "model_id": decision.model_id,
        "reasoning": decision.reasoning.value,
        "speed": decision.speed,
        "routing_source": decision.routing_source.value,
        "manual_switch_required": decision.manual_switch_required,
        "required_limit_bucket_id": decision.required_limit_bucket_id,
        "available_model_ids": list(decision.available_model_ids),
        "limit_bucket_ids": list(decision.limit_bucket_ids),
        "reason": decision.reason,
        "rationale": decision.rationale,
    }


def codex_model_discovery_snapshot_from_app_server(
    payload: Mapping[str, Any],
    *,
    observed_at: str,
    snapshot_id: str = "latest",
    rate_limits_payload: Mapping[str, Any] | None = None,
) -> CodexModelDiscoverySnapshot:
    """Normalize a Codex App Server `model/list` payload."""

    raw_models = _extract_model_list(payload)
    bucket_text_by_id = _limit_bucket_text_by_id(rate_limits_payload or {})
    limit_bucket_ids = tuple(bucket_text_by_id)
    models: list[CodexModelCapability] = []
    seen_ids: set[str] = set()
    for raw_model in raw_models:
        model = _capability_from_payload(raw_model, bucket_text_by_id=bucket_text_by_id)
        if model.model_id in seen_ids:
            continue
        seen_ids.add(model.model_id)
        models.append(model)
    if not models:
        raise CodexModelRoutingError("Codex App Server model/list returned no supported models.")
    return CodexModelDiscoverySnapshot(
        snapshot_id=_required_text(snapshot_id, "snapshot_id"),
        observed_at=_required_text(observed_at, "observed_at"),
        models=tuple(models),
        limit_bucket_ids=limit_bucket_ids,
    )


def codex_model_route_config_from_env(
    env: Mapping[str, str],
    *,
    role_routes: Mapping[AgentRole, RoleRouting] | None = None,
    complexity_routes: Mapping[ComplexityLevel, ComplexityRouting] | None = None,
) -> CodexModelRouteConfig:
    """Build routing config from defaults plus environment-style overrides."""

    resolved_role_routes = dict(role_routes or DEFAULT_ROLE_ROUTING)
    resolved_complexity_routes = dict(complexity_routes or DEFAULT_COMPLEXITY_ROUTING)
    fallback_order = _csv_values(_first_env(env, "CODEX_MODEL_FALLBACK_ORDER")) or DEFAULT_MODEL_FALLBACK_ORDER
    spark_model_id = _first_env(env, "CODEX_SPARK_MODEL_ID") or SPARK_MODEL_ID
    spark_enabled = _bool_env(_first_env(env, "CODEX_SPARK_ENABLED"), default=False)
    spark_roles = _roles_from_csv(_first_env(env, "CODEX_SPARK_ALLOWED_ROLES"))
    spark_complexities = _complexities_from_csv(_first_env(env, "CODEX_SPARK_ALLOWED_COMPLEXITIES"))
    limit_stop_threshold = _int_env(
        _first_env(env, "CODEX_MODEL_LIMIT_STOP_THRESHOLD_PERCENT"),
        default=DEFAULT_SHORT_WINDOW_STOP_THRESHOLD_PERCENT,
    )

    for role in AgentRole:
        role_key = role.value.upper()
        model = _first_env(
            env,
            f"CODEX_ROUTE_MODEL_{role_key}",
            f"CODEX_MODEL_ROLE_{role_key}",
            f"CODEX_MODEL_{role_key}",
        )
        reasoning = _optional_reasoning(
            _first_env(
                env,
                f"CODEX_ROUTE_REASONING_{role_key}",
                f"CODEX_REASONING_ROLE_{role_key}",
                f"CODEX_REASONING_{role_key}",
            )
        )
        speed = _first_env(env, f"CODEX_ROUTE_SPEED_{role_key}", f"CODEX_SPEED_ROLE_{role_key}")
        if model or reasoning or speed:
            current = resolved_role_routes.get(role)
            if current is None:
                current = RoleRouting(role=role, default_model="", reasoning=ReasoningLevel.HIGH, speed="normal", rationale="")
            resolved_role_routes[role] = RoleRouting(
                role=role,
                default_model=model or current.default_model,
                reasoning=reasoning or current.reasoning,
                speed=speed or current.speed,
                rationale=_override_rationale(current.rationale, "Environment override applied."),
            )

    for complexity in ComplexityLevel:
        level_key = complexity.value.upper()
        model = _first_env(
            env,
            f"CODEX_ROUTE_MODEL_COMPLEXITY_{level_key}",
            f"CODEX_MODEL_COMPLEXITY_{level_key}",
        )
        reasoning = _optional_reasoning(
            _first_env(
                env,
                f"CODEX_ROUTE_REASONING_COMPLEXITY_{level_key}",
                f"CODEX_REASONING_COMPLEXITY_{level_key}",
            )
        )
        speed = _first_env(
            env,
            f"CODEX_ROUTE_SPEED_COMPLEXITY_{level_key}",
            f"CODEX_SPEED_COMPLEXITY_{level_key}",
        )
        if model or reasoning or speed:
            current = resolved_complexity_routes[complexity]
            resolved_complexity_routes[complexity] = ComplexityRouting(
                level=current.level,
                name=current.name,
                points=current.points,
                default_model=model or current.default_model,
                reasoning=reasoning or current.reasoning,
                speed=speed or current.speed,
                c4_justification_required=current.c4_justification_required,
            )

    return CodexModelRouteConfig(
        role_routes=resolved_role_routes,
        complexity_routes=resolved_complexity_routes,
        fallback_model_order=tuple(fallback_order),
        spark_enabled=spark_enabled,
        spark_model_id=spark_model_id,
        spark_allowed_roles=spark_roles or DEFAULT_SPARK_ALLOWED_ROLES,
        spark_allowed_complexities=spark_complexities or DEFAULT_SPARK_ALLOWED_COMPLEXITIES,
        limit_stop_threshold_percent=limit_stop_threshold,
    )


def select_codex_model_route(
    *,
    role: AgentRole | str,
    complexity: ComplexityLevel | str,
    discovery: CodexModelDiscoverySnapshot,
    config: CodexModelRouteConfig | None = None,
    limit_record: CodexLimitAvailabilityRecord | None = None,
    current_model: str = "",
    current_reasoning: ReasoningLevel | str | None = None,
) -> CodexModelRouteDecision:
    """Select the model/reasoning route for one assignment."""

    resolved_role = _coerce_role(role)
    resolved_complexity = _coerce_complexity(complexity)
    resolved_config = config or codex_model_route_config_from_env({})
    role_route = resolved_config.role_routes.get(resolved_role)
    if role_route is not None:
        target_model = role_route.default_model
        target_reasoning = role_route.reasoning
        target_speed = role_route.speed
        routing_source = RoutingSource.ROLE
        rationale = f"{role_route.rationale} Complexity fallback remains {resolved_complexity.value}."
    else:
        complexity_route = resolved_config.complexity_routes[resolved_complexity]
        target_model = complexity_route.default_model
        target_reasoning = complexity_route.reasoning
        target_speed = complexity_route.speed
        routing_source = RoutingSource.COMPLEXITY_FALLBACK
        rationale = f"Complexity fallback {resolved_complexity.value} selected."

    if is_spark_model(target_model) and not _spark_route_allowed(
        role=resolved_role,
        complexity=resolved_complexity,
        config=resolved_config,
    ):
        return _blocked_decision(
            role=resolved_role,
            complexity=resolved_complexity,
            model_id=target_model,
            reasoning=target_reasoning,
            speed=target_speed,
            routing_source=routing_source,
            discovery=discovery,
            reason="Spark routing is disabled or not allowed for this role and complexity.",
            rationale=rationale,
        )

    selected, fallback_reason = _select_available_model(
        target_model=target_model,
        reasoning=target_reasoning,
        discovery=discovery,
        config=resolved_config,
        allow_fallback=resolved_role not in BACKBONE_ROLES,
    )
    if selected is None:
        reason = fallback_reason or f"Configured model {target_model!r} is unavailable."
        if resolved_role in BACKBONE_ROLES:
            reason = f"Backbone role {resolved_role.value!r} requires its configured model; {reason}"
        return _blocked_decision(
            role=resolved_role,
            complexity=resolved_complexity,
            model_id=target_model,
            reasoning=target_reasoning,
            speed=target_speed,
            routing_source=routing_source,
            discovery=discovery,
            reason=reason,
            rationale=rationale,
        )

    if selected.is_spark:
        bucket_decision = _spark_limit_bucket_decision(
            selected,
            limit_record=limit_record,
            threshold_percent=resolved_config.limit_stop_threshold_percent,
        )
        if bucket_decision:
            return _blocked_decision(
                role=resolved_role,
                complexity=resolved_complexity,
                model_id=selected.model_id,
                reasoning=target_reasoning,
                speed=target_speed,
                routing_source=routing_source,
                discovery=discovery,
                reason=bucket_decision,
                rationale=rationale,
                required_limit_bucket_id=selected.separate_limit_bucket_id,
            )

    normalized_current_reasoning = (
        _coerce_reasoning(current_reasoning) if current_reasoning is not None else None
    )
    manual_switch_required = bool(current_model.strip()) and current_model.strip() != selected.model_id
    manual_switch_required = manual_switch_required or (
        normalized_current_reasoning is not None and normalized_current_reasoning != target_reasoning
    )
    if manual_switch_required:
        return CodexModelRouteDecision(
            status=CodexModelRoutingStatus.PO_SWITCH_REQUIRED,
            role=resolved_role,
            complexity=resolved_complexity,
            model_id=selected.model_id,
            reasoning=target_reasoning,
            speed=target_speed,
            routing_source=routing_source,
            manual_switch_required=True,
            required_limit_bucket_id=selected.separate_limit_bucket_id,
            available_model_ids=discovery.available_model_ids,
            limit_bucket_ids=discovery.limit_bucket_ids,
            reason="Product Owner must switch the active Codex session before this work starts.",
            rationale=_decision_rationale(rationale, fallback_reason),
        )

    return CodexModelRouteDecision(
        status=CodexModelRoutingStatus.ALLOWED,
        role=resolved_role,
        complexity=resolved_complexity,
        model_id=selected.model_id,
        reasoning=target_reasoning,
        speed=target_speed,
        routing_source=routing_source,
        required_limit_bucket_id=selected.separate_limit_bucket_id,
        available_model_ids=discovery.available_model_ids,
        limit_bucket_ids=discovery.limit_bucket_ids,
        reason="Selected model and reasoning are available for the assignment.",
        rationale=_decision_rationale(rationale, fallback_reason),
    )


def is_spark_model(model_id: str, display_name: str = "") -> bool:
    """Return whether a model identity should be treated as Spark."""

    text = f"{model_id} {display_name}".casefold()
    return model_id.strip() == SPARK_MODEL_ID or "spark" in text


def _extract_model_list(payload: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    candidate: Any = payload
    for key in ("models", "items", "data"):
        value = payload.get(key)
        if isinstance(value, Mapping):
            candidate = value.get("models", value.get("items", value.get("data", value)))
            break
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            candidate = value
            break
    if isinstance(candidate, Mapping) and any(key in candidate for key in ("id", "model", "modelId")):
        return (candidate,)
    if not isinstance(candidate, Sequence) or isinstance(candidate, (str, bytes, bytearray)):
        raise CodexModelRoutingError("Codex App Server model/list payload must contain a model list.")
    result: list[Mapping[str, Any]] = []
    for index, item in enumerate(candidate):
        if not isinstance(item, Mapping):
            raise CodexModelRoutingError(f"model/list item {index} must be an object.")
        result.append(item)
    return tuple(result)


def _capability_from_payload(
    payload: Mapping[str, Any],
    *,
    bucket_text_by_id: Mapping[str, str],
) -> CodexModelCapability:
    model_id = _first_model_text(payload, "id", "model", "modelId", "model_id")
    if not model_id:
        raise CodexModelRoutingError("model/list item is missing a model id.")
    display_name = _first_model_text(
        payload,
        "displayName",
        "display_name",
        "name",
        "title",
    ) or model_id
    default_reasoning = _optional_reasoning(
        _first_model_text(payload, "defaultReasoningEffort", "default_reasoning_effort", "defaultReasoning")
    )
    supported = _supported_reasoning(payload)
    if not supported:
        supported = (default_reasoning,) if default_reasoning is not None else tuple(ReasoningLevel)
    return CodexModelCapability(
        model_id=model_id,
        display_name=display_name,
        supported_reasoning_efforts=supported,
        default_reasoning_effort=default_reasoning,
        separate_limit_bucket_id=_matching_limit_bucket_id(model_id, display_name, bucket_text_by_id),
    )


def _supported_reasoning(payload: Mapping[str, Any]) -> tuple[ReasoningLevel, ...]:
    candidate = None
    for key in (
        "supportedReasoningEfforts",
        "supported_reasoning_efforts",
        "reasoningEfforts",
        "reasoning_efforts",
        "supportedReasoning",
    ):
        value = payload.get(key)
        if value is not None:
            candidate = value
            break
    if candidate is None:
        return ()
    if isinstance(candidate, str):
        values: Sequence[Any] = _csv_values(candidate)
    elif isinstance(candidate, Sequence):
        values = candidate
    else:
        raise CodexModelRoutingError("Supported reasoning efforts must be a list or comma-separated text.")
    resolved: list[ReasoningLevel] = []
    for value in values:
        reasoning = _coerce_reasoning(value)
        if reasoning not in resolved:
            resolved.append(reasoning)
    return tuple(resolved)


def _limit_bucket_text_by_id(payload: Mapping[str, Any]) -> dict[str, str]:
    bucket_map = payload.get("rateLimitsByLimitId")
    buckets: dict[str, str] = {}
    if isinstance(bucket_map, Mapping):
        for bucket_id, bucket in bucket_map.items():
            text_parts = [str(bucket_id)]
            if isinstance(bucket, Mapping):
                for key in ("limitId", "limitName", "label"):
                    value = bucket.get(key)
                    if value is not None:
                        text_parts.append(str(value))
            buckets[_safe_text(bucket_id)] = " ".join(text_parts)
    legacy = payload.get("rateLimits")
    if isinstance(legacy, Mapping):
        bucket_id = _safe_text(legacy.get("limitId") or "codex")
        text_parts = [bucket_id]
        for key in ("limitName", "label"):
            value = legacy.get(key)
            if value is not None:
                text_parts.append(str(value))
        buckets.setdefault(bucket_id, " ".join(text_parts))
    if any(isinstance(payload.get(name), Mapping) for name in ("primary", "secondary")):
        bucket_id = _safe_text(payload.get("limitId") or "codex")
        buckets.setdefault(bucket_id, bucket_id)
    return buckets


def _matching_limit_bucket_id(
    model_id: str,
    display_name: str,
    bucket_text_by_id: Mapping[str, str],
) -> str:
    if not bucket_text_by_id:
        return ""
    model_match = _normalized_match_text(f"{model_id} {display_name}")
    for bucket_id, text in bucket_text_by_id.items():
        normalized_bucket = _normalized_match_text(text)
        if is_spark_model(model_id, display_name) and (
            "spark" in normalized_bucket or "bengalfox" in normalized_bucket
        ):
            return bucket_id
        if model_match and model_match in normalized_bucket:
            return bucket_id
    return ""


def _select_available_model(
    *,
    target_model: str,
    reasoning: ReasoningLevel,
    discovery: CodexModelDiscoverySnapshot,
    config: CodexModelRouteConfig,
    allow_fallback: bool,
) -> tuple[CodexModelCapability | None, str]:
    reasons: list[str] = []
    candidates = [target_model.strip()]
    if allow_fallback:
        candidates.extend(config.fallback_model_order)
    seen: set[str] = set()
    for model_id in candidates:
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        model = discovery.model_by_id(model_id)
        if model is None:
            reasons.append(f"{model_id} unavailable")
            continue
        if model.is_spark and model.model_id != target_model.strip() and not config.spark_enabled:
            reasons.append(f"{model_id} skipped because Spark fallback is disabled")
            continue
        if not model.supports(reasoning):
            supported = ", ".join(effort.value for effort in model.supported_reasoning_efforts)
            reasons.append(f"{model_id} does not support {reasoning.value} reasoning (supported: {supported})")
            continue
        if model.model_id != target_model.strip():
            return model, f"Fallback selected because {target_model!r} was not usable."
        return model, ""
    return None, "; ".join(reasons)


def _spark_route_allowed(
    *,
    role: AgentRole,
    complexity: ComplexityLevel,
    config: CodexModelRouteConfig,
) -> bool:
    return (
        config.spark_enabled
        and role in config.spark_allowed_roles
        and complexity in config.spark_allowed_complexities
    )


def _spark_limit_bucket_decision(
    model: CodexModelCapability,
    *,
    limit_record: CodexLimitAvailabilityRecord | None,
    threshold_percent: int,
) -> str:
    if not model.separate_limit_bucket_id:
        return "Spark routing requires model/list plus rate-limit bucket discovery for the Spark bucket."
    if limit_record is None:
        return "Spark routing requires a fresh account/rateLimits/read gate for its separate bucket."
    if limit_record.recommended_action is not CodexLimitRecommendedAction.RESUME:
        return "Spark routing is blocked because the selected Codex limit gate does not allow resume."
    matching_windows = [
        window
        for _, window in codex_limit_windows_for_display(limit_record)
        if window.bucket_id == model.separate_limit_bucket_id
    ]
    if not matching_windows:
        return f"Spark limit bucket {model.separate_limit_bucket_id!r} is not present in the selected gate."
    for window in matching_windows:
        if window.status is not CodexLimitWindowStatus.AVAILABLE:
            return f"Spark limit bucket {model.separate_limit_bucket_id!r} has a non-available window."
        if window.remaining_percent is not None and window.remaining_percent <= threshold_percent:
            return f"Spark limit bucket {model.separate_limit_bucket_id!r} is at or below the stop threshold."
    return ""


def _blocked_decision(
    *,
    role: AgentRole,
    complexity: ComplexityLevel,
    model_id: str,
    reasoning: ReasoningLevel,
    speed: str,
    routing_source: RoutingSource,
    discovery: CodexModelDiscoverySnapshot,
    reason: str,
    rationale: str,
    required_limit_bucket_id: str = "",
) -> CodexModelRouteDecision:
    return CodexModelRouteDecision(
        status=CodexModelRoutingStatus.BLOCKED,
        role=role,
        complexity=complexity,
        model_id=model_id,
        reasoning=reasoning,
        speed=speed,
        routing_source=routing_source,
        reason=reason,
        rationale=rationale,
        required_limit_bucket_id=required_limit_bucket_id,
        available_model_ids=discovery.available_model_ids,
        limit_bucket_ids=discovery.limit_bucket_ids,
    )


def _decision_rationale(base: str, fallback_reason: str) -> str:
    if fallback_reason:
        return f"{base} {fallback_reason}".strip()
    return base


def _first_env(env: Mapping[str, str], *keys: str) -> str:
    for key in keys:
        value = env.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _csv_values(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in str(value).split(",") if part.strip())


def _roles_from_csv(value: str) -> frozenset[AgentRole]:
    if not value.strip():
        return frozenset()
    return frozenset(_coerce_role(item) for item in _csv_values(value))


def _complexities_from_csv(value: str) -> frozenset[ComplexityLevel]:
    if not value.strip():
        return frozenset()
    return frozenset(_coerce_complexity(item) for item in _csv_values(value))


def _bool_env(value: str, *, default: bool) -> bool:
    text = str(value).strip().casefold()
    if not text:
        return default
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    raise CodexModelRoutingError(f"Invalid boolean value for model routing: {value!r}.")


def _int_env(value: str, *, default: int) -> int:
    if not str(value).strip():
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise CodexModelRoutingError(f"Invalid integer value for model routing: {value!r}.") from exc
    if parsed < 0 or parsed > 100:
        raise CodexModelRoutingError("Model routing percentage thresholds must stay within 0..100.")
    return parsed


def _coerce_role(value: AgentRole | str) -> AgentRole:
    if isinstance(value, AgentRole):
        return value
    text = str(value).strip()
    try:
        return AgentRole(text)
    except ValueError:
        try:
            return AgentRole[text.upper()]
        except KeyError as exc:
            raise CodexModelRoutingError(f"Unsupported agent role for model routing: {value!r}.") from exc


def _coerce_complexity(value: ComplexityLevel | str) -> ComplexityLevel:
    if isinstance(value, ComplexityLevel):
        return value
    text = str(value).strip().upper()
    try:
        return ComplexityLevel(text)
    except ValueError as exc:
        raise CodexModelRoutingError(f"Unsupported complexity for model routing: {value!r}.") from exc


def _optional_reasoning(value: Any) -> ReasoningLevel | None:
    if value is None or not str(value).strip():
        return None
    return _coerce_reasoning(value)


def _coerce_reasoning(value: ReasoningLevel | str | Any) -> ReasoningLevel:
    if isinstance(value, ReasoningLevel):
        return value
    text = str(value).strip().casefold().replace("_", "-")
    aliases = {
        "extra-high": ReasoningLevel.XHIGH,
        "x-high": ReasoningLevel.XHIGH,
        "xhigh": ReasoningLevel.XHIGH,
    }
    if text in aliases:
        return aliases[text]
    try:
        return ReasoningLevel(text)
    except ValueError as exc:
        raise CodexModelRoutingError(f"Unsupported reasoning effort for model routing: {value!r}.") from exc


def _first_model_text(payload: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if value is not None and str(value).strip():
            return _safe_text(value)
    return ""


def _required_text(value: Any, field_name: str) -> str:
    text = _safe_text(value)
    if not text:
        raise CodexModelRoutingError(f"{field_name} is required.")
    return text


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if len(text) > 200:
        return text[:100] + "..." + text[-97:]
    return text


def _normalized_match_text(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def _override_rationale(current: str, suffix: str) -> str:
    current = current.strip()
    return f"{current} {suffix}".strip() if current else suffix
