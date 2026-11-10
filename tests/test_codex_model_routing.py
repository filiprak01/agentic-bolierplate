from agentic_boilerplate.domain.codex_limit_availability import (
    CodexLimitObservationSource,
    CodexLimitPlanMode,
    CodexLimitWindowAvailability,
    CodexLimitWindowStatus,
    build_codex_limit_availability_record,
)
from agentic_boilerplate.domain.codex_model_routing import (
    SPARK_MODEL_ID,
    CodexModelRoutingStatus,
    codex_model_discovery_snapshot_from_app_server,
    codex_model_route_config_from_env,
    codex_model_route_decision_to_dict,
    select_codex_model_route,
)
from agentic_boilerplate.domain.po_inbox import AgentRole
from agentic_boilerplate.domain.story_complexity import ComplexityLevel, ReasoningLevel


MODEL_LIST_PAYLOAD = {
    "models": [
        {
            "id": "gpt-5.5",
            "displayName": "GPT-5.5",
            "supportedReasoningEfforts": ["medium", "high", "xhigh"],
            "defaultReasoningEffort": "high",
        },
        {
            "id": "gpt-5.4",
            "displayName": "GPT-5.4",
            "supportedReasoningEfforts": ["medium", "high"],
            "defaultReasoningEffort": "high",
        },
        {
            "id": "gpt-5.4-mini",
            "displayName": "GPT-5.4 Mini",
            "supportedReasoningEfforts": ["medium", "high"],
            "defaultReasoningEffort": "medium",
        },
        {
            "id": SPARK_MODEL_ID,
            "displayName": "GPT-5.3 Codex Spark",
            "supportedReasoningEfforts": ["low", "medium", "high"],
            "defaultReasoningEffort": "medium",
        },
    ]
}

RATE_LIMIT_PAYLOAD = {
    "rateLimits": {"limitId": "codex", "primary": {"usedPercent": 20, "resetsAt": 1789238788}},
    "rateLimitsByLimitId": {
        "codex": {
            "limitId": "codex",
            "limitName": "Codex",
            "primary": {"usedPercent": 20, "resetsAt": 1789238788},
        },
        "codex_bengalfox": {
            "limitId": "codex_bengalfox",
            "limitName": "GPT-5.3-Codex-Spark",
            "primary": {"usedPercent": 0, "resetsAt": 1789238788},
            "secondary": {"usedPercent": 0, "resetsAt": 1789825588},
        },
    },
}


def _snapshot(payload: dict = MODEL_LIST_PAYLOAD):
    return codex_model_discovery_snapshot_from_app_server(
        payload,
        observed_at="2026-09-12T13:55:00Z",
        snapshot_id="models-20260912T135500Z",
        rate_limits_payload=RATE_LIMIT_PAYLOAD,
    )


def _spark_limit_record():
    primary = CodexLimitWindowAvailability(
        status=CodexLimitWindowStatus.AVAILABLE,
        remaining_percent=100,
        reset_at="2026-09-12T18:00:00Z",
        observation_source=CodexLimitObservationSource.CODEX_APP_SERVER,
        observed_at="2026-09-12T13:55:00Z",
        window_id="codex_bengalfox_primary",
        label="Spark primary",
        bucket_id="codex_bengalfox",
        window_name="primary",
        window_duration_minutes=300,
    )
    secondary = CodexLimitWindowAvailability(
        status=CodexLimitWindowStatus.AVAILABLE,
        remaining_percent=100,
        reset_at="2026-09-19T18:00:00Z",
        observation_source=CodexLimitObservationSource.CODEX_APP_SERVER,
        observed_at="2026-09-12T13:55:00Z",
        window_id="codex_bengalfox_secondary",
        label="Spark secondary",
        authoritative=False,
        bucket_id="codex_bengalfox",
        window_name="secondary",
        window_duration_minutes=10080,
    )
    return build_codex_limit_availability_record(
        record_id="spark-availability-20260912T135500Z",
        short_window=primary,
        broad_quota=secondary,
        plan_mode=CodexLimitPlanMode.DYNAMIC,
        windows=(primary, secondary),
        account_scope_id="chatgpt-primary",
    )


def test_model_list_snapshot_records_reasoning_and_spark_bucket() -> None:
    snapshot = _snapshot()

    assert snapshot.available_model_ids == (
        "gpt-5.5",
        "gpt-5.4",
        "gpt-5.4-mini",
        SPARK_MODEL_ID,
    )
    assert snapshot.limit_bucket_ids == ("codex", "codex_bengalfox")
    gpt55 = snapshot.model_by_id("gpt-5.5")
    spark = snapshot.model_by_id(SPARK_MODEL_ID)

    assert gpt55 is not None
    assert ReasoningLevel.XHIGH in gpt55.supported_reasoning_efforts
    assert spark is not None
    assert spark.is_spark
    assert spark.separate_limit_bucket_id == "codex_bengalfox"


def test_env_override_parsing_updates_role_complexity_and_spark_config() -> None:
    config = codex_model_route_config_from_env(
        {
            "CODEX_ROUTE_MODEL_DEVELOPER": "gpt-5.4-mini",
            "CODEX_ROUTE_REASONING_DEVELOPER": "medium",
            "CODEX_MODEL_COMPLEXITY_C1": "gpt-5.4-mini",
            "CODEX_REASONING_COMPLEXITY_C1": "low",
            "CODEX_MODEL_FALLBACK_ORDER": "gpt-5.4-mini,gpt-5.4",
            "CODEX_SPARK_ENABLED": "true",
            "CODEX_SPARK_ALLOWED_ROLES": "tester,release_manager",
            "CODEX_SPARK_ALLOWED_COMPLEXITIES": "C1",
        }
    )

    assert config.role_routes[AgentRole.DEVELOPER].default_model == "gpt-5.4-mini"
    assert config.role_routes[AgentRole.DEVELOPER].reasoning == ReasoningLevel.MEDIUM
    assert config.complexity_routes[ComplexityLevel.C1].reasoning == ReasoningLevel.LOW
    assert config.fallback_model_order == ("gpt-5.4-mini", "gpt-5.4")
    assert config.spark_enabled is True
    assert config.spark_allowed_roles == frozenset({AgentRole.TESTER, AgentRole.RELEASE_MANAGER})
    assert config.spark_allowed_complexities == frozenset({ComplexityLevel.C1})


def test_developer_falls_back_to_available_coding_model_when_safe() -> None:
    snapshot = _snapshot(
        {
            "models": [
                {
                    "id": "gpt-5.4-mini",
                    "displayName": "GPT-5.4 Mini",
                    "supportedReasoningEfforts": ["medium", "high"],
                    "defaultReasoningEffort": "medium",
                }
            ]
        }
    )

    decision = select_codex_model_route(
        role=AgentRole.DEVELOPER,
        complexity=ComplexityLevel.C3,
        discovery=snapshot,
    )

    assert decision.status is CodexModelRoutingStatus.ALLOWED
    assert decision.model_id == "gpt-5.4-mini"
    assert decision.reasoning == ReasoningLevel.HIGH
    assert "Fallback selected" in decision.rationale


def test_unsupported_reasoning_blocks_when_no_safe_fallback_exists() -> None:
    snapshot = _snapshot(
        {
            "models": [
                {
                    "id": "gpt-5.4",
                    "displayName": "GPT-5.4",
                    "supportedReasoningEfforts": ["medium"],
                    "defaultReasoningEffort": "medium",
                }
            ]
        }
    )

    decision = select_codex_model_route(
        role=AgentRole.DEVELOPER,
        complexity=ComplexityLevel.C3,
        discovery=snapshot,
    )

    assert decision.status is CodexModelRoutingStatus.BLOCKED
    assert decision.allowed is False
    assert "does not support high reasoning" in decision.reason


def test_backbone_role_does_not_silently_downgrade() -> None:
    snapshot = _snapshot(
        {
            "models": [
                {
                    "id": "gpt-5.4",
                    "displayName": "GPT-5.4",
                    "supportedReasoningEfforts": ["medium", "high", "xhigh"],
                    "defaultReasoningEffort": "high",
                }
            ]
        }
    )

    decision = select_codex_model_route(
        role=AgentRole.ARCHITECTURE,
        complexity=ComplexityLevel.C3,
        discovery=snapshot,
    )

    assert decision.status is CodexModelRoutingStatus.BLOCKED
    assert decision.model_id == "gpt-5.5"
    assert "Backbone role" in decision.reason


def test_spark_requires_explicit_enablement_and_fresh_bucket_gate() -> None:
    snapshot = _snapshot()
    disabled_config = codex_model_route_config_from_env(
        {
            "CODEX_ROUTE_MODEL_TESTER": SPARK_MODEL_ID,
            "CODEX_ROUTE_REASONING_TESTER": "medium",
        }
    )

    disabled_decision = select_codex_model_route(
        role=AgentRole.TESTER,
        complexity=ComplexityLevel.C1,
        discovery=snapshot,
        config=disabled_config,
    )

    assert disabled_decision.status is CodexModelRoutingStatus.BLOCKED
    assert "Spark routing is disabled" in disabled_decision.reason

    enabled_config = codex_model_route_config_from_env(
        {
            "CODEX_ROUTE_MODEL_TESTER": SPARK_MODEL_ID,
            "CODEX_ROUTE_REASONING_TESTER": "medium",
            "CODEX_SPARK_ENABLED": "true",
        }
    )
    missing_gate = select_codex_model_route(
        role=AgentRole.TESTER,
        complexity=ComplexityLevel.C1,
        discovery=snapshot,
        config=enabled_config,
    )

    assert missing_gate.status is CodexModelRoutingStatus.BLOCKED
    assert "fresh account/rateLimits/read gate" in missing_gate.reason

    allowed = select_codex_model_route(
        role=AgentRole.TESTER,
        complexity=ComplexityLevel.C1,
        discovery=snapshot,
        config=enabled_config,
        limit_record=_spark_limit_record(),
    )

    assert allowed.status is CodexModelRoutingStatus.ALLOWED
    assert allowed.model_id == SPARK_MODEL_ID
    assert allowed.required_limit_bucket_id == "codex_bengalfox"


def test_manual_switch_required_and_decision_serializes_evidence() -> None:
    decision = select_codex_model_route(
        role=AgentRole.DEVELOPER,
        complexity=ComplexityLevel.C3,
        discovery=_snapshot(),
        current_model="gpt-5.5",
        current_reasoning=ReasoningLevel.XHIGH,
    )

    assert decision.status is CodexModelRoutingStatus.PO_SWITCH_REQUIRED
    assert decision.manual_switch_required is True
    assert decision.allowed is False

    evidence = codex_model_route_decision_to_dict(decision)

    assert evidence["status"] == "po_switch_required"
    assert evidence["model_id"] == "gpt-5.4"
    assert evidence["reasoning"] == "high"
    assert evidence["available_model_ids"] == ["gpt-5.5", "gpt-5.4", "gpt-5.4-mini", SPARK_MODEL_ID]
    assert evidence["limit_bucket_ids"] == ["codex", "codex_bengalfox"]
