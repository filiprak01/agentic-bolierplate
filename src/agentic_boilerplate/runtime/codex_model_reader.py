"""Host-side Codex model discovery through App Server JSON-RPC."""

from __future__ import annotations

import queue
import subprocess
import threading
import time
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from agentic_boilerplate.domain.codex_model_routing import (
    CodexModelDiscoverySnapshot,
    codex_model_discovery_snapshot_from_app_server,
)
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


class CodexAppServerModelReader:
    """Read available Codex models through `codex app-server`."""

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
            "model-list read",
        )
        if diagnostic_limit_chars < 1:
            raise CodexLimitSentinelError("Diagnostic limit must be positive.")
        if protocol_line_limit_chars < 1:
            raise CodexLimitSentinelError("Protocol line limit must be positive.")
        self.diagnostic_limit_chars = diagnostic_limit_chars
        self.protocol_line_limit_chars = protocol_line_limit_chars

    def read(self, *, cancel_event: threading.Event | None = None) -> Mapping[str, Any]:
        """Return the raw `model/list` result as an object with a `models` list."""

        args = _split_app_server_command(self.command)
        if not args or not args[0].strip():
            raise CodexLimitSentinelError("Codex app-server command is empty.")
        if cancel_event is not None and cancel_event.is_set():
            raise CodexLimitSentinelError("Codex app-server model/list read was cancelled before start.")
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
                            "name": "agentic_model_discovery",
                            "title": "Agentic Model Discovery",
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
            _write_json_rpc(process, {"method": "model/list", "id": 2, "params": {}}, diagnostics)
            read_deadline = min(total_deadline, time.monotonic() + self.read_timeout_seconds)
            result = _wait_for_json_rpc_result(
                process=process,
                stdout_events=stdout_events,
                response_id=2,
                deadline=read_deadline,
                phase="model/list",
                diagnostics=diagnostics,
                cancel_event=cancel_event,
                protocol_line_limit_chars=self.protocol_line_limit_chars,
                require_mapping=False,
            )
            if isinstance(result, Mapping):
                return result
            if isinstance(result, Sequence) and not isinstance(result, (str, bytes, bytearray)):
                return {"models": list(result)}
            raise CodexLimitSentinelError("Codex app-server model/list result was not an object or list.")
        except CodexLimitSentinelError:
            raise
        except OSError as exc:
            raise CodexLimitSentinelError(str(exc)) from exc
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

    def discover(
        self,
        *,
        observed_at: str = "",
        snapshot_id: str = "latest",
        rate_limits_payload: Mapping[str, Any] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> CodexModelDiscoverySnapshot:
        """Read and normalize the current model inventory."""

        payload = self.read(cancel_event=cancel_event)
        timestamp = observed_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        return codex_model_discovery_snapshot_from_app_server(
            payload,
            observed_at=timestamp,
            snapshot_id=snapshot_id,
            rate_limits_payload=rate_limits_payload,
        )
