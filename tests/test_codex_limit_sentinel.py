import json
import os
import sys
import threading
from pathlib import Path

import pytest

from agentic_boilerplate.domain import (
    CodexLimitObservationSource,
    CodexLimitPlanMode,
    CodexLimitRecommendedAction,
    CodexLimitWindowStatus,
    decide_codex_limit_gate,
)
from agentic_boilerplate.runtime import (
    CodexAppServerLimitReader,
    CodexLimitSentinelError,
    build_unknown_codex_limit_record,
    refresh_codex_limit_from_payload,
)
from agentic_boilerplate.runtime.codex_limit_sentinel import _split_app_server_command


def _write_protocol_fixture(tmp_path: Path) -> Path:
    script = tmp_path / "protocol_fixture.py"
    script.write_text(
        "\n".join(
            [
                "import json",
                "import os",
                "import sys",
                "import time",
                "mode = sys.argv[1]",
                "if len(sys.argv) > 2:",
                "    with open(sys.argv[2], 'w', encoding='utf-8') as pid_file:",
                "        pid_file.write(str(os.getpid()))",
                "initialized = False",
                "for line in sys.stdin:",
                "    message = json.loads(line)",
                "    method = message.get('method')",
                "    if method == 'initialize':",
                "        if mode == 'initialize_timeout':",
                "            time.sleep(10)",
                "        if mode == 'initialize_error':",
                "            print(json.dumps({'id': message['id'], 'error': {'code': -32000, 'message': 'initialize denied'}}), flush=True)",
                "            continue",
                "        if mode == 'malformed':",
                "            print('not-json', flush=True)",
                "            continue",
                "        if mode == 'oversized':",
                "            print('x' * 1000, flush=True)",
                "            continue",
                "        if mode == 'process_exit':",
                "            raise SystemExit(7)",
                "        print(json.dumps({'id': message['id'], 'result': {}}), flush=True)",
                "    elif method == 'initialized':",
                "        initialized = True",
                "        print(json.dumps({'method': 'account/rateLimits/updated', 'params': {}}), flush=True)",
                "    elif method == 'account/rateLimits/read':",
                "        if not initialized:",
                "            print(json.dumps({'id': message['id'], 'error': {'message': 'handshake order invalid'}}), flush=True)",
                "            continue",
                "        if mode == 'read_timeout':",
                "            time.sleep(10)",
                "        if mode == 'read_error':",
                "            print(json.dumps({'id': message['id'], 'error': {'code': -32601, 'message': 'Method not found token=top-secret'}}), flush=True)",
                "            continue",
                "        if mode == 'diagnostic_error':",
                "            print(('x' * 10000) + ' token=diagnostic-secret', file=sys.stderr, flush=True)",
                "            time.sleep(0.05)",
                "            print(json.dumps({'id': message['id'], 'error': {'message': 'password=rpc-secret'}}), flush=True)",
                "            continue",
                "        result = {'rateLimits': {'primary': {'usedPercent': 10, 'resetsAt': '2026-07-14T10:00:00Z'}}}",
                "        print(json.dumps({'id': message['id'], 'result': result}), flush=True)",
            ]
        ),
        encoding="utf-8",
    )
    return script


def test_refresh_normalizes_app_server_primary_and_secondary_windows() -> None:
    result = refresh_codex_limit_from_payload(
        {
            "rateLimitsByLimitId": {
                "codex": {
                    "primary": {
                        "usedPercent": 12,
                        "resetsAt": "2026-07-14T10:00:00Z",
                        "windowDurationMins": 300,
                    },
                    "secondary": {
                        "usedPercent": 44,
                        "resetsAt": "2026-07-21T10:00:00Z",
                        "windowDurationMins": 10080,
                    },
                    "rateLimitReachedType": None,
                }
            }
        },
        record_id="availability-app-server",
        observed_at="2026-07-14T09:45:00Z",
        account_scope_id="chatgpt-primary",
    )

    record = result.record
    gate = decide_codex_limit_gate(record)

    assert result.supported is True
    assert result.raw_window_count == 2
    assert record.plan_mode == CodexLimitPlanMode.DYNAMIC
    assert record.account_scope_id == "chatgpt-primary"
    assert record.short_window.remaining_percent == 88
    assert record.broad_quota.remaining_percent == 56
    assert record.short_window.observation_source == CodexLimitObservationSource.CODEX_APP_SERVER
    assert gate.allowed is True


def test_refresh_supports_single_visible_agentic_pool_and_cutoff_block() -> None:
    result = refresh_codex_limit_from_payload(
        {
            "rateLimits": {
                "primary": {
                    "usedPercent": 91,
                    "resetsAt": "2026-07-14T10:00:00Z",
                    "label": "Agentic usage pool",
                }
            }
        },
        record_id="availability-single-pool",
        observed_at="2026-07-14T09:45:00Z",
        cutoff_percent=90,
    )

    record = result.record
    gate = decide_codex_limit_gate(record)

    assert record.plan_mode == CodexLimitPlanMode.SINGLE_POOL
    assert record.short_window.status == CodexLimitWindowStatus.LIMITED
    assert record.short_window.remaining_percent == 9
    assert record.recommended_action == CodexLimitRecommendedAction.WAIT
    assert gate.allowed is False
    assert gate.resume_after == "2026-07-14T10:00:00Z"


def test_refresh_selects_verified_legacy_bucket_and_ignores_unrelated_limited_pool() -> None:
    result = refresh_codex_limit_from_payload(
        {
            "rateLimits": {
                "limitId": "codex",
                "primary": {
                    "usedPercent": 20,
                    "resetsAt": 1788343200,
                    "windowDurationMins": 10080,
                },
            },
            "rateLimitsByLimitId": {
                "spark": {
                    "limitId": "spark",
                    "primary": {
                        "usedPercent": 100,
                        "resetsAt": 1788343200,
                        "windowDurationMins": 10080,
                    },
                    "rateLimitReachedType": "hard_limit",
                },
                "codex": {
                    "limitId": "codex",
                    "limitName": "Codex subscription",
                    "primary": {
                        "usedPercent": 20,
                        "resetsAt": 1788343200,
                        "windowDurationMins": 10080,
                    },
                },
            },
        },
        record_id="availability-selected",
        observed_at="2026-09-02T13:00:00Z",
    )

    window = result.record.windows[0]
    assert decide_codex_limit_gate(result.record).allowed is True
    assert result.raw_window_count == 1
    assert window.bucket_id == "codex"
    assert window.window_name == "primary"
    assert window.window_duration_minutes == 10080
    assert window.window_id == "codex_primary"
    assert window.label == "Codex subscription - Primary (10080 min)"


def test_refresh_uses_explicit_bucket_without_map_order_inference() -> None:
    result = refresh_codex_limit_from_payload(
        {
            "rateLimitsByLimitId": {
                "unrelated": {
                    "primary": {"usedPercent": 99, "resetsAt": 1788343200},
                },
                "team-codex": {
                    "limitId": "team-codex",
                    "primary": {"usedPercent": 5, "resetsAt": 1788343200},
                },
            }
        },
        record_id="availability-configured",
        observed_at="2026-09-02T13:00:00Z",
        selected_bucket_id="team-codex",
    )

    assert result.record.windows[0].bucket_id == "team-codex"
    assert decide_codex_limit_gate(result.record).allowed is True


@pytest.mark.parametrize("selected_first", [True, False])
def test_refresh_bucket_order_permutations_keep_the_same_selected_result(
    selected_first: bool,
) -> None:
    selected = {
        "limitId": "codex",
        "primary": {"usedPercent": 12, "resetsAt": 1788343200},
    }
    unrelated = {
        "limitId": "spark",
        "primary": {"usedPercent": 100, "resetsAt": 1788343200},
    }
    buckets = (
        {"codex": selected, "spark": unrelated}
        if selected_first
        else {"spark": unrelated, "codex": selected}
    )

    result = refresh_codex_limit_from_payload(
        {
            "rateLimits": selected,
            "rateLimitsByLimitId": buckets,
        },
        record_id=f"availability-order-{selected_first}",
        observed_at="2026-09-02T13:00:00Z",
    )

    assert result.record.short_window.remaining_percent == 88
    assert result.record.short_window.bucket_id == "codex"
    assert decide_codex_limit_gate(result.record).allowed is True


def test_refresh_blocks_when_explicitly_selected_bucket_is_limited() -> None:
    result = refresh_codex_limit_from_payload(
        {
            "rateLimitsByLimitId": {
                "codex": {
                    "primary": {"usedPercent": 95, "resetsAt": 1788343200},
                },
                "spark": {
                    "primary": {"usedPercent": 1, "resetsAt": 1788343200},
                },
            }
        },
        record_id="availability-selected-limited",
        observed_at="2026-09-02T13:00:00Z",
        selected_bucket_id="codex",
    )

    assert result.record.short_window.status is CodexLimitWindowStatus.LIMITED
    assert decide_codex_limit_gate(result.record).allowed is False


def test_refresh_rejects_absent_configured_bucket() -> None:
    with pytest.raises(CodexLimitSentinelError, match="is unavailable"):
        refresh_codex_limit_from_payload(
            {
                "rateLimitsByLimitId": {
                    "spark": {
                        "primary": {"usedPercent": 1, "resetsAt": 1788343200},
                    }
                }
            },
            record_id="availability-missing-selected",
            observed_at="2026-09-02T13:00:00Z",
            selected_bucket_id="codex",
        )


def test_refresh_rejects_empty_bucket_map() -> None:
    with pytest.raises(CodexLimitSentinelError, match="ambiguous"):
        refresh_codex_limit_from_payload(
            {"rateLimitsByLimitId": {}},
            record_id="availability-empty-map",
            observed_at="2026-09-02T13:00:00Z",
        )


@pytest.mark.parametrize("invalid_map", [None, [], "invalid"])
def test_refresh_rejects_malformed_multi_bucket_container(invalid_map: object) -> None:
    with pytest.raises(CodexLimitSentinelError, match="rateLimitsByLimitId must be an object"):
        refresh_codex_limit_from_payload(
            {
                "rateLimitsByLimitId": invalid_map,
                "rateLimits": {
                    "primary": {"usedPercent": 1, "resetsAt": 1788343200},
                },
            },
            record_id="availability-malformed-map",
            observed_at="2026-09-02T13:00:00Z",
        )


def test_refresh_rejects_ambiguous_multi_bucket_payload_without_identity() -> None:
    with pytest.raises(CodexLimitSentinelError, match="CODEX_LIMIT_BUCKET_ID"):
        refresh_codex_limit_from_payload(
            {
                "rateLimitsByLimitId": {
                    "first": {"primary": {"usedPercent": 5, "resetsAt": 1788343200}},
                    "second": {"primary": {"usedPercent": 10, "resetsAt": 1788343200}},
                }
            },
            record_id="availability-ambiguous",
            observed_at="2026-09-02T13:00:00Z",
        )


@pytest.mark.parametrize(
    "used_percent",
    [-1, 101, float("nan"), float("inf"), True, None],
)
def test_refresh_rejects_invalid_usage_percentage(used_percent: object) -> None:
    with pytest.raises(CodexLimitSentinelError, match="usedPercent"):
        refresh_codex_limit_from_payload(
            {
                "rateLimits": {
                    "primary": {
                        "usedPercent": used_percent,
                        "resetsAt": 1788343200,
                    }
                }
            },
            record_id="availability-invalid-percent",
            observed_at="2026-09-02T13:00:00Z",
        )


@pytest.mark.parametrize(
    "reset_at",
    [None, True, float("inf"), "not-a-timestamp", "2026-09-02T13:00:00"],
)
def test_refresh_rejects_missing_or_invalid_reset_timestamp(reset_at: object) -> None:
    with pytest.raises(CodexLimitSentinelError, match="reset timestamp"):
        refresh_codex_limit_from_payload(
            {
                "rateLimits": {
                    "primary": {
                        "usedPercent": 10,
                        "resetsAt": reset_at,
                    }
                }
            },
            record_id="availability-invalid-reset",
            observed_at="2026-09-02T13:00:00Z",
        )


@pytest.mark.parametrize("provider_field", ["spendControlReached", "rateLimitReached"])
def test_refresh_honors_explicit_provider_blockers(provider_field: str) -> None:
    result = refresh_codex_limit_from_payload(
        {
            provider_field: True,
            "rateLimits": {
                "primary": {
                    "usedPercent": 1,
                    "resetsAt": 1788343200,
                }
            },
        },
        record_id="availability-provider-blocked",
        observed_at="2026-09-02T13:00:00Z",
    )

    assert result.record.short_window.status == CodexLimitWindowStatus.LIMITED
    assert decide_codex_limit_gate(result.record).allowed is False


def test_refresh_honors_rate_limit_reached_type_from_selected_bucket() -> None:
    result = refresh_codex_limit_from_payload(
        {
            "rateLimits": {
                "rateLimitReachedType": "hard_limit",
                "primary": {
                    "usedPercent": 1,
                    "resetsAt": 1788343200,
                },
            }
        },
        record_id="availability-provider-reached",
        observed_at="2026-09-02T13:00:00Z",
    )

    assert result.record.short_window.status == CodexLimitWindowStatus.LIMITED


def test_refresh_does_not_treat_zero_credits_as_subscription_exhaustion() -> None:
    result = refresh_codex_limit_from_payload(
        {
            "credits": {"balance": 0},
            "rateLimitResetCredits": {"availableCount": 0, "credits": []},
            "rateLimits": {
                "credits": {"balance": 0},
                "spendControlReached": False,
                "primary": {
                    "usedPercent": 25,
                    "resetsAt": 1788343200,
                },
            },
        },
        record_id="availability-zero-credits",
        observed_at="2026-09-02T13:00:00Z",
    )

    assert decide_codex_limit_gate(result.record).allowed is True


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("spendControlReached", "false"),
        ("rateLimitReached", 0),
        ("rateLimitReachedType", {"kind": "unknown"}),
    ],
)
def test_refresh_rejects_unsupported_provider_blocking_state(
    field_name: str,
    value: object,
) -> None:
    with pytest.raises(CodexLimitSentinelError, match=field_name):
        refresh_codex_limit_from_payload(
            {
                "rateLimits": {
                    field_name: value,
                    "primary": {
                        "usedPercent": 1,
                        "resetsAt": 1788343200,
                    },
                }
            },
            record_id="availability-invalid-provider-blocker",
            observed_at="2026-09-02T13:00:00Z",
        )


@pytest.mark.parametrize(
    ("used_percent", "expected_status", "expected_remaining", "expected_allowed"),
    [
        (89, CodexLimitWindowStatus.AVAILABLE, 11, True),
        (89.9, CodexLimitWindowStatus.AVAILABLE, 11, True),
        (90, CodexLimitWindowStatus.LIMITED, 10, False),
        (90.1, CodexLimitWindowStatus.LIMITED, 10, False),
    ],
)
def test_refresh_applies_default_ten_percent_remaining_boundary(
    used_percent: float,
    expected_status: CodexLimitWindowStatus,
    expected_remaining: int,
    expected_allowed: bool,
) -> None:
    result = refresh_codex_limit_from_payload(
        {
            "rateLimits": {
                "primary": {
                    "usedPercent": used_percent,
                    "resetsAt": 1788343200,
                }
            }
        },
        record_id=f"availability-threshold-{used_percent}",
        observed_at="2026-09-02T13:00:00Z",
    )

    assert result.record.short_window.status == expected_status
    assert result.record.short_window.remaining_percent == expected_remaining
    assert decide_codex_limit_gate(result.record).allowed is expected_allowed


def test_refresh_rejects_invalid_observation_timestamp() -> None:
    with pytest.raises(CodexLimitSentinelError, match="Observation timestamp"):
        refresh_codex_limit_from_payload(
            {
                "rateLimits": {
                    "primary": {
                        "usedPercent": 1,
                        "resetsAt": 1788343200,
                    }
                }
            },
            record_id="availability-invalid-observation",
            observed_at="not-a-timestamp",
        )


def test_refresh_preserves_and_gates_all_selected_bucket_windows() -> None:
    result = refresh_codex_limit_from_payload(
        {
            "rateLimits": {
                "limitId": "codex",
                "primary": {
                    "usedPercent": 20,
                    "resetsAt": "2026-09-07T10:00:00Z",
                    "windowDurationMins": 60,
                },
                "secondary": {
                    "usedPercent": 30,
                    "resetsAt": "2026-09-08T10:00:00Z",
                    "windowDurationMins": 1440,
                },
                "monthly": {
                    "usedPercent": 95,
                    "resetsAt": "2026-10-01T10:00:00Z",
                    "windowDurationMins": 43200,
                },
            }
        },
        record_id="availability-three-windows",
        observed_at="2026-09-02T13:00:00+00:00",
    )

    record = result.record
    gate = decide_codex_limit_gate(record)
    assert [window.window_name for window in record.windows] == [
        "primary",
        "secondary",
        "monthly",
    ]
    assert [window.authoritative for window in record.windows] == [True, False, False]
    assert record.windows[2].window_duration_minutes == 43200
    assert record.windows[2].observed_at == "2026-09-02T13:00:00+00:00"
    assert record.recommended_action is CodexLimitRecommendedAction.WAIT
    assert gate.allowed is False
    assert gate.resume_after == "2026-10-01T10:00:00Z"


def test_refresh_bounds_and_redacts_provider_metadata() -> None:
    result = refresh_codex_limit_from_payload(
        {
            "rateLimits": {
                "limitId": "codex",
                "limitName": ("x" * 220) + " token=provider-secret",
                "primary": {
                    "usedPercent": 20,
                    "resetsAt": 1788343200,
                },
            }
        },
        record_id="availability-redacted-metadata",
        observed_at="2026-09-02T13:00:00Z",
    )

    label = result.record.short_window.label
    assert len(label) < 240
    assert "provider-secret" not in label
    assert "***REDACTED***" in label


def test_refresh_rejects_malformed_optional_window_and_duration() -> None:
    with pytest.raises(CodexLimitSentinelError, match="invalid secondary"):
        refresh_codex_limit_from_payload(
            {
                "rateLimits": {
                    "primary": {"usedPercent": 10, "resetsAt": 1788343200},
                    "secondary": "invalid",
                }
            },
            record_id="availability-invalid-secondary",
            observed_at="2026-09-02T13:00:00Z",
        )

    with pytest.raises(CodexLimitSentinelError, match="Window duration"):
        refresh_codex_limit_from_payload(
            {
                "rateLimits": {
                    "primary": {
                        "usedPercent": 10,
                        "resetsAt": 1788343200,
                        "windowDurationMins": 1.5,
                    },
                }
            },
            record_id="availability-invalid-duration",
            observed_at="2026-09-02T13:00:00Z",
        )


def test_refresh_rejects_unsupported_payload_without_windows() -> None:
    with pytest.raises(CodexLimitSentinelError):
        refresh_codex_limit_from_payload(
            {"unsupported": True},
            record_id="availability-unsupported",
            observed_at="2026-07-14T09:45:00Z",
        )


def test_unknown_record_preserves_manual_fallback_gate() -> None:
    record = build_unknown_codex_limit_record(
        record_id="availability-unknown",
        observed_at="2026-07-14T09:45:00Z",
        note="Automatic read failed.",
    )

    gate = decide_codex_limit_gate(record)

    assert record.recommended_action == CodexLimitRecommendedAction.ASK_PRODUCT_OWNER
    assert gate.allowed is False
    assert record.short_window.status == CodexLimitWindowStatus.UNKNOWN


def test_app_server_reader_extracts_rate_limit_result_from_json_rpc_stdout(tmp_path: Path) -> None:
    script_root = tmp_path / "app server fixture"
    script_root.mkdir()
    script = script_root / "fake codex app server.py"
    script.write_text(
        "\n".join(
            [
                "import json",
                "import sys",
                "initialized = False",
                "for line in sys.stdin:",
                "    message = json.loads(line)",
                "    method = message.get('method')",
                "    if method == 'initialize':",
                "        print(json.dumps({'id': message['id'], 'result': {}}), flush=True)",
                "    elif method == 'initialized':",
                "        initialized = True",
                "        print(json.dumps({'method': 'account/rateLimits/updated', 'params': {}}), flush=True)",
                "    elif method == 'account/rateLimits/read' and initialized:",
                "        result = {'rateLimits': {'primary': {'usedPercent': 10, 'resetsAt': '2026-07-14T10:00:00Z'}}}",
                "        print(json.dumps({'id': message['id'], 'result': result}), flush=True)",
            ]
        ),
        encoding="utf-8",
    )

    payload = CodexAppServerLimitReader(command=f'"{sys.executable}" "{script}"').read()

    assert payload["rateLimits"]["primary"]["usedPercent"] == 10


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("initialize_error", "initialize denied"),
        ("read_error", "Method not found"),
        ("malformed", "malformed JSON"),
        ("process_exit", "exit=7"),
    ],
)
def test_app_server_reader_fails_closed_for_protocol_errors(
    tmp_path: Path,
    mode: str,
    expected: str,
) -> None:
    script = _write_protocol_fixture(tmp_path)
    reader = CodexAppServerLimitReader(
        command=[sys.executable, str(script), mode],
        timeout_seconds=1,
        initialization_timeout_seconds=0.5,
        read_timeout_seconds=0.5,
    )

    with pytest.raises(CodexLimitSentinelError, match=expected):
        reader.read()


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("initialize_timeout", "initialize timed out"),
        ("read_timeout", "account/rateLimits/read timed out"),
    ],
)
def test_app_server_reader_enforces_phase_timeouts(tmp_path: Path, mode: str, expected: str) -> None:
    script = _write_protocol_fixture(tmp_path)
    reader = CodexAppServerLimitReader(
        command=[sys.executable, str(script), mode],
        timeout_seconds=0.5,
        initialization_timeout_seconds=0.15,
        read_timeout_seconds=0.15,
    )

    with pytest.raises(CodexLimitSentinelError, match=expected):
        reader.read()


def test_app_server_reader_honors_cancellation_and_reaps_child(tmp_path: Path) -> None:
    script = _write_protocol_fixture(tmp_path)
    pid_path = tmp_path / "child.pid"
    cancel_event = threading.Event()
    cancel_timer = threading.Timer(0.05, cancel_event.set)
    reader = CodexAppServerLimitReader(
        command=[sys.executable, str(script), "initialize_timeout", str(pid_path)],
        timeout_seconds=2,
    )

    cancel_timer.start()
    try:
        with pytest.raises(CodexLimitSentinelError, match="cancelled"):
            reader.read(cancel_event=cancel_event)
    finally:
        cancel_timer.join()

    if pid_path.exists() and os.name != "nt":
        with pytest.raises(ProcessLookupError):
            os.kill(int(pid_path.read_text(encoding="utf-8")), 0)


def test_app_server_reader_bounds_and_redacts_protocol_diagnostics(tmp_path: Path) -> None:
    script = _write_protocol_fixture(tmp_path)
    reader = CodexAppServerLimitReader(
        command=[sys.executable, str(script), "diagnostic_error"],
        timeout_seconds=1,
        diagnostic_limit_chars=256,
    )

    with pytest.raises(CodexLimitSentinelError) as captured:
        reader.read()

    message = str(captured.value)
    assert "***REDACTED***" in message
    assert "diagnostic-secret" not in message
    assert "rpc-secret" not in message
    assert len(message) < 700


def test_app_server_reader_accepts_sequence_argv_without_shell_evaluation(tmp_path: Path) -> None:
    script = _write_protocol_fixture(tmp_path)

    payload = CodexAppServerLimitReader(command=[sys.executable, str(script), "success"]).read()

    assert payload["rateLimits"]["primary"]["usedPercent"] == 10


def test_app_server_command_parser_preserves_quoted_windows_executable_path() -> None:
    command = '"C:\\Program Files\\Codex\\codex.exe" app-server'

    assert _split_app_server_command(command, windows_style=True) == [
        "C:\\Program Files\\Codex\\codex.exe",
        "app-server",
    ]


def test_app_server_reader_rejects_oversized_stdout_before_json_parsing(tmp_path: Path) -> None:
    script = _write_protocol_fixture(tmp_path)
    reader = CodexAppServerLimitReader(
        command=[sys.executable, str(script), "oversized"],
        timeout_seconds=1,
        protocol_line_limit_chars=64,
    )

    with pytest.raises(CodexLimitSentinelError, match="oversized initialize response"):
        reader.read()


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf")])
def test_app_server_reader_rejects_non_positive_or_non_finite_timeouts(timeout: float) -> None:
    with pytest.raises(CodexLimitSentinelError, match="timeout must be positive"):
        CodexAppServerLimitReader(timeout_seconds=timeout)


def test_app_server_sequence_parser_preserves_explicit_empty_arguments() -> None:
    assert _split_app_server_command(["codex", "app-server", ""]) == ["codex", "app-server", ""]
