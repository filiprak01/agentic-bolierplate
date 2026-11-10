import json
import sys
from pathlib import Path

from agentic_boilerplate.cli import main
from agentic_boilerplate.storage import FileCodexLimitAvailabilityStore


def test_cli_records_and_reads_latest_codex_limit_gate(tmp_path: Path, capsys) -> None:
    root = tmp_path / "codex-limits"
    missing_env = tmp_path / "missing.env"

    result = main(
        [
            "--env-file",
            str(missing_env),
            "codex-limits",
            "record",
            "--id",
            "availability-20260707T100000Z",
            "--short-status",
            "available",
            "--short-remaining",
            "5",
            "--short-reset-at",
            "2026-07-07T15:00:00Z",
            "--broad-status",
            "available",
            "--broad-remaining",
            "80",
            "--broad-reset-at",
            "2026-07-14T10:00:00Z",
            "--observed-at",
            "2026-07-07T10:00:00Z",
            "--codex-limits-root",
            str(root),
        ]
    )

    assert result == 0
    assert "recorded\tavailability-20260707T100000Z\twait\tFalse\t2026-07-07T15:00:00Z" in capsys.readouterr().out

    result = main(
        [
            "--env-file",
            str(missing_env),
            "codex-limits",
            "latest",
            "--codex-limits-root",
            str(root),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert result == 0
    assert payload["record"]["id"] == "availability-20260707T100000Z"
    assert payload["record"]["recommended_action"] == "wait"
    assert payload["gate"]["allowed"] is False
    assert payload["gate"]["resume_after"] == "2026-07-07T15:00:00Z"


def test_cli_latest_blocks_when_no_codex_limit_record_exists(tmp_path: Path, capsys) -> None:
    result = main(
        [
            "--env-file",
            str(tmp_path / "missing.env"),
            "codex-limits",
            "latest",
            "--codex-limits-root",
            str(tmp_path / "codex-limits"),
        ]
    )

    output = capsys.readouterr().out

    assert result == 0
    assert "ask_product_owner" in output
    assert "False" in output
    assert "No Codex limit availability record is available." in output


def test_cli_latest_uses_scoped_observation_order_not_record_id(tmp_path: Path, capsys) -> None:
    root = tmp_path / "codex-limits"
    missing_env = tmp_path / "missing.env"

    for record_id, observed_at, remaining in (
        ("z-older", "2026-07-07T09:00:00Z", "90"),
        ("a-newer", "2026-07-07T10:00:00Z", "5"),
    ):
        assert (
            main(
                [
                    "--env-file",
                    str(missing_env),
                    "codex-limits",
                    "record",
                    "--id",
                    record_id,
                    "--plan-mode",
                    "single_pool",
                    "--short-status",
                    "available",
                    "--short-remaining",
                    remaining,
                    "--short-reset-at",
                    "2026-07-07T15:00:00Z",
                    "--observed-at",
                    observed_at,
                    "--account-scope-id",
                    "chatgpt-primary",
                    "--bucket-id",
                    "codex",
                    "--codex-limits-root",
                    str(root),
                ]
            )
            == 0
        )
        capsys.readouterr()

    result = main(
        [
            "--env-file",
            str(missing_env),
            "codex-limits",
            "latest",
            "--account-scope-id",
            "chatgpt-primary",
            "--bucket-id",
            "codex",
            "--codex-limits-root",
            str(root),
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert result == 0
    assert payload["record"]["id"] == "a-newer"
    assert payload["record"]["account_scope_id"] == "chatgpt-primary"
    assert payload["record"]["windows"][0]["bucket_id"] == "codex"
    assert payload["gate"]["allowed"] is False


def test_cli_status_prints_readable_operator_capacity(tmp_path: Path, capsys) -> None:
    root = tmp_path / "codex-limits"
    missing_env = tmp_path / "missing.env"

    assert (
        main(
            [
                "--env-file",
                str(missing_env),
                "codex-limits",
                "record",
                "--id",
                "availability-20260711T080000Z",
                "--five-hour-status",
                "available",
                "--five-hour-remaining",
                "95",
                "--five-hour-reset-at",
                "2026-07-11T13:00:00Z",
                "--weekly-status",
                "available",
                "--weekly-remaining",
                "99",
                "--weekly-reset-at",
                "2026-07-18T08:00:00Z",
                "--codex-limits-root",
                str(root),
            ]
        )
        == 0
    )
    capsys.readouterr()

    result = main(
        [
            "--env-file",
            str(missing_env),
            "codex-limits",
            "status",
            "--codex-limits-root",
            str(root),
        ]
    )

    output = capsys.readouterr().out

    assert result == 0
    assert "Codex limit capacity" in output
    assert "Record: availability-20260711T080000Z" in output
    assert "Action: resume" in output
    assert "Allowed: yes" in output
    assert "Plan mode: dual_window" in output
    assert "Primary window: status=available, remaining=95%" in output
    assert "Secondary quota: status=available, remaining=99%" in output
    assert "Automatic GUI scraping: not supported" in output


def test_cli_status_for_missing_record_explains_operator_action(tmp_path: Path, capsys) -> None:
    result = main(
        [
            "--env-file",
            str(tmp_path / "missing.env"),
            "codex-limits",
            "status",
            "--codex-limits-root",
            str(tmp_path / "codex-limits"),
        ]
    )

    output = capsys.readouterr().out

    assert result == 0
    assert "Record: missing" in output
    assert "Action: ask_product_owner" in output
    assert "Allowed: no" in output
    assert "record current Codex limit windows" in output
    assert "Automatic GUI scraping: not supported" in output


def test_cli_records_single_pool_limit_without_broad_quota(tmp_path: Path, capsys) -> None:
    root = tmp_path / "codex-limits"
    missing_env = tmp_path / "missing.env"

    result = main(
        [
            "--env-file",
            str(missing_env),
            "codex-limits",
            "record",
            "--id",
            "availability-single-pool",
            "--plan-mode",
            "single_pool",
            "--short-status",
            "available",
            "--short-remaining",
            "88",
            "--short-reset-at",
            "2026-07-14T10:00:00Z",
            "--short-window-id",
            "agentic_pool",
            "--short-label",
            "Agentic usage pool",
            "--source",
            "codex_cli",
            "--observed-at",
            "2026-07-14T09:45:00Z",
            "--codex-limits-root",
            str(root),
        ]
    )

    assert result == 0
    assert "recorded\tavailability-single-pool\tresume\tTrue" in capsys.readouterr().out

    result = main(
        [
            "--env-file",
            str(missing_env),
            "codex-limits",
            "latest",
            "--codex-limits-root",
            str(root),
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert result == 0
    assert payload["record"]["plan_mode"] == "single_pool"
    assert payload["record"]["windows"][0]["label"] == "Agentic usage pool"
    assert payload["record"]["broad_quota"]["window_id"] == "agentic_pool"
    assert payload["gate"]["allowed"] is True

    result = main(
        [
            "--env-file",
            str(missing_env),
            "codex-limits",
            "status",
            "--codex-limits-root",
            str(root),
        ]
    )
    output = capsys.readouterr().out

    assert result == 0
    assert "Plan mode: single_pool" in output
    assert "Agentic usage pool: status=available, remaining=88%" in output


def test_cli_record_accepts_codex_app_server_observation_source(tmp_path: Path, capsys) -> None:
    root = tmp_path / "codex-limits"
    missing_env = tmp_path / "missing.env"

    result = main(
        [
            "--env-file",
            str(missing_env),
            "codex-limits",
            "record",
            "--id",
            "availability-app-server",
            "--plan-mode",
            "single_pool",
            "--short-status",
            "available",
            "--short-remaining",
            "95",
            "--short-reset-at",
            "2026-07-14T10:00:00Z",
            "--source",
            "codex_app_server",
            "--observed-at",
            "2026-07-14T09:45:00Z",
            "--bucket-id",
            "codex",
            "--codex-limits-root",
            str(root),
        ]
    )

    assert result == 0
    assert "recorded	availability-app-server" in capsys.readouterr().out
    record = json.loads(
        (root / "limit-availability" / "availability-app-server.json").read_text(encoding="utf-8")
    )
    assert record["short_window"]["observation_source"] == "codex_app_server"
    assert record["short_window"]["bucket_id"] == "codex"


def test_cli_dual_window_requires_broad_status(tmp_path: Path, capsys) -> None:
    result = main(
        [
            "--env-file",
            str(tmp_path / "missing.env"),
            "codex-limits",
            "record",
            "--id",
            "availability-invalid",
            "--short-status",
            "available",
            "--short-remaining",
            "88",
            "--short-reset-at",
            "2026-07-14T10:00:00Z",
            "--codex-limits-root",
            str(tmp_path / "codex-limits"),
        ]
    )

    captured = capsys.readouterr()

    assert result == 1
    assert "--broad-status is required" in captured.err


def test_cli_refresh_records_app_server_payload(tmp_path: Path, capsys) -> None:
    root = tmp_path / "codex-limits"
    payload = tmp_path / "rate-limits.json"
    payload.write_text(
        json.dumps(
            {
                "rateLimits": {
                    "primary": {
                        "usedPercent": 20,
                        "resetsAt": "2026-07-14T10:00:00Z",
                        "label": "Agentic usage pool",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    result = main(
        [
            "--env-file",
            str(tmp_path / "missing.env"),
            "codex-limits",
            "refresh",
            "--id",
            "availability-refresh",
            "--payload-json",
            str(payload),
            "--observed-at",
            "2026-07-14T09:45:00Z",
            "--codex-limits-root",
            str(root),
        ]
    )

    assert result == 0
    assert "refreshed\tavailability-refresh\tresume\tTrue" in capsys.readouterr().out
    record = json.loads(
        (root / "limit-availability" / "availability-refresh.json").read_text(encoding="utf-8")
    )
    assert record["short_window"]["observation_source"] == "offline_fixture"
    assert record["short_window"]["bucket_id"] == "codex"

    result = main(
        [
            "--env-file",
            str(tmp_path / "missing.env"),
            "codex-limits",
            "status",
            "--codex-limits-root",
            str(root),
        ]
    )
    output = capsys.readouterr().out

    assert result == 0
    assert "Plan mode: single_pool" in output
    assert "Agentic usage pool: status=available, remaining=80%" in output


def test_cli_refresh_writes_blocked_unknown_record_when_payload_is_unsupported(tmp_path: Path, capsys) -> None:
    root = tmp_path / "codex-limits"
    payload = tmp_path / "unsupported.json"
    payload.write_text(json.dumps({"unsupported": True}), encoding="utf-8")

    result = main(
        [
            "--env-file",
            str(tmp_path / "missing.env"),
            "codex-limits",
            "refresh",
            "--id",
            "availability-unsupported",
            "--payload-json",
            str(payload),
            "--observed-at",
            "2026-07-14T09:45:00Z",
            "--codex-limits-root",
            str(root),
        ]
    )

    assert result == 1
    assert "refresh_failed\tavailability-unsupported\task_product_owner\tFalse" in capsys.readouterr().out
    record = json.loads(
        (root / "limit-availability" / "availability-unsupported.json").read_text(
            encoding="utf-8"
        )
    )
    assert record["short_window"]["observation_source"] == "offline_fixture"
    assert record["short_window"]["bucket_id"] == ""


def test_cli_failed_refresh_uses_sole_provider_bucket_and_blocks_independent_read(
    tmp_path: Path,
    capsys,
) -> None:
    root = tmp_path / "codex-limits"
    payload = tmp_path / "unsupported.json"
    payload.write_text(json.dumps({"unsupported": True}), encoding="utf-8")
    missing_env = tmp_path / "missing.env"

    assert (
        main(
            [
                "--env-file",
                str(missing_env),
                "codex-limits",
                "record",
                "--id",
                "provider-available",
                "--plan-mode",
                "single_pool",
                "--short-status",
                "available",
                "--short-remaining",
                "90",
                "--short-reset-at",
                "2026-09-03T10:00:00Z",
                "--source",
                "codex_cli",
                "--observed-at",
                "2026-09-02T12:00:00Z",
                "--bucket-id",
                "codex",
                "--codex-limits-root",
                str(root),
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert (
        main(
            [
                "--env-file",
                str(missing_env),
                "codex-limits",
                "refresh",
                "--id",
                "provider-refresh-failed",
                "--payload-json",
                str(payload),
                "--observed-at",
                "2026-09-02T12:01:00Z",
                "--codex-limits-root",
                str(root),
            ]
        )
        == 1
    )
    capsys.readouterr()

    failed = FileCodexLimitAvailabilityStore(root).read_record("provider-refresh-failed")
    assert failed.short_window.bucket_id == "codex"
    assert failed.recommended_action.value == "ask_product_owner"

    assert (
        main(
            [
                "--env-file",
                str(missing_env),
                "codex-limits",
                "latest",
                "--codex-limits-root",
                str(root),
            ]
        )
        == 0
    )
    latest_output = capsys.readouterr().out
    assert "provider-refresh-failed" in latest_output
    assert "ask_product_owner" in latest_output
    assert "False" in latest_output


def test_cli_failed_refresh_does_not_choose_between_ambiguous_provider_buckets(
    tmp_path: Path,
    capsys,
) -> None:
    root = tmp_path / "codex-limits"
    payload = tmp_path / "unsupported.json"
    payload.write_text(json.dumps({"unsupported": True}), encoding="utf-8")
    missing_env = tmp_path / "missing.env"

    for record_id, bucket_id in (
        ("provider-codex", "codex"),
        ("provider-credits", "credits"),
    ):
        assert (
            main(
                [
                    "--env-file",
                    str(missing_env),
                    "codex-limits",
                    "record",
                    "--id",
                    record_id,
                    "--plan-mode",
                    "single_pool",
                    "--short-status",
                    "available",
                    "--short-remaining",
                    "90",
                    "--short-reset-at",
                    "2026-09-03T10:00:00Z",
                    "--source",
                    "codex_cli",
                    "--observed-at",
                    "2026-09-02T12:00:00Z",
                    "--bucket-id",
                    bucket_id,
                    "--codex-limits-root",
                    str(root),
                ]
            )
            == 0
        )
        capsys.readouterr()

    result = main(
        [
            "--env-file",
            str(missing_env),
            "codex-limits",
            "refresh",
            "--id",
            "ambiguous-refresh-failure",
            "--payload-json",
            str(payload),
            "--observed-at",
            "2026-09-02T12:01:00Z",
            "--codex-limits-root",
            str(root),
        ]
    )
    captured = capsys.readouterr()

    assert result == 1
    assert "Codex quota bucket is ambiguous" in captured.err
    assert {record.id for record in FileCodexLimitAvailabilityStore(root).list_records()} == {
        "provider-codex",
        "provider-credits",
    }


def test_cli_refresh_redacts_bucket_errors_in_durable_unknown_record(tmp_path: Path, capsys) -> None:
    root = tmp_path / "codex-limits"
    payload = tmp_path / "missing-bucket.json"
    payload.write_text(
        json.dumps(
            {
                "rateLimitsByLimitId": {
                    "token=must-not-persist": {
                        "primary": {"usedPercent": 1, "resetsAt": 1788343200}
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    result = main(
        [
            "--env-file",
            str(tmp_path / "missing.env"),
            "codex-limits",
            "refresh",
            "--id",
            "availability-redacted-bucket-error",
            "--payload-json",
            str(payload),
            "--bucket-id",
            "codex",
            "--observed-at",
            "2026-09-02T13:00:00Z",
            "--codex-limits-root",
            str(root),
        ]
    )

    record = json.loads(
        (root / "limit-availability" / "availability-redacted-bucket-error.json").read_text(
            encoding="utf-8"
        )
    )
    assert result == 1
    assert "must-not-persist" not in record["note"]
    assert "***REDACTED***" in record["note"]
    assert record["short_window"]["observation_source"] == "offline_fixture"
    assert record["short_window"]["bucket_id"] == "codex"


def test_cli_refresh_honors_explicit_zero_cutoff(tmp_path: Path, capsys) -> None:
    root = tmp_path / "codex-limits"
    payload = tmp_path / "rate-limits.json"
    payload.write_text(
        json.dumps(
            {
                "rateLimits": {
                    "primary": {"usedPercent": 0, "resetsAt": 1788343200}
                }
            }
        ),
        encoding="utf-8",
    )

    result = main(
        [
            "--env-file",
            str(tmp_path / "missing.env"),
            "codex-limits",
            "refresh",
            "--payload-json",
            str(payload),
            "--cutoff-percent",
            "0",
            "--observed-at",
            "2026-09-02T13:00:00Z",
            "--codex-limits-root",
            str(root),
        ]
    )

    assert result == 2
    assert "\twait\tFalse\t" in capsys.readouterr().out


def test_cli_refresh_generates_unique_ids_for_same_second_observations(tmp_path: Path, capsys) -> None:
    root = tmp_path / "codex-limits"
    payload = tmp_path / "rate-limits.json"
    payload.write_text(
        json.dumps(
            {
                "rateLimits": {
                    "primary": {
                        "usedPercent": 20,
                        "resetsAt": "2026-09-03T10:00:00Z",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    command = [
        "--env-file",
        str(tmp_path / "missing.env"),
        "codex-limits",
        "refresh",
        "--payload-json",
        str(payload),
        "--observed-at",
        "2026-09-02T13:00:00Z",
        "--codex-limits-root",
        str(root),
    ]

    selected_ids = []
    for _ in range(2):
        assert main(command) == 0
        output = capsys.readouterr().out.strip().split("\t")
        current_ids = {
            json.loads(path.read_text(encoding="utf-8"))["id"]
            for path in (root / "limit-availability").glob("*.json")
        }
        assert output[0] == "refreshed"
        assert output[1] in current_ids
        assert output[2] in {"proceed", "resume"}
        assert output[3] == "True"
        selected_ids.append(output[1])

    record_paths = list((root / "limit-availability").glob("*.json"))
    persisted_ids = {
        json.loads(path.read_text(encoding="utf-8"))["id"] for path in record_paths
    }

    assert len(record_paths) == 2
    assert len(persisted_ids) == 2
    assert set(selected_ids) <= persisted_ids


def test_cli_refresh_rechecks_newer_or_equal_restrictive_observation(
    tmp_path: Path,
    capsys,
) -> None:
    payload = tmp_path / "available-rate-limits.json"
    payload.write_text(
        json.dumps(
            {
                "rateLimits": {
                    "primary": {
                        "usedPercent": 20,
                        "resetsAt": "2099-09-03T10:00:00Z",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    for case, provider_observed_at in (
        ("equal", "2026-09-02T13:00:00Z"),
        ("newer", "2026-09-02T13:01:00Z"),
    ):
        root = tmp_path / case / "codex-limits"
        provider_id = f"provider-block-{case}"
        assert (
            main(
                [
                    "--env-file",
                    str(tmp_path / "missing.env"),
                    "codex-limits",
                    "record",
                    "--id",
                    provider_id,
                    "--plan-mode",
                    "single_pool",
                    "--short-status",
                    "limited",
                    "--short-remaining",
                    "0",
                    "--short-reset-at",
                    "2099-09-03T10:00:00Z",
                    "--source",
                    "codex_cli",
                    "--observed-at",
                    provider_observed_at,
                    "--account-scope-id",
                    "account-a",
                    "--bucket-id",
                    "codex",
                    "--codex-limits-root",
                    str(root),
                ]
            )
            == 0
        )
        capsys.readouterr()

        result = main(
            [
                "--env-file",
                str(tmp_path / "missing.env"),
                "codex-limits",
                "refresh",
                "--id",
                f"offline-available-{case}",
                "--payload-json",
                str(payload),
                "--observed-at",
                "2026-09-02T13:00:00Z",
                "--account-scope-id",
                "account-a",
                "--bucket-id",
                "codex",
                "--codex-limits-root",
                str(root),
            ]
        )
        fields = capsys.readouterr().out.strip().split("\t")

        assert result == 2
        assert fields[0] == "refreshed"
        assert fields[1] == provider_id
        assert fields[2] == "wait"
        assert fields[3] == "False"
        assert fields[-1].endswith(f"/{provider_id}.json")


def test_cli_refresh_fails_closed_for_stale_or_future_offline_observation(
    tmp_path: Path,
    capsys,
) -> None:
    payload = tmp_path / "available-rate-limits.json"
    payload.write_text(
        json.dumps(
            {
                "rateLimits": {
                    "primary": {
                        "usedPercent": 20,
                        "resetsAt": "2101-01-01T00:00:00Z",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    env_file = tmp_path / "limits.env"
    env_file.write_text(
        "CODEX_LIMIT_STALE_AFTER_SECONDS=300\n"
        "CODEX_LIMIT_FUTURE_TOLERANCE_SECONDS=30\n",
        encoding="utf-8",
    )

    for case, observed_at in (
        ("stale", "2000-01-01T00:00:00Z"),
        ("future", "2100-01-01T00:00:00Z"),
    ):
        root = tmp_path / case / "codex-limits"
        record_id = f"offline-{case}"
        result = main(
            [
                "--env-file",
                str(env_file),
                "codex-limits",
                "refresh",
                "--id",
                record_id,
                "--payload-json",
                str(payload),
                "--observed-at",
                observed_at,
                "--codex-limits-root",
                str(root),
            ]
        )
        fields = capsys.readouterr().out.strip().split("\t")

        assert result == 2
        assert fields[0] == "refreshed"
        assert fields[1] == record_id
        assert fields[2] == "ask_product_owner"
        assert fields[3] == "False"


def test_cli_refresh_reader_error_writes_sanitized_blocked_unknown_record(tmp_path: Path, capsys) -> None:
    root = tmp_path / "codex-limits"
    script = tmp_path / "failing_app_server.py"
    script.write_text(
        "\n".join(
            [
                "import json",
                "import sys",
                "initialized = False",
                "for line in sys.stdin:",
                "    message = json.loads(line)",
                "    if message.get('method') == 'initialize':",
                "        print(json.dumps({'id': message['id'], 'result': {}}), flush=True)",
                "    elif message.get('method') == 'initialized':",
                "        initialized = True",
                "    elif message.get('method') == 'account/rateLimits/read' and initialized:",
                "        print(json.dumps({'id': message['id'], 'error': {'message': 'token=must-not-persist'}}), flush=True)",
            ]
        ),
        encoding="utf-8",
    )

    result = main(
        [
            "--env-file",
            str(tmp_path / "missing.env"),
            "codex-limits",
            "refresh",
            "--id",
            "availability-reader-error",
            "--app-server-command",
            f'"{sys.executable}" "{script}"',
            "--timeout-seconds",
            "1",
            "--observed-at",
            "2026-07-14T09:45:00Z",
            "--codex-limits-root",
            str(root),
        ]
    )

    record = json.loads(
        (root / "limit-availability" / "availability-reader-error.json").read_text(encoding="utf-8")
    )
    assert result == 1
    assert "refresh_failed\tavailability-reader-error\task_product_owner\tFalse" in capsys.readouterr().out
    assert record["recommended_action"] == "ask_product_owner"
    assert record["windows"][0]["status"] == "unknown"
    assert "must-not-persist" not in record["note"]
    assert "***REDACTED***" in record["note"]


def test_cli_latest_blocks_stale_record_when_threshold_is_supplied(tmp_path: Path, capsys) -> None:
    root = tmp_path / "codex-limits"
    assert (
        main(
            [
                "--env-file",
                str(tmp_path / "missing.env"),
                "codex-limits",
                "record",
                "--id",
                "availability-stale",
                "--short-status",
                "available",
                "--short-remaining",
                "95",
                "--short-reset-at",
                "2026-07-14T10:00:00Z",
                "--broad-status",
                "available",
                "--broad-remaining",
                "95",
                "--broad-reset-at",
                "2026-07-21T10:00:00Z",
                "--observed-at",
                "2026-07-14T09:45:00Z",
                "--codex-limits-root",
                str(root),
            ]
        )
        == 0
    )
    capsys.readouterr()

    result = main(
        [
            "--env-file",
            str(tmp_path / "missing.env"),
            "codex-limits",
            "latest",
            "--codex-limits-root",
            str(root),
            "--stale-after-seconds",
            "300",
            "--now",
            "2026-07-14T09:51:00Z",
        ]
    )

    output = capsys.readouterr().out

    assert result == 0
    assert "ask_product_owner" in output
    assert "False" in output
    assert "stale" in output
