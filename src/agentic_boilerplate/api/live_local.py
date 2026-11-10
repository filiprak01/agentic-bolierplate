"""Live Codex quota refresh wrapper for the local operator API."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

from agentic_boilerplate.api.local import (
    APIResponse,
    LocalAPI,
    _codex_limits_body_from_record,
    _redact_secret_text,
    _redact_values,
    _safe_browser_path,
    _utc_now,
    _write_idempotent_operator_limit_record,
    make_request_handler,
)
from agentic_boilerplate.domain import CodexLimitAvailabilityRecord, CodexLimitObservationSource
from agentic_boilerplate.runtime import (
    CodexAppServerLiveStatusReader,
    CodexLimitSentinelError,
    build_unknown_codex_limit_record,
    codex_live_auth_summary_to_dict,
    refresh_codex_limit_from_payload,
    summarize_codex_subscription_auth,
)
from agentic_boilerplate.storage.codex_limit_availability import FileCodexLimitAvailabilityStore


class LiveCodexLocalAPI(LocalAPI):
    """Local operator API with host-owned live Codex quota refresh."""

    def __init__(
        self,
        *,
        inbox_root: Path | str,
        data_root: Path | str | None = None,
        codex_live_status_reader: Any | None = None,
        codex_live_app_server_command: str = "codex app-server",
        codex_live_timeout_seconds: float = 15,
        codex_limit_cutoff_percent: int = 90,
        limit_account_scope_id: str = "",
        limit_bucket_id: str = "",
        limit_stale_after_seconds: int | None = None,
        limit_future_tolerance_seconds: int = 30,
    ) -> None:
        super().__init__(
            inbox_root=inbox_root,
            data_root=data_root,
            limit_account_scope_id=limit_account_scope_id,
            limit_bucket_id=limit_bucket_id,
            limit_stale_after_seconds=limit_stale_after_seconds,
            limit_future_tolerance_seconds=limit_future_tolerance_seconds,
        )
        self.codex_live_status_reader = codex_live_status_reader
        self.codex_live_app_server_command = codex_live_app_server_command
        self.codex_live_timeout_seconds = codex_live_timeout_seconds
        self.codex_limit_cutoff_percent = codex_limit_cutoff_percent

    def _dispatch(
        self,
        method: str,
        path_parts: list[str],
        query: Mapping[str, str],
        body: Mapping[str, Any],
    ) -> APIResponse:
        if method == "POST" and path_parts == ["codex-limits", "refresh"]:
            return _refresh_live_codex_limits_response(
                data_root=self.data_root,
                reader=self.codex_live_status_reader,
                app_server_command=self.codex_live_app_server_command,
                timeout_seconds=self.codex_live_timeout_seconds,
                cutoff_percent=self.codex_limit_cutoff_percent,
                account_scope_id=self.limit_account_scope_id,
                bucket_id=self.limit_bucket_id,
                stale_after_seconds=self.limit_stale_after_seconds,
                future_tolerance_seconds=self.limit_future_tolerance_seconds,
            )

        response = super()._dispatch(method, path_parts, query, body)
        if method == "GET" and path_parts == ["codex-limits"] and response.status_code == 200:
            return APIResponse(
                status_code=200,
                body=_augment_codex_limit_body(
                    response.body,
                    live_capable=True,
                    refresh_status="cached_latest",
                ),
                headers=response.headers,
            )
        return response


def serve_live_local_api(
    *,
    inbox_root: Path | str,
    data_root: Path | str | None = None,
    host: str = "127.0.0.1",
    port: int = 8000,
    codex_live_app_server_command: str = "codex app-server",
    codex_live_timeout_seconds: float = 15,
    codex_limit_cutoff_percent: int = 90,
    limit_account_scope_id: str = "",
    limit_bucket_id: str = "",
    limit_stale_after_seconds: int | None = None,
    limit_future_tolerance_seconds: int = 30,
) -> None:
    """Serve the live-enabled local API over HTTP until the process is stopped."""

    api = LiveCodexLocalAPI(
        inbox_root=inbox_root,
        data_root=data_root,
        codex_live_app_server_command=codex_live_app_server_command,
        codex_live_timeout_seconds=codex_live_timeout_seconds,
        codex_limit_cutoff_percent=codex_limit_cutoff_percent,
        limit_account_scope_id=limit_account_scope_id,
        limit_bucket_id=limit_bucket_id,
        limit_stale_after_seconds=limit_stale_after_seconds,
        limit_future_tolerance_seconds=limit_future_tolerance_seconds,
    )
    server = ThreadingHTTPServer((host, port), make_request_handler(api))
    print(f"agentic live local api serving on http://{host}:{port}", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def _refresh_live_codex_limits_response(
    *,
    data_root: Path,
    reader: Any | None,
    app_server_command: str,
    timeout_seconds: float,
    cutoff_percent: int,
    account_scope_id: str,
    bucket_id: str,
    stale_after_seconds: int | None,
    future_tolerance_seconds: int,
) -> APIResponse:
    observed_at = _utc_now()
    store = FileCodexLimitAvailabilityStore(data_root / "codex-limits")
    normalized_scope = account_scope_id or "default"
    record_id = _live_limit_record_id(observed_at)
    provider: dict[str, Any] = {"source": "codex_app_server"}

    try:
        active_reader = reader or CodexAppServerLiveStatusReader(
            command=app_server_command,
            timeout_seconds=timeout_seconds,
        )
        payload = active_reader.read()
        auth_summary = summarize_codex_subscription_auth(payload.account, rate_limits_payload=payload.rate_limits)
        auth = codex_live_auth_summary_to_dict(auth_summary)
        provider = _provider_summary(payload.rate_limits, selected_bucket_id=bucket_id)

        if not auth_summary.subscription_auth:
            reason = _redact_secret_text(
                auth_summary.reason or "Codex auth is not confirmed as ChatGPT subscription-backed."
            )
            record = build_unknown_codex_limit_record(
                record_id=record_id,
                observed_at=observed_at,
                source=CodexLimitObservationSource.CODEX_APP_SERVER,
                note=f"Live Codex auth rejected: {reason}",
                account_scope_id=normalized_scope,
                bucket_id=_provider_bucket_id(provider, bucket_id),
            )
            selected = _write_live_limit_record(
                store,
                record,
                account_scope_id=normalized_scope,
                bucket_id=bucket_id,
            )
            return _live_limit_response(
                status_code=403,
                selected=selected,
                stale_after_seconds=stale_after_seconds,
                future_tolerance_seconds=future_tolerance_seconds,
                live_refresh={
                    "status": "auth_rejected",
                    "source": "codex_app_server",
                    "record_id": record.id,
                    "observed_at": observed_at,
                    "error": reason,
                },
                auth=auth,
                provider=provider,
                location={"record_id": record.id, "path": _safe_browser_path(str(store.record_path(record.id)))},
            )

        result = refresh_codex_limit_from_payload(
            payload.rate_limits,
            record_id=record_id,
            observed_at=observed_at,
            cutoff_percent=cutoff_percent,
            account_scope_id=normalized_scope,
            selected_bucket_id=bucket_id,
            source=CodexLimitObservationSource.CODEX_APP_SERVER,
            note="Live Codex App Server quota refresh with ChatGPT subscription auth.",
        )
        selected = _write_live_limit_record(
            store,
            result.record,
            account_scope_id=normalized_scope,
            bucket_id=bucket_id,
        )
        return _live_limit_response(
            status_code=201,
            selected=selected,
            stale_after_seconds=stale_after_seconds,
            future_tolerance_seconds=future_tolerance_seconds,
            live_refresh={
                "status": "refreshed",
                "source": "codex_app_server",
                "record_id": result.record.id,
                "observed_at": observed_at,
                "raw_window_count": result.raw_window_count,
            },
            auth=auth,
            provider=provider,
            location={"record_id": result.record.id, "path": _safe_browser_path(str(store.record_path(result.record.id)))},
        )
    except (CodexLimitSentinelError, OSError, TypeError, ValueError) as error:
        message = _redact_secret_text(str(error) or "Live Codex App Server refresh failed.")
        record = build_unknown_codex_limit_record(
            record_id=record_id,
            observed_at=observed_at,
            source=CodexLimitObservationSource.CODEX_APP_SERVER,
            note=f"Live Codex App Server refresh failed: {message}",
            account_scope_id=normalized_scope,
            bucket_id=bucket_id,
        )
        selected = _write_live_limit_record(
            store,
            record,
            account_scope_id=normalized_scope,
            bucket_id=bucket_id,
        )
        return _live_limit_response(
            status_code=503,
            selected=selected,
            stale_after_seconds=stale_after_seconds,
            future_tolerance_seconds=future_tolerance_seconds,
            live_refresh={
                "status": "unavailable",
                "source": "codex_app_server",
                "record_id": record.id,
                "observed_at": observed_at,
                "error": message,
            },
            auth={
                "subscription_auth": False,
                "account_type": "unknown",
                "plan_type": "",
                "reason": "Codex App Server could not be read safely.",
                "source": "account/read",
            },
            provider=provider,
            location={"record_id": record.id, "path": _safe_browser_path(str(store.record_path(record.id)))},
        )


def _write_live_limit_record(
    store: FileCodexLimitAvailabilityStore,
    record: CodexLimitAvailabilityRecord,
    *,
    account_scope_id: str,
    bucket_id: str,
) -> CodexLimitAvailabilityRecord:
    return store.write_record_and_select_latest(
        record,
        account_scope_id=account_scope_id or record.account_scope_id,
        bucket_id=bucket_id,
        write=lambda candidate: _write_idempotent_operator_limit_record(store, candidate),
    )


def _live_limit_response(
    *,
    status_code: int,
    selected: CodexLimitAvailabilityRecord,
    stale_after_seconds: int | None,
    future_tolerance_seconds: int,
    live_refresh: Mapping[str, Any],
    auth: Mapping[str, Any],
    provider: Mapping[str, Any],
    location: Mapping[str, Any],
) -> APIResponse:
    body = _codex_limits_body_from_record(
        selected,
        stale_after_seconds=stale_after_seconds,
        future_tolerance_seconds=future_tolerance_seconds,
    )
    augmented = _augment_codex_limit_body(
        body,
        live_capable=True,
        refresh_status=str(live_refresh.get("status") or "unknown"),
    )
    augmented.update(
        {
            "live_refresh": dict(live_refresh),
            "auth": dict(auth),
            "provider": dict(provider),
            "location": dict(location),
        }
    )
    return APIResponse(status_code=status_code, body=_redact_values(augmented))


def _augment_codex_limit_body(
    body: Mapping[str, Any],
    *,
    live_capable: bool,
    refresh_status: str,
) -> dict[str, Any]:
    data = dict(body)
    gate = data.get("gate") if isinstance(data.get("gate"), Mapping) else {}
    data["canStartWork"] = bool(gate.get("allowed"))
    data["blocking_reason"] = "" if data["canStartWork"] else str(gate.get("reason") or "Codex limit gate is blocked.")
    data["live_refresh"] = {
        "status": refresh_status,
        "source": "codex_app_server",
        "live_capable": live_capable,
    }

    record = data.get("latest_record") if isinstance(data.get("latest_record"), Mapping) else None
    record_windows = _record_windows_by_id(record)
    windows: list[dict[str, Any]] = []
    for index, window in enumerate(data.get("windows") if isinstance(data.get("windows"), list) else []):
        if not isinstance(window, Mapping):
            continue
        window_id = str(window.get("window_id") or f"window_{index + 1}")
        full_window = record_windows.get(window_id, {})
        remaining = _coerce_percent(window.get("remaining_percent"))
        if remaining is None:
            remaining = _coerce_percent(full_window.get("remaining_percent"))
        used = None if remaining is None else max(0, min(100, 100 - remaining))
        reset_at = str(window.get("reset_at") or full_window.get("reset_at") or "")
        windows.append(
            {
                **dict(window),
                "window_id": window_id,
                "bucket_id": str(full_window.get("bucket_id") or window.get("bucket_id") or ""),
                "window_name": str(full_window.get("window_name") or window.get("window_name") or ""),
                "window_duration_minutes": full_window.get("window_duration_minutes")
                or window.get("window_duration_minutes"),
                "windowDurationMins": full_window.get("window_duration_minutes")
                or window.get("window_duration_minutes"),
                "remainingPercent": remaining,
                "usedPercent": used,
                "resetsAt": reset_at,
                "authoritative": bool(full_window.get("authoritative", window.get("authoritative", index == 0))),
            }
        )
    data["windows"] = windows
    return data


def _record_windows_by_id(record: Mapping[str, Any] | None) -> dict[str, Mapping[str, Any]]:
    if not record:
        return {}
    raw_windows = record.get("windows")
    if not isinstance(raw_windows, list):
        raw_windows = [record.get("short_window"), record.get("broad_quota")]
    result: dict[str, Mapping[str, Any]] = {}
    for index, window in enumerate(raw_windows):
        if not isinstance(window, Mapping):
            continue
        window_id = str(window.get("window_id") or f"window_{index + 1}")
        result[window_id] = window
    return result


def _provider_summary(payload: Mapping[str, Any], *, selected_bucket_id: str) -> dict[str, Any]:
    summary: dict[str, Any] = {"source": "account/rateLimits/read"}
    bucket_id, bucket = _select_provider_bucket(payload, selected_bucket_id=selected_bucket_id)
    summary["raw_bucket_count"] = _bucket_count(payload)
    if bucket_id:
        summary["bucket_id"] = bucket_id
    if bucket:
        summary.update(
            {
                "bucket_name": str(bucket.get("limitName") or ""),
                "plan_type": str(bucket.get("planType") or payload.get("planType") or ""),
                "rate_limit_reached_type": bucket.get("rateLimitReachedType")
                or payload.get("rateLimitReachedType"),
                "spend_control_reached": bucket.get("spendControlReached")
                if isinstance(bucket.get("spendControlReached"), bool)
                else payload.get("spendControlReached")
                if isinstance(payload.get("spendControlReached"), bool)
                else None,
            }
        )
    reset_credits = payload.get("rateLimitResetCredits")
    if isinstance(reset_credits, Mapping):
        summary["reset_credit_count"] = _optional_int(reset_credits.get("availableCount"))
    credits = bucket.get("credits") if isinstance(bucket, Mapping) else None
    if isinstance(credits, Mapping):
        summary["credits"] = {
            "has_credits": credits.get("hasCredits") if isinstance(credits.get("hasCredits"), bool) else None,
            "unlimited": credits.get("unlimited") if isinstance(credits.get("unlimited"), bool) else None,
            "balance": str(credits.get("balance") or ""),
        }
    return summary


def _select_provider_bucket(payload: Mapping[str, Any], *, selected_bucket_id: str) -> tuple[str, Mapping[str, Any]]:
    buckets = payload.get("rateLimitsByLimitId")
    if isinstance(buckets, Mapping):
        typed_buckets = {str(key): value for key, value in buckets.items() if isinstance(value, Mapping)}
        if selected_bucket_id and selected_bucket_id in typed_buckets:
            return selected_bucket_id, typed_buckets[selected_bucket_id]
        legacy = payload.get("rateLimits")
        legacy_id = str(legacy.get("limitId") or "") if isinstance(legacy, Mapping) else ""
        if legacy_id and legacy_id in typed_buckets:
            return legacy_id, typed_buckets[legacy_id]
        if len(typed_buckets) == 1:
            key = next(iter(typed_buckets))
            return key, typed_buckets[key]
    legacy = payload.get("rateLimits")
    if isinstance(legacy, Mapping):
        legacy_id = str(legacy.get("limitId") or selected_bucket_id or "codex")
        return legacy_id, legacy
    return "", {}


def _bucket_count(payload: Mapping[str, Any]) -> int:
    buckets = payload.get("rateLimitsByLimitId")
    if isinstance(buckets, Mapping):
        return len([value for value in buckets.values() if isinstance(value, Mapping)])
    return 1 if isinstance(payload.get("rateLimits"), Mapping) else 0


def _provider_bucket_id(provider: Mapping[str, Any], configured_bucket_id: str) -> str:
    return str(provider.get("bucket_id") or configured_bucket_id or "")


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_percent(value: Any) -> int | None:
    try:
        percent = int(value)
    except (TypeError, ValueError):
        return None
    if percent < 0 or percent > 100:
        return None
    return percent


def _live_limit_record_id(timestamp: str) -> str:
    safe_timestamp = timestamp.replace("-", "").replace(":", "")
    return f"live-codex-{safe_timestamp}-{uuid.uuid4().hex[:12]}"
