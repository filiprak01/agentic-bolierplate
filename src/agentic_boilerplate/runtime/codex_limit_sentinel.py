"""Host-side Codex limit signal capture and normalization."""

from __future__ import annotations

import json
import math
import os
import queue
import shlex
import subprocess
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

from agentic_boilerplate.domain import (
    CodexLimitAvailabilityRecord,
    CodexLimitObservationSource,
    CodexLimitPlanMode,
    CodexLimitWindowAvailability,
    CodexLimitWindowStatus,
    build_codex_limit_availability_record,
    redact_integration_readiness_text,
)


class CodexLimitSentinelError(RuntimeError):
    """Raised when the host-side sentinel cannot read usable limit signals."""


@dataclass(frozen=True)
class CodexLimitSentinelResult:
    """Result of one sentinel refresh attempt."""

    record: CodexLimitAvailabilityRecord
    supported: bool
    error_summary: str = ""
    raw_window_count: int = 0


class CodexAppServerLimitReader:
    """Read Codex rate limits through the local Codex app-server JSON-RPC boundary."""

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
            "rate-limit read",
        )
        if diagnostic_limit_chars < 1:
            raise CodexLimitSentinelError("Diagnostic limit must be positive.")
        if protocol_line_limit_chars < 1:
            raise CodexLimitSentinelError("Protocol line limit must be positive.")
        self.diagnostic_limit_chars = diagnostic_limit_chars
        self.protocol_line_limit_chars = protocol_line_limit_chars

    def read(self, *, cancel_event: threading.Event | None = None) -> Mapping[str, Any]:
        """Return the raw `account/rateLimits/read` result."""

        args = _split_app_server_command(self.command)
        if not args or not args[0].strip():
            raise CodexLimitSentinelError("Codex app-server command is empty.")
        if cancel_event is not None and cancel_event.is_set():
            raise CodexLimitSentinelError("Codex app-server read was cancelled before start.")
        process: subprocess.Popen[str] | None = None
        stdout_events: queue.Queue[_StreamEvent] = queue.Queue()
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
                            "name": "agentic_limit_sentinel",
                            "title": "Agentic Limit Sentinel",
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
            _write_json_rpc(
                process,
                {"method": "account/rateLimits/read", "id": 2, "params": {}},
                diagnostics,
            )
            read_deadline = min(total_deadline, time.monotonic() + self.read_timeout_seconds)
            result = _wait_for_json_rpc_result(
                process=process,
                stdout_events=stdout_events,
                response_id=2,
                deadline=read_deadline,
                phase="account/rateLimits/read",
                diagnostics=diagnostics,
                cancel_event=cancel_event,
                protocol_line_limit_chars=self.protocol_line_limit_chars,
                require_mapping=True,
            )
            assert isinstance(result, Mapping)
            return result
        except CodexLimitSentinelError:
            raise
        except OSError as exc:
            raise CodexLimitSentinelError(_sanitized_error(str(exc))) from exc
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


@dataclass(frozen=True)
class _StreamEvent:
    kind: str
    text: str = ""


class _BoundedDiagnostics:
    def __init__(self, limit_chars: int) -> None:
        self._limit_chars = limit_chars
        self._value = ""
        self._truncated = False
        self._lock = threading.Lock()

    def append(self, value: str) -> None:
        if not value:
            return
        with self._lock:
            combined = self._value + value
            if len(combined) > self._limit_chars:
                combined = combined[-self._limit_chars :]
                self._truncated = True
            self._value = combined

    def sanitized_text(self) -> str:
        with self._lock:
            value = self._value.strip()
            truncated = self._truncated
        if not value:
            return ""
        prefix = "[truncated] " if truncated else ""
        return _sanitized_error(prefix + value)


def _start_stream_threads(
    process: subprocess.Popen[str],
    stdout_events: queue.Queue[_StreamEvent],
    diagnostics: _BoundedDiagnostics,
    *,
    protocol_line_limit_chars: int,
) -> list[threading.Thread]:
    assert process.stdout is not None
    assert process.stderr is not None
    stdout_thread = threading.Thread(
        target=_pump_stdout,
        args=(process.stdout, stdout_events, protocol_line_limit_chars),
        name="codex-limit-stdout",
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=_drain_stderr,
        args=(process.stderr, diagnostics),
        name="codex-limit-stderr",
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()
    return [stdout_thread, stderr_thread]


def _pump_stdout(
    stream: TextIO,
    events: queue.Queue[_StreamEvent],
    protocol_line_limit_chars: int,
) -> None:
    try:
        while True:
            line = stream.readline(protocol_line_limit_chars + 1)
            if line == "":
                return
            events.put(_StreamEvent(kind="line", text=line))
    finally:
        events.put(_StreamEvent(kind="eof"))


def _drain_stderr(stream: TextIO, diagnostics: _BoundedDiagnostics) -> None:
    while True:
        chunk = stream.read(1024)
        if chunk == "":
            return
        diagnostics.append(chunk)


def _write_json_rpc(
    process: subprocess.Popen[str],
    message: Mapping[str, Any],
    diagnostics: _BoundedDiagnostics,
) -> None:
    if process.stdin is None:
        raise CodexLimitSentinelError("Codex app-server stdin is unavailable.")
    try:
        process.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
        process.stdin.flush()
    except (BrokenPipeError, OSError) as exc:
        raise CodexLimitSentinelError(
            _error_with_diagnostics(f"Codex app-server input failed: {exc}", diagnostics)
        ) from exc


def _wait_for_json_rpc_result(
    *,
    process: subprocess.Popen[str],
    stdout_events: queue.Queue[_StreamEvent],
    response_id: int,
    deadline: float,
    phase: str,
    diagnostics: _BoundedDiagnostics,
    cancel_event: threading.Event | None,
    protocol_line_limit_chars: int,
    require_mapping: bool,
) -> Any:
    while True:
        if cancel_event is not None and cancel_event.is_set():
            raise CodexLimitSentinelError(
                _error_with_diagnostics(f"Codex app-server {phase} was cancelled.", diagnostics)
            )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise CodexLimitSentinelError(
                _error_with_diagnostics(f"Codex app-server {phase} timed out.", diagnostics)
            )
        try:
            event = stdout_events.get(timeout=min(0.05, remaining))
        except queue.Empty:
            continue
        if event.kind == "eof":
            return_code = process.poll()
            raise CodexLimitSentinelError(
                _error_with_diagnostics(
                    f"Codex app-server exited before {phase} completed (exit={return_code}).",
                    diagnostics,
                )
            )
        line = event.text.strip()
        if not line:
            continue
        if len(line) > protocol_line_limit_chars:
            raise CodexLimitSentinelError(
                _error_with_diagnostics(
                    f"Codex app-server returned an oversized {phase} response.",
                    diagnostics,
                )
            )
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CodexLimitSentinelError(
                _error_with_diagnostics(
                    f"Codex app-server returned malformed JSON during {phase}: {exc.msg}.",
                    diagnostics,
                )
            ) from exc
        if not isinstance(message, Mapping):
            raise CodexLimitSentinelError(
                _error_with_diagnostics(
                    f"Codex app-server returned a non-object message during {phase}.",
                    diagnostics,
                )
            )
        if message.get("id") != response_id:
            continue
        if "error" in message:
            raise CodexLimitSentinelError(
                _error_with_diagnostics(
                    f"Codex app-server {phase} failed: {_json_rpc_error_text(message['error'])}",
                    diagnostics,
                )
            )
        result = message.get("result")
        if require_mapping and not isinstance(result, Mapping):
            raise CodexLimitSentinelError(
                _error_with_diagnostics(
                    f"Codex app-server {phase} result was not an object.",
                    diagnostics,
                )
            )
        return result


def _terminate_and_reap(process: subprocess.Popen[str]) -> None:
    if process.stdin is not None:
        try:
            process.stdin.close()
        except OSError:
            pass
    if process.poll() is None:
        try:
            process.terminate()
        except OSError:
            pass
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except OSError:
            pass
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass


def _split_app_server_command(
    command: str | Sequence[str],
    *,
    windows_style: bool | None = None,
) -> list[str]:
    if not isinstance(command, str):
        return [str(part) for part in command]
    use_windows_style = os.name == "nt" if windows_style is None else windows_style
    try:
        parts = shlex.split(command, posix=not use_windows_style)
    except ValueError as exc:
        raise CodexLimitSentinelError(f"Invalid Codex app-server command: {_sanitized_error(str(exc))}") from exc
    if use_windows_style:
        return [_strip_matching_quotes(part) for part in parts]
    return parts


def _strip_matching_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _positive_timeout(value: float, label: str) -> float:
    try:
        timeout = float(value)
    except (TypeError, ValueError) as exc:
        raise CodexLimitSentinelError(f"Codex app-server {label} timeout must be numeric.") from exc
    if not math.isfinite(timeout) or timeout <= 0:
        raise CodexLimitSentinelError(f"Codex app-server {label} timeout must be positive.")
    return timeout


def _json_rpc_error_text(value: Any) -> str:
    if isinstance(value, Mapping):
        return str(value.get("message") or value)
    return str(value)


def _error_with_diagnostics(message: str, diagnostics: _BoundedDiagnostics) -> str:
    detail = diagnostics.sanitized_text()
    suffix = f" Diagnostics: {detail}" if detail else ""
    return _sanitized_error(message + suffix)


def _sanitized_error(value: str) -> str:
    return redact_integration_readiness_text(value).strip()


def refresh_codex_limit_from_payload(
    payload: Mapping[str, Any],
    *,
    record_id: str,
    observed_at: str,
    cutoff_percent: int = 90,
    account_scope_id: str = "default",
    selected_bucket_id: str = "",
    source: CodexLimitObservationSource | str = CodexLimitObservationSource.CODEX_APP_SERVER,
    note: str = "",
) -> CodexLimitSentinelResult:
    """Normalize a raw app-server rate-limit payload into a durable record."""

    normalized_observed_at = _validated_iso_timestamp(observed_at, "Observation")
    normalized_cutoff = _validated_percentage(cutoff_percent, "Cutoff percentage")
    windows = _extract_windows(
        payload,
        observed_at=normalized_observed_at,
        cutoff_percent=normalized_cutoff,
        selected_bucket_id=selected_bucket_id,
        source=_coerce_source(source),
    )
    if not windows:
        raise CodexLimitSentinelError("No supported Codex rate-limit windows were found.")
    if len(windows) == 1:
        record = build_codex_limit_availability_record(
            record_id=record_id,
            short_window=windows[0],
            broad_quota=windows[0],
            plan_mode=CodexLimitPlanMode.SINGLE_POOL,
            windows=windows,
            note=note,
            account_scope_id=account_scope_id,
        )
    else:
        record = build_codex_limit_availability_record(
            record_id=record_id,
            short_window=windows[0],
            broad_quota=windows[1],
            plan_mode=CodexLimitPlanMode.DYNAMIC,
            windows=windows,
            note=note,
            account_scope_id=account_scope_id,
        )
    return CodexLimitSentinelResult(record=record, supported=True, raw_window_count=len(windows))


def build_unknown_codex_limit_record(
    *,
    record_id: str,
    observed_at: str,
    source: CodexLimitObservationSource | str = CodexLimitObservationSource.UNKNOWN,
    note: str,
    account_scope_id: str = "default",
    bucket_id: str = "",
) -> CodexLimitAvailabilityRecord:
    """Build a safe blocked record when automatic reading is unavailable."""

    unknown = CodexLimitWindowAvailability(
        status=CodexLimitWindowStatus.UNKNOWN,
        remaining_percent=None,
        reset_at="",
        observation_source=_coerce_source(source),
        observed_at=observed_at,
        window_id="unknown",
        label="Codex limit state unknown",
        bucket_id=bucket_id,
    )
    return build_codex_limit_availability_record(
        record_id=record_id,
        short_window=unknown,
        broad_quota=unknown,
        plan_mode=CodexLimitPlanMode.SINGLE_POOL,
        windows=(unknown,),
        note=note,
        account_scope_id=account_scope_id,
    )


def load_rate_limit_payload(path: Path | str) -> Mapping[str, Any]:
    """Load an offline JSON payload used by tests and manual diagnostics."""

    with Path(path).open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, Mapping):
        raise CodexLimitSentinelError("Rate-limit payload must be a JSON object.")
    return data


def _extract_windows(
    payload: Mapping[str, Any],
    *,
    observed_at: str,
    cutoff_percent: int,
    selected_bucket_id: str,
    source: CodexLimitObservationSource,
) -> tuple[CodexLimitWindowAvailability, ...]:
    bucket_id, bucket = _select_rate_limit_bucket(
        payload,
        selected_bucket_id=selected_bucket_id,
    )
    bucket_label = _provider_text(bucket.get("limitName"), "limitName")
    windows: list[CodexLimitWindowAvailability] = []
    provider_blocker = _provider_blocker(payload, bucket)
    for window_name, window_data in _window_items(bucket):
        windows.append(
            _window_from_payload(
                bucket_id=bucket_id,
                bucket_label=bucket_label,
                window_name=window_name,
                window_data=window_data,
                provider_blocker=provider_blocker,
                observed_at=observed_at,
                cutoff_percent=cutoff_percent,
                source=source,
            )
        )
    return tuple(windows)


def _select_rate_limit_bucket(
    payload: Mapping[str, Any],
    *,
    selected_bucket_id: str,
) -> tuple[str, Mapping[str, Any]]:
    requested_id = selected_bucket_id.strip()
    candidates = payload.get("rateLimitsByLimitId")
    if "rateLimitsByLimitId" in payload and not isinstance(candidates, Mapping):
        raise CodexLimitSentinelError("rateLimitsByLimitId must be an object when provided.")
    if isinstance(candidates, Mapping):
        bucket_map = {
            str(bucket_id): bucket
            for bucket_id, bucket in candidates.items()
            if isinstance(bucket, Mapping)
        }
        legacy = payload.get("rateLimits")
        legacy_id = (
            _provider_text(legacy.get("limitId"), "rateLimits.limitId")
            if isinstance(legacy, Mapping)
            else ""
        )
        applicable_id = requested_id or legacy_id
        if not applicable_id:
            if len(bucket_map) == 1:
                applicable_id = next(iter(bucket_map))
            else:
                raise CodexLimitSentinelError(
                    "Codex rate-limit bucket is ambiguous; configure CODEX_LIMIT_BUCKET_ID "
                    "or use an App Server payload with rateLimits.limitId."
                )
        bucket = bucket_map.get(applicable_id)
        if bucket is None:
            available = ", ".join(
                _provider_text(value, "rate-limit bucket id") for value in sorted(bucket_map)
            ) or "none"
            raise CodexLimitSentinelError(
                f"Selected Codex rate-limit bucket "
                f"{_provider_text(applicable_id, 'selected bucket id')!r} is unavailable "
                f"(available: {available}); configure CODEX_LIMIT_BUCKET_ID."
            )
        declared_id = _provider_text(bucket.get("limitId"), "limitId")
        if declared_id and declared_id != applicable_id:
            raise CodexLimitSentinelError(
                f"Codex rate-limit bucket key "
                f"{_provider_text(applicable_id, 'bucket key')!r} does not match "
                f"its limitId {declared_id!r}."
            )
        return _provider_text(applicable_id, "bucket id"), bucket
    rate_limits = payload.get("rateLimits")
    if isinstance(rate_limits, Mapping):
        declared_id = _provider_text(rate_limits.get("limitId"), "rateLimits.limitId")
        if requested_id and declared_id and requested_id != declared_id:
            raise CodexLimitSentinelError(
                f"Selected Codex rate-limit bucket "
                f"{_provider_text(requested_id, 'selected bucket id')!r} does not match "
                f"the legacy rateLimits.limitId {declared_id!r}."
            )
        return _provider_text(requested_id or declared_id or "codex", "bucket id"), rate_limits
    if any(isinstance(payload.get(name), Mapping) for name in ("primary", "secondary")):
        declared_id = _provider_text(payload.get("limitId"), "limitId")
        if requested_id and declared_id and requested_id != declared_id:
            raise CodexLimitSentinelError(
                f"Selected Codex rate-limit bucket "
                f"{_provider_text(requested_id, 'selected bucket id')!r} does not match "
                f"the payload limitId {declared_id!r}."
            )
        return _provider_text(requested_id or declared_id or "codex", "bucket id"), payload
    raise CodexLimitSentinelError("No supported Codex rate-limit bucket was found.")


def _window_items(bucket: Mapping[str, Any]) -> tuple[tuple[str, Mapping[str, Any]], ...]:
    primary = bucket.get("primary")
    if not isinstance(primary, Mapping):
        raise CodexLimitSentinelError(
            "Selected Codex rate-limit bucket is missing the required primary window."
        )
    windows: list[tuple[str, Mapping[str, Any]]] = [("primary", primary)]
    secondary = bucket.get("secondary")
    if isinstance(secondary, Mapping):
        windows.append(("secondary", secondary))
    elif secondary is not None:
        raise CodexLimitSentinelError(
            "Selected Codex rate-limit bucket has an invalid secondary window."
        )
    known_names = {
        "primary",
        "secondary",
        "limitId",
        "limitName",
        "planType",
        "credits",
        "rateLimitReachedType",
        "spendControlReached",
        "rateLimitReached",
    }
    for key in sorted(bucket, key=lambda value: str(value)):
        name = str(key)
        if name in known_names:
            continue
        candidate = bucket.get(key)
        if isinstance(candidate, Mapping) and any(
            field in candidate for field in ("usedPercent", "resetsAt", "windowDurationMins")
        ):
            windows.append((_provider_text(name, "window name"), candidate))
    return tuple(windows)


def _window_from_payload(
    *,
    bucket_id: str,
    bucket_label: str,
    window_name: str,
    window_data: Mapping[str, Any],
    provider_blocker: str,
    observed_at: str,
    cutoff_percent: int,
    source: CodexLimitObservationSource,
) -> CodexLimitWindowAvailability:
    used_percent = _validated_percentage(
        window_data.get("usedPercent"),
        f"{bucket_id}.{window_name}.usedPercent",
    )
    reset_at = _reset_at(window_data.get("resetsAt"))
    # The durable contract stores whole percentages. Ceiling preserves the
    # provider's exact cutoff decision for fractional usage just below it.
    remaining_percent = int(math.ceil(100 - used_percent))
    if provider_blocker or used_percent >= cutoff_percent:
        status = CodexLimitWindowStatus.LIMITED
    else:
        status = CodexLimitWindowStatus.AVAILABLE
    duration = _window_duration_minutes(window_data.get("windowDurationMins"))
    label = _window_label(bucket_id, bucket_label, window_name, window_data)
    return CodexLimitWindowAvailability(
        status=status,
        remaining_percent=remaining_percent,
        reset_at=reset_at,
        observation_source=source,
        observed_at=observed_at,
        window_id=f"{bucket_id}_{window_name}",
        label=label,
        authoritative=window_name == "primary",
        bucket_id=bucket_id,
        window_name=window_name,
        window_duration_minutes=duration,
    )


def _window_label(
    bucket_id: str,
    bucket_label: str,
    window_name: str,
    window_data: Mapping[str, Any],
) -> str:
    configured_label = _provider_text(window_data.get("label"), "window label")
    if configured_label:
        return configured_label
    base = bucket_label or bucket_id.replace("_", " ").title()
    duration = window_data.get("windowDurationMins")
    if duration is None:
        return f"{base} - {window_name.replace('_', ' ').title()}"
    return f"{base} - {window_name.replace('_', ' ').title()} ({duration} min)"


def _window_duration_minutes(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise CodexLimitSentinelError("Window duration must be a positive integer.")
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise CodexLimitSentinelError("Window duration must be a positive integer.") from exc
    if not math.isfinite(numeric) or numeric <= 0 or not numeric.is_integer():
        raise CodexLimitSentinelError("Window duration must be a positive integer.")
    return int(numeric)


def _validated_percentage(value: Any, field_name: str) -> float:
    if value is None or value == "" or isinstance(value, bool):
        raise CodexLimitSentinelError(f"{field_name} must be a finite number within 0..100.")
    try:
        percentage = float(value)
    except (TypeError, ValueError) as exc:
        raise CodexLimitSentinelError(
            f"{field_name} must be a finite number within 0..100."
        ) from exc
    if not math.isfinite(percentage) or percentage < 0 or percentage > 100:
        raise CodexLimitSentinelError(f"{field_name} must be a finite number within 0..100.")
    return percentage


def _reset_at(value: Any) -> str:
    if value is None or value == "" or isinstance(value, bool):
        raise CodexLimitSentinelError("Rate-limit reset timestamp is required.")
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            raise CodexLimitSentinelError("Rate-limit reset timestamp is invalid.")
        return _timestamp_to_utc(value)
    text = str(value).strip()
    if text.isdigit():
        return _timestamp_to_utc(float(text))
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise CodexLimitSentinelError("Rate-limit reset timestamp is invalid.") from exc
    if parsed.tzinfo is None:
        raise CodexLimitSentinelError("Rate-limit reset timestamp must include a timezone.")
    return text


def _timestamp_to_utc(timestamp: float) -> str:
    try:
        parsed = datetime.fromtimestamp(timestamp, timezone.utc)
    except (OverflowError, OSError, ValueError) as exc:
        raise CodexLimitSentinelError("Rate-limit reset timestamp is invalid.") from exc
    return parsed.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _validated_iso_timestamp(value: Any, field_name: str) -> str:
    text = str(value).strip()
    if not text:
        raise CodexLimitSentinelError(f"{field_name} timestamp is required.")
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise CodexLimitSentinelError(f"{field_name} timestamp is invalid.") from exc
    if parsed.tzinfo is None:
        raise CodexLimitSentinelError(f"{field_name} timestamp must include a timezone.")
    return text


def _provider_blocker(
    payload: Mapping[str, Any],
    bucket: Mapping[str, Any],
) -> str:
    blockers: list[str] = []
    for source_name, source_data in (("payload", payload), ("bucket", bucket)):
        reached_type = source_data.get("rateLimitReachedType")
        if reached_type not in (None, ""):
            if not isinstance(reached_type, str):
                raise CodexLimitSentinelError(
                    f"{source_name}.rateLimitReachedType has an unsupported value."
                )
            blockers.append(f"rateLimitReachedType={reached_type.strip() or 'unknown'}")
        for field_name in ("spendControlReached", "rateLimitReached"):
            value = source_data.get(field_name)
            if value is None:
                continue
            if not isinstance(value, bool):
                raise CodexLimitSentinelError(
                    f"{source_name}.{field_name} has an unsupported value."
                )
            if value:
                blockers.append(field_name)
    return ", ".join(dict.fromkeys(blockers))


def _provider_text(value: Any, field_name: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise CodexLimitSentinelError(f"{field_name} must be text when provided.")
    sanitized = _sanitized_error(value.strip())
    if len(sanitized) > 200:
        return sanitized[:100] + "..." + sanitized[-97:]
    return sanitized


def _coerce_source(value: CodexLimitObservationSource | str) -> CodexLimitObservationSource:
    if isinstance(value, CodexLimitObservationSource):
        return value
    try:
        return CodexLimitObservationSource(str(value).strip())
    except ValueError as exc:
        raise CodexLimitSentinelError(f"Unsupported Codex limit source: {value!r}.") from exc


def _optional_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
