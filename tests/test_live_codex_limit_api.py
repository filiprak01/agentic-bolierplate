import json
from pathlib import Path
from typing import Any

from agentic_boilerplate.api.live_local import LiveCodexLocalAPI
from agentic_boilerplate.runtime import CodexLimitSentinelError, CodexLiveStatusPayload
from agentic_boilerplate.storage.codex_limit_availability import FileCodexLimitAvailabilityStore


class FakeLiveStatusReader:
    def __init__(self, *, payload: CodexLiveStatusPayload | None = None, error: Exception | None = None) -> None:
        self.payload = payload
        self.error = error
        self.calls = 0

    def read(self) -> CodexLiveStatusPayload:
        self.calls += 1
        if self.error is not None:
            raise self.error
        assert self.payload is not None
        return self.payload


def test_live_refresh_persists_chatgpt_subscription_quota_snapshot(tmp_path: Path) -> None:
    reader = FakeLiveStatusReader(payload=_live_payload(used_percent=18))
    api = _api(tmp_path, reader)

    response = api.handle_request("POST", "/codex-limits/refresh")

    assert response.status_code == 201
    assert reader.calls == 1
    assert response.body["live_refresh"]["status"] == "refreshed"
    assert response.body["auth"]["subscription_auth"] is True
    assert response.body["provider"]["plan_type"] == "prolite"
    assert response.body["provider"]["reset_credit_count"] == 2
    assert response.body["canStartWork"] is True
    assert response.body["gate"]["allowed"] is True

    window = response.body["windows"][0]
    assert window["bucket_id"] == "codex"
    assert window["window_name"] == "primary"
    assert window["windowDurationMins"] == 10080
    assert window["usedPercent"] == 18
    assert window["remainingPercent"] == 82
    assert window["resetsAt"] == "2026-09-19T12:00:00Z"

    records = FileCodexLimitAvailabilityStore(tmp_path / "codex-limits").list_records()
    assert len(records) == 1
    assert records[0].windows[0].observation_source.value == "codex_app_server"


def test_live_refresh_rejects_api_key_auth_and_redacts_response(tmp_path: Path) -> None:
    reader = FakeLiveStatusReader(
        payload=_live_payload(
            account={"authMode": "api_key", "apiKey": "sk-secret-value", "status": "authenticated"},
            used_percent=10,
        )
    )
    api = _api(tmp_path, reader)

    response = api.handle_request("POST", "/codex-limits/refresh")

    assert response.status_code == 403
    assert response.body["live_refresh"]["status"] == "auth_rejected"
    assert response.body["gate"]["allowed"] is False
    serialized = json.dumps(response.body)
    assert "sk-secret-value" not in serialized
    assert "apiKey" not in serialized


def test_live_refresh_failure_persists_safe_unknown_record(tmp_path: Path) -> None:
    reader = FakeLiveStatusReader(error=CodexLimitSentinelError("token=super-secret failure"))
    api = _api(tmp_path, reader)

    response = api.handle_request("POST", "/codex-limits/refresh")

    assert response.status_code == 503
    assert response.body["live_refresh"]["status"] == "unavailable"
    assert response.body["gate"]["allowed"] is False
    serialized = json.dumps(response.body)
    assert "super-secret" not in serialized
    records = FileCodexLimitAvailabilityStore(tmp_path / "codex-limits").list_records()
    assert len(records) == 1
    assert "super-secret" not in records[0].note
    assert records[0].windows[0].status.value == "unknown"


def test_cached_get_keeps_live_serialization_aliases(tmp_path: Path) -> None:
    api = _api(tmp_path, FakeLiveStatusReader(payload=_live_payload(used_percent=31)))
    refresh = api.handle_request("POST", "/codex-limits/refresh")
    assert refresh.status_code == 201

    cached = api.handle_request("GET", "/codex-limits")

    assert cached.status_code == 200
    assert cached.body["live_refresh"]["status"] == "cached_latest"
    assert cached.body["canStartWork"] is True
    assert cached.body["windows"][0]["usedPercent"] == 31
    assert cached.body["windows"][0]["remainingPercent"] == 69
    assert cached.body["windows"][0]["windowDurationMins"] == 10080


def _api(tmp_path: Path, reader: FakeLiveStatusReader) -> LiveCodexLocalAPI:
    return LiveCodexLocalAPI(
        inbox_root=tmp_path / "po-inbox",
        data_root=tmp_path,
        codex_live_status_reader=reader,
        limit_account_scope_id="default",
        limit_bucket_id="codex",
        codex_limit_cutoff_percent=90,
    )


def _live_payload(
    *,
    account: dict[str, Any] | None = None,
    used_percent: int,
) -> CodexLiveStatusPayload:
    bucket = {
        "limitId": "codex",
        "limitName": "Codex subscription",
        "planType": "prolite",
        "primary": {
            "usedPercent": used_percent,
            "resetsAt": "2026-09-19T12:00:00Z",
            "windowDurationMins": 10080,
        },
        "rateLimitReachedType": None,
        "spendControlReached": False,
        "credits": {"hasCredits": False, "unlimited": False, "balance": "0"},
    }
    return CodexLiveStatusPayload(
        account=account
        or {
            "authMode": "chatgpt",
            "accountType": "subscription",
            "planType": "prolite",
            "status": "authenticated",
        },
        rate_limits={
            "rateLimits": bucket,
            "rateLimitsByLimitId": {"codex": bucket},
            "rateLimitResetCredits": {"availableCount": 2},
        },
    )
