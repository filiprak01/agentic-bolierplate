import pytest

from agentic_boilerplate.domain import (
    CodexLimitAvailabilityError,
    CodexLimitObservationSource,
    CodexLimitPlanMode,
    CodexLimitRecommendedAction,
    CodexLimitWindowAvailability,
    CodexLimitWindowStatus,
    build_codex_limit_availability_record,
    build_single_pool_codex_limit_availability_record,
    codex_limit_availability_record_from_dict,
    codex_limit_availability_record_to_dict,
    codex_limit_windows_for_display,
    decide_codex_limit_gate,
    recommend_codex_limit_action,
)


def test_record_round_trips_to_json_compatible_data() -> None:
    record = build_codex_limit_availability_record(
        record_id="availability-20260706T100000Z",
        short_window=_window(
            status=CodexLimitWindowStatus.AVAILABLE,
            remaining_percent=100,
            reset_at="2026-07-06T10:00:00Z",
        ),
        broad_quota=_window(
            status=CodexLimitWindowStatus.LIMITED,
            remaining_percent=40,
            reset_at="2026-07-13T00:00:00Z",
        ),
        account_scope_id="chatgpt-primary",
    )

    restored = codex_limit_availability_record_from_dict(codex_limit_availability_record_to_dict(record))

    assert restored == record
    assert record.recommended_action == CodexLimitRecommendedAction.DOWNGRADE_MODEL
    assert record.plan_mode == CodexLimitPlanMode.DUAL_WINDOW
    assert restored.account_scope_id == "chatgpt-primary"


def test_legacy_record_without_bucket_metadata_remains_loadable() -> None:
    legacy_window = {
        "status": "available",
        "remaining_percent": 75,
        "reset_at": "2026-09-07T10:00:00Z",
        "observation_source": "operator",
        "observed_at": "2026-09-02T13:00:00Z",
        "window_id": "primary",
        "label": "Primary window",
        "authoritative": True,
    }
    record = codex_limit_availability_record_from_dict(
        {
            "id": "legacy-record",
            "short_window": legacy_window,
            "broad_quota": legacy_window,
            "recommended_action": "resume",
            "note": "",
            "plan_mode": "single_pool",
            "windows": [legacy_window],
        }
    )

    assert record.short_window.bucket_id == ""
    assert record.short_window.window_name == ""
    assert record.short_window.window_duration_minutes is None
    assert decide_codex_limit_gate(record).allowed is True


def test_unknown_window_recommends_po_question() -> None:
    short_window = _window(
        status=CodexLimitWindowStatus.UNKNOWN,
        remaining_percent=None,
        reset_at="",
        source=CodexLimitObservationSource.UNKNOWN,
    )
    broad_quota = _window(
        status=CodexLimitWindowStatus.AVAILABLE,
        remaining_percent=55,
        reset_at="2026-07-13T00:00:00Z",
    )

    action = recommend_codex_limit_action(short_window=short_window, broad_quota=broad_quota)

    assert action == CodexLimitRecommendedAction.ASK_PRODUCT_OWNER


def test_single_pool_record_allows_resume_without_secondary_window() -> None:
    pool = _window(
        status=CodexLimitWindowStatus.AVAILABLE,
        remaining_percent=72,
        reset_at="2026-07-14T10:00:00Z",
        window_id="agentic_pool",
        label="Agentic usage pool",
    )
    record = build_single_pool_codex_limit_availability_record(
        record_id="availability-single-pool",
        pool=pool,
    )

    decision = decide_codex_limit_gate(record)
    labels = [label for label, _window in codex_limit_windows_for_display(record)]

    assert decision.allowed is True
    assert record.plan_mode == CodexLimitPlanMode.SINGLE_POOL
    assert record.short_window == pool
    assert record.broad_quota == pool
    assert labels == ["Agentic usage pool"]


def test_single_pool_payload_projects_visible_pool_for_legacy_fields() -> None:
    restored = codex_limit_availability_record_from_dict(
        {
            "id": "availability-app-server",
            "plan_mode": "single_pool",
            "recommended_action": "resume",
            "windows": [
                {
                    "status": "available",
                    "remaining_percent": 88,
                    "reset_at": "2026-07-14T10:00:00Z",
                    "observation_source": "codex_cli",
                    "observed_at": "2026-07-14T09:45:00Z",
                    "window_id": "app_server_primary",
                    "label": "Codex app-server primary",
                    "authoritative": True,
                }
            ],
        }
    )

    decision = decide_codex_limit_gate(restored)

    assert decision.allowed is True
    assert restored.short_window.window_id == "app_server_primary"
    assert restored.broad_quota.window_id == "app_server_primary"
    assert restored.windows[0].label == "Codex app-server primary"


def test_single_pool_near_exhaustion_recommends_wait() -> None:
    record = build_single_pool_codex_limit_availability_record(
        record_id="availability-single-pool-low",
        pool=_window(
            status=CodexLimitWindowStatus.AVAILABLE,
            remaining_percent=8,
            reset_at="2026-07-14T10:00:00Z",
            label="Agentic usage pool",
        ),
    )

    decision = decide_codex_limit_gate(record)

    assert record.recommended_action == CodexLimitRecommendedAction.WAIT
    assert decision.allowed is False
    assert "Agentic usage pool" in decision.reason
    assert decision.resume_after == "2026-07-14T10:00:00Z"


def test_short_window_limited_recommends_wait() -> None:
    action = recommend_codex_limit_action(
        short_window=_window(
            status=CodexLimitWindowStatus.LIMITED,
            remaining_percent=5,
            reset_at="2026-07-06T14:00:00Z",
        ),
        broad_quota=_window(
            status=CodexLimitWindowStatus.AVAILABLE,
            remaining_percent=80,
            reset_at="2026-07-13T00:00:00Z",
        ),
    )

    assert action == CodexLimitRecommendedAction.WAIT


def test_short_window_close_to_exhaustion_recommends_wait() -> None:
    action = recommend_codex_limit_action(
        short_window=_window(
            status=CodexLimitWindowStatus.AVAILABLE,
            remaining_percent=9,
            reset_at="2026-07-06T14:00:00Z",
        ),
        broad_quota=_window(
            status=CodexLimitWindowStatus.AVAILABLE,
            remaining_percent=80,
            reset_at="2026-07-13T00:00:00Z",
        ),
    )

    assert action == CodexLimitRecommendedAction.WAIT


def test_broad_quota_close_to_exhaustion_recommends_downgrade() -> None:
    action = recommend_codex_limit_action(
        short_window=_window(
            status=CodexLimitWindowStatus.AVAILABLE,
            remaining_percent=80,
            reset_at="2026-07-06T14:00:00Z",
        ),
        broad_quota=_window(
            status=CodexLimitWindowStatus.AVAILABLE,
            remaining_percent=6,
            reset_at="2026-07-13T00:00:00Z",
        ),
    )

    assert action == CodexLimitRecommendedAction.DOWNGRADE_MODEL


def test_display_uses_configured_dynamic_window_labels() -> None:
    record = build_codex_limit_availability_record(
        record_id="availability-dynamic",
        plan_mode=CodexLimitPlanMode.DYNAMIC,
        short_window=_window(
            status=CodexLimitWindowStatus.AVAILABLE,
            remaining_percent=91,
            reset_at="2026-07-14T10:00:00Z",
            window_id="primary",
            label="App-server primary",
        ),
        broad_quota=_window(
            status=CodexLimitWindowStatus.AVAILABLE,
            remaining_percent=64,
            reset_at="2026-07-21T10:00:00Z",
            window_id="secondary",
            label="Subscription credits",
        ),
    )

    labels = [label for label, _window in codex_limit_windows_for_display(record)]

    assert labels == ["App-server primary", "Subscription credits"]


def test_gate_blocks_when_no_limit_record_is_available() -> None:
    decision = decide_codex_limit_gate(None)

    assert decision.allowed is False
    assert decision.action == CodexLimitRecommendedAction.ASK_PRODUCT_OWNER
    assert "No Codex limit availability record" in decision.reason


def test_gate_blocks_waiting_record_and_exposes_resume_after() -> None:
    record = build_codex_limit_availability_record(
        record_id="availability-20260706T100000Z",
        short_window=_window(
            status=CodexLimitWindowStatus.AVAILABLE,
            remaining_percent=9,
            reset_at="2026-07-06T14:00:00Z",
        ),
        broad_quota=_window(
            status=CodexLimitWindowStatus.AVAILABLE,
            remaining_percent=80,
            reset_at="2026-07-13T00:00:00Z",
        ),
    )

    decision = decide_codex_limit_gate(record)

    assert decision.allowed is False
    assert decision.action == CodexLimitRecommendedAction.WAIT
    assert decision.resume_after == "2026-07-06T14:00:00Z"


def test_gate_downgrade_prefers_broad_quota_resume_after() -> None:
    record = build_codex_limit_availability_record(
        record_id="availability-20260706T100000Z",
        short_window=_window(
            status=CodexLimitWindowStatus.AVAILABLE,
            remaining_percent=80,
            reset_at="2026-07-06T14:00:00Z",
        ),
        broad_quota=_window(
            status=CodexLimitWindowStatus.AVAILABLE,
            remaining_percent=6,
            reset_at="2026-07-13T00:00:00Z",
        ),
    )

    decision = decide_codex_limit_gate(record)

    assert decision.allowed is False
    assert decision.action == CodexLimitRecommendedAction.DOWNGRADE_MODEL
    assert decision.resume_after == "2026-07-13T00:00:00Z"


def test_gate_allows_resume_record() -> None:
    record = build_codex_limit_availability_record(
        record_id="availability-20260706T100000Z",
        short_window=_window(
            status=CodexLimitWindowStatus.AVAILABLE,
            remaining_percent=80,
            reset_at="2026-07-06T14:00:00Z",
        ),
        broad_quota=_window(
            status=CodexLimitWindowStatus.AVAILABLE,
            remaining_percent=80,
            reset_at="2026-07-13T00:00:00Z",
        ),
    )

    decision = decide_codex_limit_gate(record)

    assert decision.allowed is True
    assert decision.action == CodexLimitRecommendedAction.RESUME


def test_gate_blocks_stale_record_when_threshold_is_supplied() -> None:
    record = build_codex_limit_availability_record(
        record_id="availability-20260706T100000Z",
        short_window=_window(
            status=CodexLimitWindowStatus.AVAILABLE,
            remaining_percent=80,
            reset_at="2026-07-06T14:00:00Z",
        ),
        broad_quota=_window(
            status=CodexLimitWindowStatus.AVAILABLE,
            remaining_percent=80,
            reset_at="2026-07-13T00:00:00Z",
        ),
    )

    decision = decide_codex_limit_gate(
        record,
        now="2026-07-06T09:36:00Z",
        stale_after_seconds=300,
    )

    assert decision.allowed is False
    assert decision.action == CodexLimitRecommendedAction.ASK_PRODUCT_OWNER
    assert "stale" in decision.reason


def test_gate_checks_every_window_instead_of_using_only_the_freshest() -> None:
    stale = _window(
        status=CodexLimitWindowStatus.AVAILABLE,
        remaining_percent=80,
        reset_at="2026-07-13T00:00:00Z",
        observed_at="2026-07-06T09:20:00Z",
        label="Stale provider window",
    )
    fresh = _window(
        status=CodexLimitWindowStatus.AVAILABLE,
        remaining_percent=80,
        reset_at="2026-07-13T00:00:00Z",
        observed_at="2026-07-06T09:35:00Z",
        label="Fresh auxiliary window",
    )
    record = build_codex_limit_availability_record(
        record_id="availability-mixed-freshness",
        short_window=stale,
        broad_quota=fresh,
        plan_mode=CodexLimitPlanMode.DYNAMIC,
        windows=(stale, fresh),
    )

    decision = decide_codex_limit_gate(
        record,
        now="2026-07-06T09:36:00Z",
        stale_after_seconds=300,
    )

    assert decision.allowed is False
    assert "Stale provider window" in decision.reason
    assert "stale" in decision.reason


def test_gate_blocks_materially_future_observation_but_allows_clock_tolerance() -> None:
    future_record = build_single_pool_codex_limit_availability_record(
        record_id="availability-future",
        pool=_window(
            status=CodexLimitWindowStatus.AVAILABLE,
            remaining_percent=80,
            reset_at="2026-07-13T00:00:00Z",
            observed_at="2026-07-06T09:31:00Z",
        ),
    )

    blocked = decide_codex_limit_gate(
        future_record,
        now="2026-07-06T09:30:00Z",
        future_tolerance_seconds=30,
    )
    tolerated = decide_codex_limit_gate(
        future_record,
        now="2026-07-06T09:30:45Z",
        future_tolerance_seconds=30,
    )

    assert blocked.allowed is False
    assert "future-dated" in blocked.reason
    assert tolerated.allowed is True


def test_gate_blocks_observation_without_timezone() -> None:
    record = build_single_pool_codex_limit_availability_record(
        record_id="availability-no-timezone",
        pool=_window(
            status=CodexLimitWindowStatus.AVAILABLE,
            remaining_percent=80,
            reset_at="2026-07-13T00:00:00Z",
            observed_at="2026-07-06T09:30:00",
        ),
    )

    decision = decide_codex_limit_gate(record, now="2026-07-06T09:30:10Z")

    assert decision.allowed is False
    assert "invalid timestamp" in decision.reason


def test_app_server_observation_source_round_trips() -> None:
    record = build_single_pool_codex_limit_availability_record(
        record_id="availability-app-server",
        pool=_window(
            status=CodexLimitWindowStatus.AVAILABLE,
            remaining_percent=80,
            reset_at="2026-07-13T00:00:00Z",
            source=CodexLimitObservationSource.CODEX_APP_SERVER,
        ),
    )

    restored = codex_limit_availability_record_from_dict(codex_limit_availability_record_to_dict(record))

    assert restored.short_window.observation_source == CodexLimitObservationSource.CODEX_APP_SERVER


def test_invalid_unknown_window_remaining_percent_is_rejected() -> None:
    with pytest.raises(CodexLimitAvailabilityError):
        build_codex_limit_availability_record(
            record_id="availability-20260706T100000Z",
            short_window=_window(
                status=CodexLimitWindowStatus.UNKNOWN,
                remaining_percent=12,
                reset_at="",
                source=CodexLimitObservationSource.UNKNOWN,
            ),
            broad_quota=_window(
                status=CodexLimitWindowStatus.AVAILABLE,
                remaining_percent=80,
                reset_at="2026-07-13T00:00:00Z",
            ),
        )


def _window(
    *,
    status: CodexLimitWindowStatus,
    remaining_percent: int | None,
    reset_at: str,
    source: CodexLimitObservationSource = CodexLimitObservationSource.OPERATOR,
    window_id: str = "",
    label: str = "",
    authoritative: bool = True,
    observed_at: str = "2026-07-06T09:30:00Z",
) -> CodexLimitWindowAvailability:
    return CodexLimitWindowAvailability(
        status=status,
        remaining_percent=remaining_percent,
        reset_at=reset_at,
        observation_source=source,
        observed_at=observed_at,
        window_id=window_id,
        label=label,
        authoritative=authoritative,
    )
