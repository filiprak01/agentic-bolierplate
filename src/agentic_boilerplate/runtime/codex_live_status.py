"""Host-side Codex account and quota status through App Server JSON-RPC."""

from __future__ import annotations

import queue
import subprocess
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from agentic_boilerplate.domain import redact_integration_readiness_text
from agentic_boilerplate.runtime.codex_limit_sentinel import (
    CodexLimitSentinelError,
    _BoundedDiagnostics,
    _positive_timeout,
    _split_app_server_command,
    _start_stream_threads,
    _terminate_and_reap,
    _wait_for_json_rpc_result,
    _write_json_rpc,
)


@dataclass(frozen=True)
class CodexLiveStatusPayload:
    """Raw host-owned account and rate-limit payloads read from Codex App Server."""

    account: Mapping[str, Any]
    rate_limits: Mapping[str, Any]


@dataclass(frozen=True)
class CodexLiveAuthSummary:
    """Sanitized subscription-auth decision used by operator-facing APIs."""

    authenticated: bool
    subscription_auth: bool
    auth_mode: str
    account_type: str
    plan_type: str
    reason: str


class CodexAppServerLiveStatusReader:
    """Read account identity and rate limits from `codex app-server`."""

    def __init__(
        self,
        *,
        command: str | Sequence[str] = "codex app-server",
        timeout_seconds: float = 15,
        initialization_timeout_seconds: float | None = None,
        read_timeout_seconds: float | None = None,
        diagnostic_limit_chars: int = 4096,
        protocol_line_limit_chars: int = 65536,
    ) -> None:
        self.command = command
        self.timeout_seconds = _positive_timeout(timeout_seconds, "total")
        self.initialization_timeout_seconds = _positive_timeout(
            initialization_timeout_seconds if initialization_timeout_seconds is not None else timeout_seconds,
            "initialization",
        )
        self.read_timeout_seconds = _positive_timeout(
            read_timeout_seconds if read_timeout_seconds is not None else timeout_seconds,
            "live status read",
        )
        if diagnostic_limit_chars < 1:
            raise CodexLimitSentinelError("Diagnostic limit must be positive.")
        if protocol_line_limit_chars < 1:
            raise CodexLimitSentinelError("Protocol line limit must be positive.")
        self.diagnostic_limit_chars = diagnostic_limit_chars
        self.protocol_line_limit_chars = protocol_line_limit_chars

    def read(self, *, cancel_event: threading.Event | None = None) -> CodexLiveStatusPayload:
        """Return raw `account/read` and `account/rateLimits/read` results."""

        args = _split_app_server_command(self.command)
        if not args or not args[0].strip():
            raise CodexLimitSentinelError("Codex app-server command is empty.")
        if cancel_event is not None and cancel_event.is_set():
            raise CodexLimitSentinelError("Codex app-server live status read was cancelled before start.")

        process: subprocess.Popen[str] | None = None
        stdout_events: queue.Queue[Any] = queue.Queue()
        diagnostics = _BoundedDiagnostics(self.diagnostic_limit_chars)
        threads: list[threading.Thread] = []
        started_at = time.monotonic()
        total_deadline = started_at + self.timeout_seconds
        try:
            process = subprocess.Popen(
                args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                shell=False,
            )
            if process.stdin is None or process.stdout is None or process.stderr is None:
                raise CodexLimitSentinelError("Codex app-server pipes were not created.")
            threads = _start_stream_threads(
                process,
                stdout_events,
                diagnostics,
                protocol_line_limit_chars=self.protocol_line_limit_chars,
            )
            _write_json_rpc(
                process,
                {
                    "method": "initialize",
                    "id": 1,
                    "params": {
                        "clientInfo": {
                            "name": "agentic_live_status",
                            "title": "Agentic Live Status",
                            "version": "1.0.0",
                        }
                    },
                },
                diagnostics,
            )
            initialization_deadline = min(
                total_deadline,
                started_at + self.initialization_timeout_seconds,
            )
            _wait_for_json_rpc_result(
                process=process,
                stdout_events=stdout_events,
                response_id=1,
                deadline=initialization_deadline,
                phase="initialize",
                diagnostics=diagnostics,
                cancel_event=cancel_event,
                protocol_line_limit_chars=self.protocol_line_limit_chars,
                require_mapping=False,
            )
            _write_json_rpc(process, {"method": "initialized", "params": {}}, diagnostics)
            account = _read_mapping_response(
                process=process,
                stdout_events=stdout_events,
                response_id=2,
                method="account/read",
                phase="account/read",
                total_deadline=total_deadline,
                read_timeout_seconds=self.read_timeout_seconds,
                diagnostics=diagnostics,
                cancel_event=cancel_event,
                protocol_line_limit_chars=self.protocol_line_limit_chars,
            )
            rate_limits = _read_mapping_response(
                process=process,
                stdout_events=stdout_events,
                response_id=3,
                method="account/rateLimits/read",
                phase="account/rateLimits/read",
                total_deadline=total_deadline,
                read_timeout_seconds=self.read_timeout_seconds,
                diagnostics=diagnostics,
                cancel_event=cancel_event,
                protocol_line_limit_chars=self.protocol_line_limit_chars,
            )
            return CodexLiveStatusPayload(account=account, rate_limits=rate_limits)
        except CodexLimitSentinelError:
            raise
        except OSError as exc:
            raise CodexLimitSentinelError(_safe_text(str(exc))) from exc
        finally:
            if process is not None:
                _terminate_and_reap(process)
            for thread in threads:
                thread.join(timeout=0.2)
            if process is not None:
                for stream in (process.stdout, process.stderr):
                    if stream is not None:
                        try:
                            stream.close()
                        except OSError:
                            pass


def _read_mapping_response(
    *,
    process: subprocess.Popen[str],
    stdout_events: queue.Queue[Any],
    response_id: int,
    method: str,
    phase: str,
    total_deadline: float,
    read_timeout_seconds: float,
    diagnostics: _BoundedDiagnostics,
    cancel_event: threading.Event | None,
    protocol_line_limit_chars: int,
) -> Mapping[str, Any]:
    _write_json_rpc(process, {"method": method, "id": response_id, "params": {}}, diagnostics)
    read_deadline = min(total_deadline, time.monotonic() + read_timeout_seconds)
    result = _wait_for_json_rpc_result(
        process=process,
        stdout_events=stdout_events,
        response_id=response_id,
        deadline=read_deadline,
        phase=phase,
        diagnostics=diagnostics,
        cancel_event=cancel_event,
        protocol_line_limit_chars=protocol_line_limit_chars,
        require_mapping=True,
    )
    assert isinstance(result, Mapping)
    return result


def summarize_codex_subscription_auth(
    account_payload: Mapping[str, Any],
    *,
    rate_limits_payload: Mapping[str, Any] | None = None,
) -> CodexLiveAuthSummary:
    """Return a fail-closed, redacted decision for ChatGPT subscription auth."""

    rate_limits = rate_limits_payload or {}
    auth_mode = _first_text(
        account_payload,
        ("authMode", "auth_mode", "authenticationMode", "mode", "loginMode", "credentialType", "authType"),
    )
    account_type = _first_text(account_payload, ("accountType", "account_type", "type", "kind", "source"))
    plan_type = _first_text(
        account_payload,
        ("planType", "plan_type", "plan", "planName", "subscriptionPlan"),
    ) or _first_text(
        rate_limits,
        ("planType", "plan_type", "plan", "planName", "subscriptionPlan"),
    )
    status = _first_text(account_payload, ("status", "state", "loginStatus", "authStatus"))
    markers = " ".join(value.casefold() for value in (auth_mode, account_type, plan_type, status) if value)

    if not account_payload:
        return CodexLiveAuthSummary(False, False, auth_mode, account_type, plan_type, "Codex account/read returned no account data.")
    if _contains_api_key_marker(account_payload):
        return CodexLiveAuthSummary(False, False, auth_mode or "api_key", account_type, plan_type, "Codex appears to be authenticated by API key, not ChatGPT subscription.")
    if any(marker in markers for marker in ("expired", "signed_out", "logged_out", "unauthenticated", "missing")):
        return CodexLiveAuthSummary(False, False, auth_mode, account_type, plan_type, "Codex account is not currently authenticated.")

    authenticated = bool(plan_type) or any(marker in markers for marker in ("authenticated", "signed_in", "logged_in", "chatgpt", "subscription"))
    subscription_auth = bool(plan_type) or any(marker in markers for marker in ("chatgpt", "subscription"))
    if authenticated and subscription_auth:
        return CodexLiveAuthSummary(True, True, auth_mode or "chatgpt", account_type, plan_type, "ChatGPT subscription authentication is available.")
    if authenticated:
        return CodexLiveAuthSummary(True, False, auth_mode, account_type, plan_type, "Codex auth is present but subscription mode is ambiguous.")
    return CodexLiveAuthSummary(False, False, auth_mode, account_type, plan_type, "Codex account state is ambiguous; refresh fails closed.")


def codex_live_auth_summary_to_dict(summary: CodexLiveAuthSummary) -> dict[str, Any]:
    """Convert sanitized auth summary to JSON-compatible data."""

    return {
        "authenticated": summary.authenticated,
        "subscription_auth": summary.subscription_auth,
        "auth_mode": summary.auth_mode,
        "account_type": summary.account_type,
        "plan_type": summary.plan_type,
        "reason": summary.reason,
    }


def _first_text(payload: Mapping[str, Any], names: Sequence[str]) -> str:
    wanted = {name.casefold() for name in names}
    for key, value in _walk_mapping(payload):
        if key.split(".")[-1].casefold() in wanted and isinstance(value, str):
            return _safe_text(value)
    return ""


def _contains_api_key_marker(payload: Mapping[str, Any]) -> bool:
    for key, value in _walk_mapping(payload):
        lowered_key = key.casefold()
        if "apikey" in lowered_key or "api_key" in lowered_key or ("api" in lowered_key and "key" in lowered_key):
            return True
        if isinstance(value, str):
            lowered_value = value.casefold()
            if "api key" in lowered_value or "api_key" in lowered_value or lowered_value.startswith("sk-"):
                return True
    return False


def _walk_mapping(payload: Mapping[str, Any], prefix: str = "") -> list[tuple[str, Any]]:
    items: list[tuple[str, Any]] = []
    for key, value in payload.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        items.append((path, value))
        if isinstance(value, Mapping):
            items.extend(_walk_mapping(value, path))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                if isinstance(item, Mapping):
                    items.extend(_walk_mapping(item, f"{path}[{index}]"))
    return items


def _safe_text(value: str) -> str:
    text = redact_integration_readiness_text(str(value).strip())
    lowered = text.casefold()
    if any(marker in lowered for marker in ("authorization", "token", "secret", "password", "credential", "api_key")):
        return "[redacted]"
    if len(text) > 120:
        return text[:60] + "..." + text[-57:]
    return text
