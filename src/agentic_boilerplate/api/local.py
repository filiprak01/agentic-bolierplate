"""Minimal local API for platform workers and future UI surfaces."""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from dataclasses import replace
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from agentic_boilerplate.domain import (
    AgentCommunicationChannel,
    AgentMessageStatus,
    AgentMessageType,
    AgentRole,
    CodexLimitAvailabilityRecord,
    CodexLimitObservationSource,
    CodexLimitPlanMode,
    CodexLimitWindowAvailability,
    CodexLimitWindowStatus,
    InboxAuditEvent,
    InboxMessageType,
    InboxSchemaError,
    InboxStatus,
    POInboxItem,
    build_codex_limit_availability_record,
    build_single_pool_codex_limit_availability_record,
    codex_limit_windows_for_display,
    decide_codex_limit_gate,
    inbox_item_to_dict,
)
from agentic_boilerplate.domain.agent_communication import AgentMessage, agent_message_to_dict
from agentic_boilerplate.domain.agent_communication import (
    AgentMessagePriority,
    agent_message_idempotency_key,
    build_agent_message,
)
from agentic_boilerplate.domain.agent_assignment import (
    AgentAssignment,
    AssignmentStatus,
    TERMINAL_ASSIGNMENT_STATUSES,
)
from agentic_boilerplate.domain.codex_limit_availability import codex_limit_availability_record_to_dict
from agentic_boilerplate.domain.test_evidence_artifact import redact_evidence_text
from agentic_boilerplate.storage import FilePOInboxStore, InboxItemNotFoundError, POInboxStoreError
from agentic_boilerplate.storage.agent_communication import (
    AgentCommunicationStoreError,
    AgentMessageNotFoundError,
    FileAgentCommunicationStore,
)
from agentic_boilerplate.storage.agent_assignment import (
    AgentAssignmentNotFoundError,
    AgentAssignmentStoreError,
    FileAgentAssignmentStore,
)
from agentic_boilerplate.storage.codex_limit_availability import (
    CodexLimitAvailabilitySelectionError,
    ConflictingCodexLimitAvailabilityRecordError,
    FileCodexLimitAvailabilityStore,
    InvalidCodexLimitAvailabilityIdError,
    resolve_codex_limit_write_bucket_id,
)


OPERATOR_RESCUE_ACTIONS: tuple[str, ...] = (
    "pause",
    "resume",
    "retry",
    "requeue",
    "cancel",
    "clear-stale-lock",
    "refresh-diagnostics",
)
OPERATOR_RESCUE_LIMIT_ACTIONS: frozenset[str] = frozenset({"resume", "retry", "requeue", "clear-stale-lock"})
OPERATOR_RESCUE_ACTIVE_STATUSES: frozenset[AssignmentStatus] = frozenset(
    {
        AssignmentStatus.QUEUED,
        AssignmentStatus.ASSIGNED,
        AssignmentStatus.IN_PROGRESS,
        AssignmentStatus.PAUSED_LIMIT,
        AssignmentStatus.PAUSED_PO,
    }
)
OPERATOR_RESCUE_STALE_LOCK_MINUTES = 60


@dataclass(frozen=True)
class APIResponse:
    status_code: int
    body: dict[str, Any]
    headers: Mapping[str, str] = field(default_factory=lambda: {"Content-Type": "application/json"})

    def to_json_bytes(self) -> bytes:
        return json.dumps(self.body, indent=2, sort_keys=True).encode("utf-8") + b"\n"


@dataclass(frozen=True)
class InboxProjectSource:
    """Local project inbox source configured for the operator API."""

    project_id: str
    project_name: str
    jira_project_key: str
    repository: str
    inbox_root: Path

    @property
    def source_key(self) -> str:
        return self.project_id or self.jira_project_key or "default"


@dataclass(frozen=True)
class OperatorRescueDecision:
    """Safe operator action decision for a durable assignment."""

    action: str
    allowed: bool
    reason: str
    blockers: tuple[str, ...]
    effect: str


class LocalAPI:
    """Route minimal local API requests without calling external systems."""

    def __init__(
        self,
        inbox_root: Path | str,
        data_root: Path | str | None = None,
        inbox_projects: tuple[InboxProjectSource, ...] | None = None,
        limit_account_scope_id: str = "",
        limit_bucket_id: str = "",
        limit_stale_after_seconds: int | None = None,
        limit_future_tolerance_seconds: int = 30,
    ) -> None:
        self.inbox_root = Path(inbox_root)
        self.data_root = Path(data_root) if data_root is not None else _infer_data_root(self.inbox_root)
        self.store = FilePOInboxStore(self.inbox_root)
        self.inbox_projects = inbox_projects or _load_operator_inbox_projects(self.data_root, self.inbox_root)
        self.limit_account_scope_id = limit_account_scope_id
        self.limit_bucket_id = limit_bucket_id
        self.limit_stale_after_seconds = limit_stale_after_seconds
        self.limit_future_tolerance_seconds = limit_future_tolerance_seconds

    def handle_request(self, method: str, target: str, body: Mapping[str, Any] | None = None) -> APIResponse:
        parsed = urlsplit(target)
        path_parts = [unquote(part) for part in parsed.path.split("/") if part]
        query = {key: values[-1] for key, values in parse_qs(parsed.query).items() if values}
        request_body = body or {}

        try:
            return self._dispatch(method.upper(), path_parts, query, request_body)
        except ConflictingCodexLimitAvailabilityRecordError:
            return _error_response(
                409,
                "immutable_record_conflict",
                "A Codex limit record with this id already exists with different immutable content.",
            )
        except InvalidCodexLimitAvailabilityIdError:
            return _error_response(
                400,
                "bad_request",
                "Codex limit record id is invalid.",
            )
        except (InboxItemNotFoundError, AgentMessageNotFoundError, AgentAssignmentNotFoundError) as error:
            return _error_response(404, "not_found", str(error))
        except (
            InboxSchemaError,
            POInboxStoreError,
            AgentCommunicationStoreError,
            AgentAssignmentStoreError,
            ValueError,
            TypeError,
        ) as error:
            return _error_response(400, "bad_request", str(error))

    def _dispatch(
        self,
        method: str,
        path_parts: list[str],
        query: Mapping[str, str],
        body: Mapping[str, Any],
    ) -> APIResponse:
        if method == "GET" and path_parts == ["health"]:
            return APIResponse(
                status_code=200,
                body={
                    "status": "ok",
                    "service": "agentic-boilerplate",
                    "external_systems_checked": False,
                    "po_inbox_ready": True,
                },
            )

        if method == "GET" and path_parts == ["operator-status"]:
            return APIResponse(
                status_code=200,
                body=_operator_status_body(
                    self.data_root,
                    account_scope_id=self.limit_account_scope_id,
                    bucket_id=self.limit_bucket_id,
                    stale_after_seconds=self.limit_stale_after_seconds,
                    future_tolerance_seconds=self.limit_future_tolerance_seconds,
                ),
            )

        if method == "GET" and path_parts == ["operator-rescue"]:
            return APIResponse(
                status_code=200,
                body=_operator_rescue_body(
                    self.data_root,
                    query=query,
                    account_scope_id=self.limit_account_scope_id,
                    bucket_id=self.limit_bucket_id,
                    stale_after_seconds=self.limit_stale_after_seconds,
                    future_tolerance_seconds=self.limit_future_tolerance_seconds,
                ),
            )

        if method == "GET" and len(path_parts) == 2 and path_parts[0] == "operator-rescue":
            return APIResponse(
                status_code=200,
                body=_operator_rescue_assignment_body(
                    self.data_root,
                    path_parts[1],
                    query=query,
                    account_scope_id=self.limit_account_scope_id,
                    bucket_id=self.limit_bucket_id,
                    stale_after_seconds=self.limit_stale_after_seconds,
                    future_tolerance_seconds=self.limit_future_tolerance_seconds,
                ),
            )

        if method == "POST" and len(path_parts) == 3 and path_parts[0] == "operator-rescue":
            return _apply_operator_rescue_action_response(
                self.data_root,
                path_parts[1],
                path_parts[2],
                body,
                account_scope_id=self.limit_account_scope_id,
                bucket_id=self.limit_bucket_id,
                stale_after_seconds=self.limit_stale_after_seconds,
                future_tolerance_seconds=self.limit_future_tolerance_seconds,
            )

        if method == "GET" and path_parts == ["agent-messages"]:
            return APIResponse(status_code=200, body=_agent_messages_body(self.data_root, query=query))

        if method == "POST" and path_parts == ["agent-messages"]:
            return _create_agent_message_response(self.data_root, body)

        if method == "GET" and len(path_parts) == 2 and path_parts[0] == "agent-messages":
            return APIResponse(status_code=200, body=_agent_message_read_body(self.data_root, path_parts[1]))

        if method == "POST" and len(path_parts) == 3 and path_parts[0] == "agent-messages":
            if path_parts[2] == "acknowledge":
                message = FileAgentCommunicationStore(self.data_root / "agent-state").acknowledge_message(
                    path_parts[1],
                    acknowledged_at=_utc_now(),
                )
                return APIResponse(status_code=200, body={"item": _agent_message_api_body(message)})
            if path_parts[2] == "consume":
                message = FileAgentCommunicationStore(self.data_root / "agent-state").consume_message(
                    path_parts[1],
                    consumed_at=_utc_now(),
                )
                return APIResponse(status_code=200, body={"item": _agent_message_api_body(message)})
            if path_parts[2] == "respond":
                return _respond_to_agent_message_response(self.data_root, path_parts[1], body)

        if method == "GET" and path_parts == ["codex-limits"]:
            return APIResponse(
                status_code=200,
                body=_codex_limits_body(
                    self.data_root,
                    account_scope_id=self.limit_account_scope_id,
                    bucket_id=self.limit_bucket_id,
                    stale_after_seconds=self.limit_stale_after_seconds,
                    future_tolerance_seconds=self.limit_future_tolerance_seconds,
                ),
            )

        if method == "POST" and path_parts == ["codex-limits", "records"]:
            limit_store = FileCodexLimitAvailabilityStore(self.data_root / "codex-limits")
            account_scope_id = _configured_limit_scope_value(
                body.get("account_scope_id"),
                configured_value=self.limit_account_scope_id,
                fallback="default",
                field_name="account_scope_id",
            )
            default_bucket_id = _resolve_operator_limit_default_bucket_id(
                limit_store,
                body,
                account_scope_id=account_scope_id,
                configured_bucket_id=self.limit_bucket_id,
            )
            record = _codex_limit_record_from_update_body(
                body,
                default_account_scope_id=self.limit_account_scope_id,
                default_bucket_id=default_bucket_id,
            )
            written_record_id = record.id
            selected_record = limit_store.write_record_and_select_latest(
                record,
                account_scope_id=account_scope_id,
                bucket_id=self.limit_bucket_id,
                write=lambda candidate: _write_idempotent_operator_limit_record(
                    limit_store,
                    candidate,
                ),
            )
            return APIResponse(
                status_code=201,
                body=_redact_values(
                    {
                        **_codex_limits_body_from_record(
                            selected_record,
                            stale_after_seconds=self.limit_stale_after_seconds,
                            future_tolerance_seconds=self.limit_future_tolerance_seconds,
                        ),
                        "location": {
                            "record_id": written_record_id,
                            "path": _safe_browser_path(str(limit_store.record_path(written_record_id))),
                        },
                    }
                ),
            )

        if method == "GET" and path_parts == ["po-inbox"]:
            status = InboxStatus(query["status"]) if "status" in query else None
            return APIResponse(status_code=200, body=self._list_inbox_items(status=status, query=query))

        if method == "GET" and path_parts == ["po-inbox", "export"]:
            status = InboxStatus(query["status"]) if "status" in query else None
            return APIResponse(status_code=200, body=self._export_inbox_items(status=status, query=query))

        if method == "GET" and len(path_parts) == 2 and path_parts[0] == "po-inbox":
            source, store, item_id = self._resolve_inbox_item_ref(path_parts[1])
            return APIResponse(status_code=200, body={"item": _inbox_item_api_body(store.read(item_id), source)})

        if method == "POST" and path_parts == ["po-inbox"]:
            item = _item_from_create_body(body)
            location = self.store.create(item)
            return APIResponse(
                status_code=201,
                body={
                    "item": _inbox_item_api_body(item, _default_inbox_project_source(self.inbox_root)),
                    "location": {
                        "item_id": location.item_id,
                        "status": location.status.value,
                        "path": _safe_browser_path(str(location.path)),
                    },
                },
            )

        if method == "POST" and len(path_parts) == 3 and path_parts[0] == "po-inbox":
            item_id = path_parts[1]
            action = path_parts[2]
            if action == "answer":
                return self._apply_decision(item_id, body, InboxStatus.ANSWERED, "answered")
            if action == "approve":
                return self._apply_decision(item_id, body, InboxStatus.APPROVED, "approved")
            if action == "reject":
                return self._apply_decision(item_id, body, InboxStatus.REJECTED, "rejected")
            if action == "resolve":
                return self._resolve_item(item_id, body)

        return _error_response(404, "not_found", f"No route for {method} /{'/'.join(path_parts)}.")

    def _list_inbox_items(self, *, status: InboxStatus | None, query: Mapping[str, str]) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        project_errors: list[dict[str, str]] = []
        project_filter = query.get("project_id", "")
        agent_role_filter = query.get("agent_role", "")
        message_type_filter = query.get("message_type", "")
        jira_issue_filter = query.get("jira_issue_key", "")

        for source in self.inbox_projects:
            if (
                project_filter
                and source.source_key != "default"
                and project_filter not in {source.project_id, source.jira_project_key, source.source_key}
            ):
                continue
            try:
                source_store = FilePOInboxStore(source.inbox_root)
                for item in source_store.list_items(status=status):
                    if project_filter and project_filter not in {
                        item.project_id,
                        item.jira_project_key,
                        source.project_id,
                        source.jira_project_key,
                        source.source_key,
                    }:
                        continue
                    if not _matches_inbox_filters(
                        item,
                        agent_role=agent_role_filter,
                        message_type=message_type_filter,
                        jira_issue_key=jira_issue_filter,
                    ):
                        continue
                    items.append(_inbox_item_api_body(item, source))
            except (InboxSchemaError, POInboxStoreError, OSError, ValueError, TypeError):
                project_errors.append(_project_error_body(source))

        items.sort(key=lambda item: (item.get("created_at") or "", item.get("composite_id") or ""), reverse=True)
        return {
            "items": items,
            "projects": [_project_public_body(source) for source in self.inbox_projects],
            "project_errors": project_errors,
        }

    def _export_inbox_items(self, *, status: InboxStatus | None, query: Mapping[str, str]) -> dict[str, Any]:
        project_filter = query.get("project_id", "")
        filters = _export_filter_body(status=status, query=query)
        exported_projects: list[dict[str, Any]] = []
        safe_errors: list[dict[str, str]] = []

        for source in self.inbox_projects:
            if (
                project_filter
                and project_filter != "all"
                and source.source_key != "default"
                and project_filter not in {source.project_id, source.jira_project_key, source.source_key}
            ):
                continue
            try:
                source_items: list[dict[str, Any]] = []
                for item in FilePOInboxStore(source.inbox_root).list_items(status=status):
                    if project_filter and project_filter != "all" and project_filter not in {
                        item.project_id,
                        item.jira_project_key,
                        source.project_id,
                        source.jira_project_key,
                        source.source_key,
                    }:
                        continue
                    if not _matches_inbox_filters(
                        item,
                        agent_role=query.get("agent_role", ""),
                        message_type=query.get("message_type", ""),
                        jira_issue_key=query.get("jira_issue_key", ""),
                    ):
                        continue
                    source_items.append(_inbox_item_api_body(item, source))
                source_items.sort(
                    key=lambda item: (item.get("created_at") or "", item.get("composite_id") or ""),
                    reverse=True,
                )
                exported_projects.append(
                    {
                        "project": _project_public_body(source),
                        "items": source_items,
                    }
                )
            except (InboxSchemaError, POInboxStoreError, OSError, ValueError, TypeError):
                safe_errors.append(_project_error_body(source))

        generated_at = _utc_now()
        if project_filter and project_filter != "all":
            project_export = exported_projects[0] if exported_projects else {"project": {}, "items": []}
            return {
                "schema_version": "po-inbox-export/v1",
                "generated_at": generated_at,
                "scope": "project",
                "filters": filters,
                "project": project_export["project"],
                "items": project_export["items"],
                "errors": safe_errors,
            }

        return {
            "schema_version": "po-inbox-export/v1",
            "generated_at": generated_at,
            "scope": "all_projects",
            "filters": filters,
            "projects": exported_projects,
            "errors": safe_errors,
        }

    def _resolve_inbox_item_ref(self, item_ref: str) -> tuple[InboxProjectSource, FilePOInboxStore, str]:
        if "::" not in item_ref:
            return _default_inbox_project_source(self.inbox_root), self.store, item_ref

        source_key, item_id = item_ref.split("::", 1)
        if not item_id:
            raise InboxItemNotFoundError(f"PO inbox item {item_ref!r} was not found.")
        for source in self.inbox_projects:
            if source_key in {source.source_key, source.project_id, source.jira_project_key}:
                return source, FilePOInboxStore(source.inbox_root), item_id
        raise InboxItemNotFoundError(f"PO inbox project {source_key!r} was not found.")

    def _apply_decision(
        self,
        item_ref: str,
        body: Mapping[str, Any],
        status: InboxStatus,
        action: str,
    ) -> APIResponse:
        timestamp = _utc_now()
        answer = _required_text(body, "answer")
        actor = _optional_text(body.get("actor"), "po")

        def apply(item: POInboxItem) -> POInboxItem:
            return replace(
                item,
                status=status,
                answer=answer,
                answered_at=timestamp,
                audit=item.audit
                + (
                    InboxAuditEvent(
                        timestamp=timestamp,
                        actor=actor,
                        action=action,
                    ),
                ),
            )

        source, store, item_id = self._resolve_inbox_item_ref(item_ref)
        location = store.update(item_id, apply)
        item = store.read(item_id)
        return APIResponse(
            status_code=200,
            body={"item": _inbox_item_api_body(item, source), "location": _location_body(location)},
        )

    def _resolve_item(self, item_ref: str, body: Mapping[str, Any]) -> APIResponse:
        timestamp = _utc_now()
        actor = _optional_text(body.get("actor"), "po")
        note = _optional_text(body.get("note"))

        def apply(item: POInboxItem) -> POInboxItem:
            return replace(
                item,
                status=InboxStatus.ARCHIVED,
                audit=item.audit
                + (
                    InboxAuditEvent(
                        timestamp=timestamp,
                        actor=actor,
                        action="resolved",
                        note=note,
                    ),
                ),
            )

        source, store, item_id = self._resolve_inbox_item_ref(item_ref)
        location = store.update(item_id, apply)
        item = store.read(item_id)
        return APIResponse(
            status_code=200,
            body={"item": _inbox_item_api_body(item, source), "location": _location_body(location)},
        )


def make_request_handler(api: LocalAPI) -> type[BaseHTTPRequestHandler]:
    """Create a stdlib request handler bound to a LocalAPI instance."""

    class LocalAPIRequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib handler method name
            self._handle()

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler method name
            self._handle()

        def do_OPTIONS(self) -> None:  # noqa: N802 - stdlib handler method name
            self.send_response(204)
            self._send_cors_headers()
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            return

        def _handle(self) -> None:
            try:
                response = api.handle_request(self.command, self.path, _read_json_body(self))
            except (json.JSONDecodeError, ValueError) as error:
                response = _error_response(400, "bad_request", str(error))
            payload = response.to_json_bytes()
            self.send_response(response.status_code)
            for key, value in response.headers.items():
                self.send_header(key, value)
            self._send_cors_headers()
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _send_cors_headers(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

    return LocalAPIRequestHandler


def serve_local_api(
    *,
    inbox_root: Path | str,
    data_root: Path | str | None = None,
    host: str = "127.0.0.1",
    port: int = 8000,
    limit_account_scope_id: str = "",
    limit_bucket_id: str = "",
    limit_stale_after_seconds: int | None = None,
    limit_future_tolerance_seconds: int = 30,
) -> None:
    """Serve the local API over HTTP until the process is stopped."""

    api = LocalAPI(
        inbox_root=inbox_root,
        data_root=data_root,
        limit_account_scope_id=limit_account_scope_id,
        limit_bucket_id=limit_bucket_id,
        limit_stale_after_seconds=limit_stale_after_seconds,
        limit_future_tolerance_seconds=limit_future_tolerance_seconds,
    )
    server = ThreadingHTTPServer((host, port), make_request_handler(api))
    print(f"agentic local api serving on http://{host}:{port}", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def _default_inbox_project_source(inbox_root: Path) -> InboxProjectSource:
    return InboxProjectSource(
        project_id="",
        project_name="",
        jira_project_key="",
        repository="",
        inbox_root=inbox_root,
    )


def _load_operator_inbox_projects(data_root: Path, default_inbox_root: Path) -> tuple[InboxProjectSource, ...]:
    config_path = data_root / "operator-projects.json"
    if not config_path.is_file():
        return (_default_inbox_project_source(default_inbox_root),)

    with config_path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    raw_projects = data.get("projects", []) if isinstance(data, Mapping) else []
    if not isinstance(raw_projects, list):
        raise ValueError("operator-projects.json field 'projects' must be a list.")

    projects: list[InboxProjectSource] = []
    for index, raw_project in enumerate(raw_projects):
        if not isinstance(raw_project, Mapping):
            raise ValueError(f"operator-projects.json projects[{index}] must be an object.")
        inbox_root = _project_inbox_root(data_root, _optional_text(raw_project.get("inbox_root")))
        projects.append(
            InboxProjectSource(
                project_id=_optional_text(raw_project.get("project_id")),
                project_name=_optional_text(raw_project.get("project_name")),
                jira_project_key=_optional_text(raw_project.get("jira_project_key")),
                repository=_optional_text(raw_project.get("repository")),
                inbox_root=inbox_root,
            )
        )
    return tuple(projects) if projects else (_default_inbox_project_source(default_inbox_root),)


def _project_inbox_root(data_root: Path, value: str) -> Path:
    if not value:
        raise ValueError("operator-projects.json project entries require inbox_root.")
    path = Path(value)
    return path if path.is_absolute() else data_root / path


def _project_public_body(source: InboxProjectSource) -> dict[str, str]:
    return {
        "project_id": source.project_id,
        "project_name": source.project_name,
        "jira_project_key": source.jira_project_key,
        "repository": source.repository,
    }


def _project_error_body(source: InboxProjectSource) -> dict[str, str]:
    return {
        **_project_public_body(source),
        "message": "Project inbox could not be loaded safely.",
    }


def _inbox_item_api_body(item: POInboxItem, source: InboxProjectSource) -> dict[str, Any]:
    data = inbox_item_to_dict(item)
    project_id = item.project_id or source.project_id
    project_name = item.project_name or source.project_name
    jira_project_key = item.jira_project_key or source.jira_project_key
    repository = item.repository or source.repository
    source_key = source.source_key
    data.update(
        {
            "project_id": project_id,
            "project_name": project_name,
            "jira_project_key": jira_project_key,
            "repository": repository,
            "project_identity": _project_identity_label(
                project_id=project_id,
                project_name=project_name,
                jira_project_key=jira_project_key,
            ),
            "source_project_id": source_key,
            "source_item_id": item.id,
            "composite_id": f"{source_key}::{item.id}",
            "project_root": _safe_browser_path(data.get("project_root", "")),
            "context_pack_path": _safe_browser_path(data.get("context_pack_path", "")),
        }
    )
    return data


def _project_identity_label(*, project_id: str, project_name: str, jira_project_key: str) -> str:
    if project_name and jira_project_key:
        return f"{project_name} ({jira_project_key})"
    return project_name or jira_project_key or project_id


def _matches_inbox_filters(
    item: POInboxItem,
    *,
    agent_role: str,
    message_type: str,
    jira_issue_key: str,
) -> bool:
    if agent_role and item.agent_role.value != agent_role:
        return False
    if message_type and item.message_type.value != message_type:
        return False
    if jira_issue_key and item.jira_issue_key != jira_issue_key:
        return False
    return True


def _export_filter_body(*, status: InboxStatus | None, query: Mapping[str, str]) -> dict[str, str]:
    return {
        "status": status.value if status else "all",
        "project_id": query.get("project_id", "") or "all",
        "agent_role": query.get("agent_role", "") or "all",
        "message_type": query.get("message_type", "") or "all",
        "jira_issue_key": query.get("jira_issue_key", ""),
    }


def _item_from_create_body(body: Mapping[str, Any]) -> POInboxItem:
    timestamp = _utc_now()
    agent_role = _optional_text(body.get("agent_role"), AgentRole.PLATFORM.value)
    agent_id = _optional_text(body.get("agent_id"))
    return POInboxItem(
        id=_required_text(body, "id"),
        message_type=InboxMessageType(_required_text(body, "message_type")),
        status=InboxStatus.OPEN,
        title=_required_text(body, "title"),
        message=_required_text(body, "message"),
        agent_role=AgentRole(agent_role),
        created_at=timestamp,
        agent_id=agent_id,
        jira_issue_key=_optional_text(body.get("jira_issue_key")),
        project_id=_optional_text(body.get("project_id")),
        project_name=_optional_text(body.get("project_name")),
        project_root=_optional_text(body.get("project_root")),
        repository=_optional_text(body.get("repository")),
        jira_project_key=_optional_text(body.get("jira_project_key")),
        confluence_page_id=_optional_text(body.get("confluence_page_id")),
        context_pack_path=_optional_text(body.get("context_pack_path")),
        business_impact=_optional_text(body.get("business_impact")),
        recommendation=_optional_text(body.get("recommendation")),
        audit=(
            InboxAuditEvent(
                timestamp=timestamp,
                actor=agent_id or agent_role,
                action="created",
                note="Created by local PO inbox API.",
            ),
        ),
    )


def _location_body(location: Any) -> dict[str, str]:
    return {
        "item_id": location.item_id,
        "status": location.status.value,
        "path": _safe_browser_path(str(location.path)),
    }


def _safe_browser_path(value: str) -> str:
    if not value:
        return ""
    path = Path(value)
    if path.is_absolute() or value.startswith("\\\\") or value[1:3] == ":\\":
        return "[redacted]"
    return value


def _operator_status_body(
    data_root: Path,
    *,
    account_scope_id: str = "",
    bucket_id: str = "",
    stale_after_seconds: int | None = None,
    future_tolerance_seconds: int = 30,
) -> dict[str, Any]:
    assignment_store = FileAgentAssignmentStore(data_root / "agent-state")
    limit_store = FileCodexLimitAvailabilityStore(data_root / "codex-limits")
    durable_assignments = assignment_store.list_assignments()
    workers = [_worker_status_summary(worker) for worker in assignment_store.list_workers()]
    assignments = [_assignment_status_summary(assignment) for assignment in durable_assignments]
    latest_limit = limit_store.latest_record(
        account_scope_id=account_scope_id,
        bucket_id=bucket_id,
    )
    limit_gate = decide_codex_limit_gate(
        latest_limit,
        now=_utc_now(),
        stale_after_seconds=stale_after_seconds,
        future_tolerance_seconds=future_tolerance_seconds,
    )
    return _redact_values(
        {
            "workers": workers,
            "assignments": assignments,
            "stack_lanes": _stack_lane_status_summaries(durable_assignments),
            "codex_limit": codex_limit_availability_record_to_dict(latest_limit) if latest_limit else None,
            "codex_limit_gate": {
                "allowed": limit_gate.allowed,
                "action": limit_gate.action.value,
                "reason": limit_gate.reason,
                "resume_after": limit_gate.resume_after,
            },
            "codex_limit_windows": _limit_window_summaries(latest_limit),
            "recent_logs": _recent_log_entries(data_root / "agent-logs"),
        }
    )


def _operator_rescue_body(
    data_root: Path,
    *,
    query: Mapping[str, str],
    account_scope_id: str = "",
    bucket_id: str = "",
    stale_after_seconds: int | None = None,
    future_tolerance_seconds: int = 30,
) -> dict[str, Any]:
    assignment_store = FileAgentAssignmentStore(data_root / "agent-state")
    project_id = query.get("project_id", "")
    assignments = assignment_store.list_assignments(project_id=project_id)
    latest_limit = _latest_codex_limit_record(
        data_root,
        account_scope_id=account_scope_id,
        bucket_id=bucket_id,
    )
    limit_gate = decide_codex_limit_gate(
        latest_limit,
        now=_utc_now(),
        stale_after_seconds=stale_after_seconds,
        future_tolerance_seconds=future_tolerance_seconds,
    )
    return _redact_values(
        {
            "items": [
                _operator_rescue_assignment_decision_body(
                    assignment,
                    assignments=assignments,
                    limit_gate=limit_gate,
                    generated_at=_utc_now(),
                )
                for assignment in sorted(assignments, key=lambda item: (item.updated_at, item.id), reverse=True)
            ],
            "filters": {
                "project_id": project_id or "all",
            },
            "stale_lock_minutes": OPERATOR_RESCUE_STALE_LOCK_MINUTES,
            "codex_limit_gate": {
                "allowed": limit_gate.allowed,
                "action": limit_gate.action.value,
                "reason": limit_gate.reason,
                "resume_after": limit_gate.resume_after,
            },
        }
    )


def _operator_rescue_assignment_body(
    data_root: Path,
    assignment_id: str,
    *,
    query: Mapping[str, str],
    account_scope_id: str = "",
    bucket_id: str = "",
    stale_after_seconds: int | None = None,
    future_tolerance_seconds: int = 30,
) -> dict[str, Any]:
    assignment_store = FileAgentAssignmentStore(data_root / "agent-state")
    assignment = assignment_store.read_assignment(assignment_id)
    assignments = assignment_store.list_assignments(project_id=query.get("project_id", ""))
    latest_limit = _latest_codex_limit_record(
        data_root,
        account_scope_id=account_scope_id,
        bucket_id=bucket_id,
    )
    limit_gate = decide_codex_limit_gate(
        latest_limit,
        now=_utc_now(),
        stale_after_seconds=stale_after_seconds,
        future_tolerance_seconds=future_tolerance_seconds,
    )
    return _redact_values(
        _operator_rescue_assignment_decision_body(
            assignment,
            assignments=assignments,
            limit_gate=limit_gate,
            generated_at=_utc_now(),
        )
    )


def _apply_operator_rescue_action_response(
    data_root: Path,
    assignment_id: str,
    action: str,
    body: Mapping[str, Any],
    *,
    account_scope_id: str = "",
    bucket_id: str = "",
    stale_after_seconds: int | None = None,
    future_tolerance_seconds: int = 30,
) -> APIResponse:
    if action not in OPERATOR_RESCUE_ACTIONS:
        return _error_response(404, "not_found", f"Unknown operator rescue action: {action}.")

    timestamp = _utc_now()
    assignment_store = FileAgentAssignmentStore(data_root / "agent-state")
    assignments = assignment_store.list_assignments()
    assignment = assignment_store.read_assignment(assignment_id)
    latest_limit = _latest_codex_limit_record(
        data_root,
        account_scope_id=account_scope_id,
        bucket_id=bucket_id,
    )
    limit_gate = decide_codex_limit_gate(
        latest_limit,
        now=timestamp,
        stale_after_seconds=stale_after_seconds,
        future_tolerance_seconds=future_tolerance_seconds,
    )
    decision = _operator_rescue_action_decision(
        assignment,
        action=action,
        assignments=assignments,
        limit_gate=limit_gate,
        generated_at=timestamp,
    )
    if not decision.allowed:
        return APIResponse(
            status_code=409,
            body=_redact_values(
                {
                    "assignment": _assignment_status_summary(assignment),
                    "decision": _operator_rescue_decision_body(decision),
                    "audit_written": False,
                    "message_written": False,
                }
            ),
        )

    actor = _optional_text(body.get("actor"), "operator")
    reason = _optional_text(body.get("reason"), decision.reason)
    updated_assignment = _assignment_after_rescue_action(assignment, action=action, updated_at=timestamp)
    if updated_assignment != assignment:
        assignment_store.save_assignment(updated_assignment)

    audit_path = _write_operator_rescue_audit(
        data_root,
        assignment=assignment,
        updated_assignment=updated_assignment,
        action=action,
        actor=actor,
        reason=reason,
        decision=decision,
        timestamp=timestamp,
    )
    message_location = _publish_operator_rescue_message(
        data_root,
        assignment=updated_assignment,
        action=action,
        actor=actor,
        reason=reason,
        decision=decision,
        audit_path=audit_path,
        timestamp=timestamp,
    )

    return APIResponse(
        status_code=200,
        body=_redact_values(
            {
                "assignment": _assignment_status_summary(updated_assignment),
                "previous_status": assignment.status.value,
                "decision": _operator_rescue_decision_body(decision),
                "audit_written": True,
                "audit_ref": _safe_platform_relative_path(audit_path, data_root),
                "message_written": True,
                "message_id": message_location.id,
                "message_created": message_location.created,
                "duplicate_of": message_location.duplicate_of,
            }
        ),
    )


def _operator_rescue_assignment_decision_body(
    assignment: AgentAssignment,
    *,
    assignments: tuple[AgentAssignment, ...],
    limit_gate: Any,
    generated_at: str,
) -> dict[str, Any]:
    return {
        "assignment": _assignment_status_summary(assignment),
        "actions": [
            _operator_rescue_decision_body(
                _operator_rescue_action_decision(
                    assignment,
                    action=action,
                    assignments=assignments,
                    limit_gate=limit_gate,
                    generated_at=generated_at,
                )
            )
            for action in OPERATOR_RESCUE_ACTIONS
        ],
    }


def _operator_rescue_decision_body(decision: OperatorRescueDecision) -> dict[str, Any]:
    return {
        "action": decision.action,
        "allowed": decision.allowed,
        "reason": _redact_secret_text(decision.reason),
        "blockers": [_redact_secret_text(blocker) for blocker in decision.blockers],
        "effect": decision.effect,
    }


def _operator_rescue_action_decision(
    assignment: AgentAssignment,
    *,
    action: str,
    assignments: tuple[AgentAssignment, ...],
    limit_gate: Any,
    generated_at: str,
) -> OperatorRescueDecision:
    blockers: list[str] = []
    status = assignment.status

    if action in OPERATOR_RESCUE_LIMIT_ACTIONS and not limit_gate.allowed:
        blockers.append(f"Codex limit gate is closed: {limit_gate.reason}")

    if action in {"resume", "retry", "requeue"} and _has_duplicate_active_assignment(assignment, assignments):
        blockers.append("Another active assignment already exists for this Jira issue and role.")

    if action == "pause":
        if status not in {AssignmentStatus.QUEUED, AssignmentStatus.ASSIGNED, AssignmentStatus.IN_PROGRESS}:
            blockers.append("Only queued, assigned, or in-progress assignments can receive a pause request.")
        return _operator_rescue_decision(
            action=action,
            blockers=blockers,
            allowed_reason="Pause request will be sent to the current worker or role queue.",
            effect="Writes an operator pause audit event and status_update message. Assignment status is unchanged.",
        )

    if action == "resume":
        if status not in {AssignmentStatus.PAUSED_LIMIT, AssignmentStatus.PAUSED_PO}:
            blockers.append("Only limit-paused or PO-paused assignments can be resumed.")
        return _operator_rescue_decision(
            action=action,
            blockers=blockers,
            allowed_reason="Assignment will be requeued after all resume gates pass.",
            effect="Moves assignment to queued, clears pause fields, writes audit, and sends a resume_request.",
        )

    if action == "retry":
        if status is not AssignmentStatus.FAILED:
            blockers.append("Only failed assignments can be retried.")
        return _operator_rescue_decision(
            action=action,
            blockers=blockers,
            allowed_reason="Failed assignment will be requeued for a new attempt.",
            effect="Moves failed assignment to queued, increments attempt count, writes audit, and sends a resume_request.",
        )

    if action == "requeue":
        if status not in {
            AssignmentStatus.PAUSED_LIMIT,
            AssignmentStatus.PAUSED_PO,
            AssignmentStatus.FAILED,
            AssignmentStatus.CANCELLED,
        }:
            blockers.append("Only paused, failed, or cancelled assignments can be requeued.")
        return _operator_rescue_decision(
            action=action,
            blockers=blockers,
            allowed_reason="Assignment will be placed back in the queue.",
            effect="Moves assignment to queued, increments attempt count, writes audit, and sends a resume_request.",
        )

    if action == "cancel":
        if status in {AssignmentStatus.COMPLETED, AssignmentStatus.CANCELLED}:
            blockers.append("Completed or already cancelled assignments cannot be cancelled.")
        return _operator_rescue_decision(
            action=action,
            blockers=blockers,
            allowed_reason="Assignment will be cancelled by operator request.",
            effect="Moves assignment to cancelled, writes audit, and sends a status_update message.",
        )

    if action == "clear-stale-lock":
        if not (assignment.worker_id or assignment.codex_job_id):
            blockers.append("Assignment does not carry a worker or Codex job lock.")
        if status is AssignmentStatus.COMPLETED:
            blockers.append("Completed assignments keep their Codex job id for traceability.")
        if status not in TERMINAL_ASSIGNMENT_STATUSES and not _assignment_is_stale(assignment, generated_at):
            blockers.append(
                f"Assignment updated less than {OPERATOR_RESCUE_STALE_LOCK_MINUTES} minutes ago; lock is not stale."
            )
        if _has_duplicate_active_assignment(assignment, assignments):
            blockers.append("Another active assignment already exists for this Jira issue and role.")
        return _operator_rescue_decision(
            action=action,
            blockers=blockers,
            allowed_reason="Stale worker lock will be cleared safely.",
            effect="Clears worker/job lock. Non-terminal assignments are requeued and a resume_request is sent.",
        )

    if action == "refresh-diagnostics":
        return OperatorRescueDecision(
            action=action,
            allowed=True,
            reason="Diagnostic refresh can always be requested.",
            blockers=(),
            effect="Writes audit and status_update message without changing assignment status.",
        )

    return OperatorRescueDecision(
        action=action,
        allowed=False,
        reason="Unknown rescue action.",
        blockers=("Unknown rescue action.",),
        effect="No change.",
    )


def _operator_rescue_decision(
    *,
    action: str,
    blockers: list[str],
    allowed_reason: str,
    effect: str,
) -> OperatorRescueDecision:
    return OperatorRescueDecision(
        action=action,
        allowed=not blockers,
        reason=allowed_reason if not blockers else "Operator rescue action is blocked.",
        blockers=tuple(blockers),
        effect=effect,
    )


def _assignment_after_rescue_action(
    assignment: AgentAssignment,
    *,
    action: str,
    updated_at: str,
) -> AgentAssignment:
    if action in {"pause", "refresh-diagnostics"}:
        return assignment
    if action == "cancel":
        return replace(
            assignment,
            status=AssignmentStatus.CANCELLED,
            worker_id="",
            codex_job_id="",
            pause_reason="",
            po_inbox_item_id="",
            failure_reason="",
            completed_at="",
            updated_at=updated_at,
        )
    if action == "clear-stale-lock" and assignment.status in TERMINAL_ASSIGNMENT_STATUSES:
        return replace(
            assignment,
            worker_id="",
            codex_job_id="" if assignment.status is not AssignmentStatus.COMPLETED else assignment.codex_job_id,
            updated_at=updated_at,
        )
    return replace(
        assignment,
        status=AssignmentStatus.QUEUED,
        worker_id="",
        codex_job_id="",
        pause_reason="",
        po_inbox_item_id="",
        failure_reason="",
        completed_at="",
        attempt_count=assignment.attempt_count + (1 if action in {"retry", "requeue"} else 0),
        updated_at=updated_at,
    )


def _write_operator_rescue_audit(
    data_root: Path,
    *,
    assignment: AgentAssignment,
    updated_assignment: AgentAssignment,
    action: str,
    actor: str,
    reason: str,
    decision: OperatorRescueDecision,
    timestamp: str,
) -> Path:
    audit_root = data_root / "agent-state" / "operator-rescue-audit"
    audit_root.mkdir(parents=True, exist_ok=True)
    audit_path = audit_root / f"{_safe_file_key(timestamp)}-{_safe_file_key(assignment.id)}-{action}.json"
    payload = _redact_values(
        {
            "schema_version": "operator-rescue-audit/v1",
            "created_at": timestamp,
            "actor": actor,
            "action": action,
            "assignment_id": assignment.id,
            "jira_issue_key": assignment.jira_issue_key,
            "project_id": assignment.project_id,
            "role": assignment.role.value,
            "before_status": assignment.status.value,
            "after_status": updated_assignment.status.value,
            "reason": reason,
            "decision": _operator_rescue_decision_body(decision),
        }
    )
    temp_path = audit_path.with_name(f".{audit_path.name}.tmp")
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp_path.replace(audit_path)
    return audit_path


def _publish_operator_rescue_message(
    data_root: Path,
    *,
    assignment: AgentAssignment,
    action: str,
    actor: str,
    reason: str,
    decision: OperatorRescueDecision,
    audit_path: Path,
    timestamp: str,
) -> Any:
    message_type = (
        AgentMessageType.RESUME_REQUEST
        if action in {"resume", "retry", "requeue", "clear-stale-lock"}
        else AgentMessageType.STATUS_UPDATE
    )
    project_id = assignment.project_id or assignment.jira_project_key or assignment.jira_issue_key.split("-")[0]
    target_channel = AgentCommunicationChannel.ASSIGNMENT if assignment.id else AgentCommunicationChannel.ROLE
    correlation_id = f"operator-rescue:{action}:{timestamp}"
    message = build_agent_message(
        message_id=_safe_file_key(f"operator-rescue-{assignment.id}-{action}-{timestamp}"),
        message_type=message_type,
        idempotency_key=agent_message_idempotency_key(
            message_type=message_type,
            project_id=project_id,
            jira_issue_key=assignment.jira_issue_key,
            assignment_id=assignment.id,
            target_role=assignment.role,
            target_channel=target_channel,
            correlation_id=correlation_id,
            causation_id=assignment.id,
        ),
        source_role=AgentRole.SCHEDULER,
        target_role=assignment.role,
        target_channel=target_channel,
        origin_actor=actor or "operator",
        created_at=timestamp,
        project_id=project_id,
        project_name=assignment.project_name,
        repository=assignment.repository,
        jira_project_key=assignment.jira_project_key,
        jira_issue_key=assignment.jira_issue_key,
        assignment_id=assignment.id,
        priority=AgentMessagePriority.HIGH if message_type is AgentMessageType.RESUME_REQUEST else AgentMessagePriority.NORMAL,
        correlation_id=correlation_id,
        causation_id=assignment.id,
        payload={
            "operator_action": action,
            "reason": reason,
            "gate": {
                "allowed": decision.allowed,
                "reason": decision.reason,
                "blockers": list(decision.blockers),
            },
            "effect": decision.effect,
        },
        artifact_refs=(_safe_platform_relative_path(audit_path, data_root),),
        requires_acknowledgement=message_type is AgentMessageType.RESUME_REQUEST,
    )
    return FileAgentCommunicationStore(data_root / "agent-state").publish_message(message)


def _has_duplicate_active_assignment(
    assignment: AgentAssignment,
    assignments: tuple[AgentAssignment, ...],
) -> bool:
    for other in assignments:
        if other.id == assignment.id or other.status not in OPERATOR_RESCUE_ACTIVE_STATUSES:
            continue
        if other.role is not assignment.role:
            continue
        if other.jira_issue_key.upper() != assignment.jira_issue_key.upper():
            continue
        if assignment.project_id and other.project_id and assignment.project_id != other.project_id:
            continue
        return True
    return False


def _assignment_is_stale(assignment: AgentAssignment, generated_at: str) -> bool:
    updated_at = _parse_utc_datetime(assignment.updated_at)
    now = _parse_utc_datetime(generated_at)
    if updated_at is None or now is None:
        return False
    age_seconds = (now - updated_at).total_seconds()
    return age_seconds >= OPERATOR_RESCUE_STALE_LOCK_MINUTES * 60


def _parse_utc_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _latest_codex_limit_record(
    data_root: Path,
    *,
    account_scope_id: str = "",
    bucket_id: str = "",
) -> Any:
    return FileCodexLimitAvailabilityStore(data_root / "codex-limits").latest_record(
        account_scope_id=account_scope_id,
        bucket_id=bucket_id,
    )


def _safe_platform_relative_path(path: Path, data_root: Path) -> str:
    try:
        return path.relative_to(data_root).as_posix()
    except ValueError:
        return _safe_browser_path(str(path))


def _safe_file_key(value: str) -> str:
    safe = "".join(character if character.isalnum() or character in {"-", "_", "."} else "-" for character in value)
    return safe.strip("-") or "operator-rescue"


def _agent_messages_body(data_root: Path, *, query: Mapping[str, str]) -> dict[str, Any]:
    store = FileAgentCommunicationStore(data_root / "agent-state")
    status = AgentMessageStatus(query["status"]) if query.get("status") else None
    message_type = AgentMessageType(query["message_type"]) if query.get("message_type") else None
    target_channel = AgentCommunicationChannel(query["target_channel"]) if query.get("target_channel") else None
    messages = store.list_messages(
        status=status,
        project_id=query.get("project_id", ""),
        jira_issue_key=query.get("jira_issue_key", ""),
        assignment_id=query.get("assignment_id", ""),
        target_channel=target_channel,
        message_type=message_type,
    )
    role_filter = query.get("role", "")
    if role_filter:
        messages = tuple(
            message
            for message in messages
            if message.source_role.value == role_filter
            or (message.target_role is not None and message.target_role.value == role_filter)
        )
    messages = tuple(sorted(messages, key=lambda message: (message.created_at, message.id), reverse=True))
    assignments = FileAgentAssignmentStore(data_root / "agent-state").list_assignments(
        project_id=query.get("project_id", "")
    )
    return _redact_values(
        {
            "items": [_agent_message_api_body(message) for message in messages],
            "graph": _agent_message_graph(messages, assignments),
            "filters": {
                "project_id": query.get("project_id", "") or "all",
                "jira_issue_key": query.get("jira_issue_key", ""),
                "assignment_id": query.get("assignment_id", ""),
                "role": role_filter or "all",
                "message_type": query.get("message_type", "") or "all",
                "status": query.get("status", "") or "all",
                "target_channel": query.get("target_channel", "") or "all",
            },
        }
    )


def _agent_message_read_body(data_root: Path, message_id: str) -> dict[str, Any]:
    message = FileAgentCommunicationStore(data_root / "agent-state").read_message(message_id)
    return _redact_values({"item": _agent_message_api_body(message)})


def _create_agent_message_response(data_root: Path, body: Mapping[str, Any]) -> APIResponse:
    message = _agent_message_from_create_body(body, created_at=_utc_now())
    location = FileAgentCommunicationStore(data_root / "agent-state").publish_message(message)
    stored = FileAgentCommunicationStore(data_root / "agent-state").read_message(location.id)
    return APIResponse(
        status_code=201 if location.created else 200,
        body=_redact_values(
            {
                "item": _agent_message_api_body(stored),
                "created": location.created,
                "duplicate_of": location.duplicate_of,
                "location": {"message_id": location.id, "path": _safe_browser_path(str(location.path))},
            }
        ),
    )


def _respond_to_agent_message_response(data_root: Path, message_id: str, body: Mapping[str, Any]) -> APIResponse:
    store = FileAgentCommunicationStore(data_root / "agent-state")
    source = store.read_message(message_id)
    timestamp = _utc_now()
    response_message = _agent_response_message_from_body(source, body, created_at=timestamp)
    location = store.publish_message(response_message)
    stored = store.read_message(location.id)
    return APIResponse(
        status_code=201 if location.created else 200,
        body=_redact_values(
            {
                "item": _agent_message_api_body(stored),
                "created": location.created,
                "duplicate_of": location.duplicate_of,
                "location": {"message_id": location.id, "path": _safe_browser_path(str(location.path))},
            }
        ),
    )


def _agent_message_api_body(message: AgentMessage) -> dict[str, Any]:
    data = agent_message_to_dict(message)
    data["project_root"] = _safe_browser_path(data.get("project_root", ""))
    data["display_lane"] = _agent_message_lane(message)
    data["project_identity"] = _project_identity_label(
        project_id=message.project_id,
        project_name=message.project_name,
        jira_project_key=message.jira_project_key,
    )
    data["resume_gate"] = _resume_gate_summary(message)
    data["linked_refs"] = _agent_message_linked_refs(message)
    return data


def _agent_message_from_create_body(body: Mapping[str, Any], *, created_at: str) -> AgentMessage:
    message_type = AgentMessageType(_required_text(body, "message_type"))
    target_role = AgentRole(_optional_text(body.get("target_role"))) if body.get("target_role") else None
    target_channel = (
        AgentCommunicationChannel(_optional_text(body.get("target_channel")))
        if body.get("target_channel")
        else AgentCommunicationChannel.PRODUCT_OWNER_OUTBOX
    )
    project_id = _required_text(body, "project_id")
    jira_issue_key = _optional_text(body.get("jira_issue_key"))
    assignment_id = _optional_text(body.get("assignment_id"))
    correlation_id = _optional_text(body.get("correlation_id"))
    causation_id = _optional_text(body.get("causation_id"))
    message_id = _optional_text(
        body.get("id"),
        _generated_agent_message_id("po", project_id=project_id, message_type=message_type, created_at=created_at),
    )
    payload = _po_message_payload_from_body(body)
    idempotency_key = _optional_text(
        body.get("idempotency_key"),
        agent_message_idempotency_key(
            message_type=message_type,
            project_id=project_id,
            jira_issue_key=jira_issue_key,
            assignment_id=assignment_id,
            target_role=target_role,
            target_channel=target_channel,
            correlation_id=correlation_id,
            causation_id=causation_id,
        ),
    )
    return build_agent_message(
        message_id=message_id,
        message_type=message_type,
        idempotency_key=idempotency_key,
        source_role=AgentRole(_optional_text(body.get("source_role"), AgentRole.PLATFORM.value)),
        target_role=target_role,
        target_channel=target_channel,
        target_worker_id=_optional_text(body.get("target_worker_id")),
        origin_actor="product_owner",
        created_at=created_at,
        project_id=project_id,
        project_name=_optional_text(body.get("project_name")),
        repository=_optional_text(body.get("repository")),
        jira_project_key=_optional_text(body.get("jira_project_key")),
        sprint_id=_optional_text(body.get("sprint_id")),
        sprint_name=_optional_text(body.get("sprint_name")),
        jira_issue_key=jira_issue_key,
        assignment_id=assignment_id,
        priority=AgentMessagePriority(_optional_text(body.get("priority"), AgentMessagePriority.NORMAL.value)),
        correlation_id=correlation_id,
        causation_id=causation_id,
        payload=payload,
        artifact_refs=tuple(_optional_string_list(body.get("artifact_refs"))),
        requires_acknowledgement=_optional_bool(body.get("requires_acknowledgement"), default=True),
        expires_at=_optional_text(body.get("expires_at")),
    )


def _agent_response_message_from_body(source: AgentMessage, body: Mapping[str, Any], *, created_at: str) -> AgentMessage:
    response_id = _optional_text(
        body.get("id"),
        _generated_agent_message_id("response", project_id=source.project_id, message_type=AgentMessageType.AGENT_RESPONSE_TO_PO, created_at=created_at),
    )
    source_role = AgentRole(_optional_text(body.get("source_role"), source.target_role.value if source.target_role else AgentRole.PLATFORM.value))
    idempotency_key = _optional_text(
        body.get("idempotency_key"),
        agent_message_idempotency_key(
            message_type=AgentMessageType.AGENT_RESPONSE_TO_PO,
            project_id=source.project_id,
            jira_issue_key=source.jira_issue_key,
            assignment_id=source.assignment_id,
            target_channel=AgentCommunicationChannel.PRODUCT_OWNER_OUTBOX,
            correlation_id=source.correlation_id or source.id,
            causation_id=source.id,
        ),
    )
    return build_agent_message(
        message_id=response_id,
        message_type=AgentMessageType.AGENT_RESPONSE_TO_PO,
        idempotency_key=idempotency_key,
        source_role=source_role,
        target_channel=AgentCommunicationChannel.PRODUCT_OWNER_OUTBOX,
        origin_actor="worker",
        created_at=created_at,
        project_id=source.project_id,
        project_name=source.project_name,
        repository=source.repository,
        jira_project_key=source.jira_project_key,
        sprint_id=source.sprint_id,
        sprint_name=source.sprint_name,
        jira_issue_key=source.jira_issue_key,
        assignment_id=source.assignment_id,
        priority=AgentMessagePriority(_optional_text(body.get("priority"), AgentMessagePriority.NORMAL.value)),
        correlation_id=source.correlation_id or source.id,
        causation_id=source.id,
        payload=_po_message_payload_from_body(body),
        artifact_refs=tuple(_optional_string_list(body.get("artifact_refs"))),
        requires_acknowledgement=False,
    )


def _po_message_payload_from_body(body: Mapping[str, Any]) -> dict[str, Any]:
    payload = body.get("payload")
    if payload is not None:
        if not isinstance(payload, Mapping):
            raise ValueError("Agent message payload must be an object.")
        safe_payload = dict(payload)
    else:
        safe_payload = {}
    subject = _optional_text(body.get("subject"))
    message = _optional_text(body.get("body") or body.get("message"))
    if subject:
        safe_payload["subject"] = subject
    if message:
        safe_payload["body"] = message
    if "response_requested" in body:
        safe_payload["response_requested"] = _optional_bool(body.get("response_requested"), default=False)
    references = _optional_string_list(body.get("references"))
    if references:
        safe_payload["references"] = references
    if not safe_payload.get("subject") and not safe_payload.get("body"):
        raise ValueError("Agent message requires subject or body text.")
    return _redact_values(safe_payload)


def _generated_agent_message_id(prefix: str, *, project_id: str, message_type: AgentMessageType, created_at: str) -> str:
    raw = f"{prefix}-{project_id}-{message_type.value}-{created_at}"
    return "".join(character if character.isalnum() or character in {"-", "_", "."} else "-" for character in raw).strip("-")


def _agent_message_lane(message: AgentMessage) -> str:
    if message.message_type is AgentMessageType.PO_REQUIRED:
        return "po_inbox_question"
    if message.origin_actor.casefold() in {"po", "product_owner"}:
        return "product_owner"
    if message.target_channel is AgentCommunicationChannel.PRODUCT_OWNER_OUTBOX:
        return "product_owner"
    return "automated"


def _resume_gate_summary(message: AgentMessage) -> dict[str, Any]:
    if message.message_type is not AgentMessageType.RESUME_REQUEST:
        return {}
    payload = dict(message.payload or {})
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else payload
    return {
        "allowed": bool(gate.get("allowed")) if "allowed" in gate else None,
        "reason": _redact_secret_text(str(gate.get("reason") or "")),
        "blockers": [str(blocker) for blocker in gate.get("blockers", [])] if isinstance(gate.get("blockers"), list) else [],
    }


def _agent_message_linked_refs(message: AgentMessage) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    for kind, value in (
        ("jira_issue", message.jira_issue_key),
        ("assignment", message.assignment_id),
        ("repository", message.repository),
    ):
        if value:
            refs.append({"kind": kind, "value": _safe_browser_path(_redact_secret_text(value))})
    for artifact in message.artifact_refs:
        refs.append({"kind": "artifact", "value": _safe_browser_path(_redact_secret_text(artifact))})
    return refs


def _agent_message_graph(messages: tuple[AgentMessage, ...], assignments: tuple[Any, ...]) -> dict[str, list[dict[str, str]]]:
    nodes: dict[str, dict[str, str]] = {}
    edges: list[dict[str, str]] = []

    def add_node(node_id: str, label: str, kind: str, status: str = "") -> None:
        if node_id and node_id not in nodes:
            nodes[node_id] = {"id": node_id, "label": label or node_id, "kind": kind, "status": status}

    def add_edge(source: str, target: str, label: str) -> None:
        if source and target:
            edges.append({"source": source, "target": target, "label": label})

    for assignment in assignments:
        assignment_node = f"assignment:{assignment.id}"
        add_node(assignment_node, assignment.id, "assignment", assignment.status.value)
        if assignment.project_id:
            project_node = f"project:{assignment.project_id}"
            add_node(project_node, _project_identity_label(
                project_id=assignment.project_id,
                project_name=assignment.project_name,
                jira_project_key=assignment.jira_project_key,
            ), "project")
            add_edge(project_node, assignment_node, "has assignment")
        if assignment.jira_issue_key:
            issue_node = f"issue:{assignment.jira_issue_key.upper()}"
            add_node(issue_node, assignment.jira_issue_key.upper(), "jira_issue")
            add_edge(assignment_node, issue_node, "works on")

    for message in messages:
        message_node = f"message:{message.id}"
        add_node(message_node, message.id, "message", message.status.value)
        source_node = f"role:{message.source_role.value}"
        add_node(source_node, message.source_role.value, "role")
        add_edge(source_node, message_node, message.message_type.value)
        if message.target_role:
            target_node = f"role:{message.target_role.value}"
            add_node(target_node, message.target_role.value, "role")
            add_edge(message_node, target_node, "targets")
        elif message.target_channel:
            target_node = f"channel:{message.target_channel.value}"
            add_node(target_node, message.target_channel.value, "channel")
            add_edge(message_node, target_node, "targets")
        if message.project_id:
            project_node = f"project:{message.project_id}"
            add_node(
                project_node,
                _project_identity_label(
                    project_id=message.project_id,
                    project_name=message.project_name,
                    jira_project_key=message.jira_project_key,
                ),
                "project",
            )
            add_edge(project_node, message_node, "contains")
        if message.jira_issue_key:
            issue_node = f"issue:{message.jira_issue_key.upper()}"
            add_node(issue_node, message.jira_issue_key.upper(), "jira_issue")
            add_edge(message_node, issue_node, "references")
        if message.assignment_id:
            assignment_node = f"assignment:{message.assignment_id}"
            add_node(assignment_node, message.assignment_id, "assignment")
            add_edge(message_node, assignment_node, "references")

    return {"nodes": list(nodes.values()), "edges": edges}


def _worker_status_summary(worker: Any) -> dict[str, str]:
    return {
        "id": worker.id,
        "role": worker.role.value,
        "status": worker.status.value,
        "display_name": worker.display_name,
        "container_name": worker.container_name,
        "current_assignment_id": worker.current_assignment_id,
        "updated_at": worker.updated_at,
    }


def _assignment_status_summary(assignment: Any) -> dict[str, Any]:
    return {
        "id": assignment.id,
        "jira_issue_key": assignment.jira_issue_key,
        "role": assignment.role.value,
        "status": assignment.status.value,
        "worker_id": assignment.worker_id,
        "codex_job_id": assignment.codex_job_id,
        "branch_name": assignment.branch_name,
        "project_id": assignment.project_id,
        "project_name": assignment.project_name,
        "project_root": _safe_browser_path(assignment.project_root),
        "repository": assignment.repository,
        "jira_project_key": assignment.jira_project_key,
        "updated_at": assignment.updated_at,
        "pause_reason": assignment.pause_reason,
        "failure_reason": assignment.failure_reason,
        "attempt_count": assignment.attempt_count,
        "stack_metadata": _assignment_stack_metadata_summary(assignment),
        "artifact_refs": _assignment_artifact_refs(assignment),
        "story_lifecycle": _assignment_lifecycle_summary(assignment),
    }


def _assignment_stack_metadata_summary(assignment: Any) -> dict[str, Any]:
    metadata = assignment.stack_metadata
    return {
        "stack_id": metadata.stack_id,
        "lane_id": metadata.lane_id,
        "stack_mode": metadata.stack_mode,
        "resolved_path_version": metadata.resolved_path_version,
        "current_layer": metadata.current_layer,
        "expected_next_agent": metadata.expected_next_agent,
        "stale_state": metadata.stale_state,
        "rebase_required": metadata.rebase_required,
    }


def _stack_lane_status_summaries(assignments: tuple[Any, ...]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[Any]] = {}
    for assignment in assignments:
        metadata = assignment.stack_metadata
        if not metadata.stack_id:
            continue
        lane_id = metadata.lane_id or "default"
        grouped.setdefault((metadata.stack_id, lane_id), []).append(assignment)

    lanes: list[dict[str, Any]] = []
    for (stack_id, lane_id), lane_assignments in sorted(grouped.items()):
        sorted_assignments = sorted(
            lane_assignments,
            key=lambda item: (item.stack_metadata.current_layer, item.jira_issue_key, item.id),
        )
        first_metadata = sorted_assignments[0].stack_metadata
        lanes.append(
            {
                "stack_id": stack_id,
                "lane_id": lane_id,
                "stack_mode": first_metadata.stack_mode,
                "resolved_path_version": first_metadata.resolved_path_version,
                "stories": [_stack_lane_story_summary(assignment) for assignment in sorted_assignments],
            }
        )
    return lanes


def _stack_lane_story_summary(assignment: Any) -> dict[str, Any]:
    metadata = assignment.stack_metadata
    lifecycle = _assignment_lifecycle_summary(assignment)
    return {
        "jira_issue_key": assignment.jira_issue_key,
        "assignment_id": assignment.id,
        "role": assignment.role.value,
        "current_agent": assignment.role.value,
        "current_status": assignment.status.value,
        "layer_order": metadata.current_layer,
        "stack_id": metadata.stack_id,
        "lane_id": metadata.lane_id or "default",
        "stack_mode": metadata.stack_mode,
        "resolved_path_version": metadata.resolved_path_version,
        "branch_name": assignment.branch_name,
        "pull_request_urls": _assignment_pull_request_urls(assignment),
        "next_step": metadata.expected_next_agent or lifecycle["next_expected_step"],
        "blocked_reason": _stack_lane_blocked_reason(assignment, lifecycle),
        "stale_retest_required": bool(metadata.rebase_required or metadata.stale_state),
        "evidence_state": _stack_lane_evidence_state(assignment, lifecycle),
    }


def _assignment_pull_request_urls(assignment: Any) -> list[str]:
    refs = _assignment_artifact_refs(assignment)
    urls: list[str] = []
    for ref in refs:
        value = ref.get("path", "")
        if ref.get("kind") == "pull_request" or value.startswith("https://github.com/"):
            urls.append(value)
    return urls


def _stack_lane_blocked_reason(assignment: Any, lifecycle: Mapping[str, Any]) -> str:
    metadata = assignment.stack_metadata
    if metadata.rebase_required:
        return "Stack layer requires Developer Agent rebase before review, merge, or final testing."
    if metadata.stale_state:
        return f"Stack evidence state is {metadata.stale_state}."
    return str(lifecycle.get("blocked_reason") or "")


def _stack_lane_evidence_state(assignment: Any, lifecycle: Mapping[str, Any]) -> str:
    metadata = assignment.stack_metadata
    if metadata.rebase_required or metadata.stale_state:
        return "stale"
    if lifecycle.get("blocked_reason") or assignment.status in {
        AssignmentStatus.PAUSED_LIMIT,
        AssignmentStatus.PAUSED_PO,
        AssignmentStatus.FAILED,
    }:
        return "blocked"
    if assignment.status is AssignmentStatus.COMPLETED and assignment.paths.evidence_path:
        return "final"
    if assignment.paths.evidence_path:
        return "provisional"
    return "not-recorded"


def _assignment_artifact_refs(assignment: Any) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    for label, value in (
        ("context_pack", assignment.paths.context_pack_path),
        ("codex_job", assignment.paths.codex_job_path),
        ("output", assignment.paths.output_path),
        ("workspace", assignment.paths.workspace_path),
        ("evidence", assignment.paths.evidence_path),
        ("failed_request", assignment.paths.failed_request_path),
        ("po_resume_context", assignment.paths.po_inbox_resume_context_path),
    ):
        if value:
            refs.append({"kind": label, "path": _safe_browser_path(value)})
    if assignment.branch_name:
        refs.append({"kind": "branch", "path": assignment.branch_name})
    if assignment.po_inbox_item_id:
        refs.append({"kind": "po_inbox_item", "path": assignment.po_inbox_item_id})
    return refs


def _assignment_lifecycle_summary(assignment: Any) -> dict[str, Any]:
    route = _lifecycle_route()
    role_value = assignment.role.value
    route_roles = [step["role"] for step in route]
    if role_value not in route_roles:
        return {
            "needs_process_mapping": True,
            "next_expected_step": "Needs process mapping",
            "blocked_reason": "Assignment role is not mapped to the story lifecycle route.",
            "sprint_label": "Sprint not recorded",
            "steps": [
                {
                    "id": "needs_process_mapping",
                    "label": "Needs process mapping",
                    "role": role_value,
                    "state": "blocked/stuck",
                    "artifact_refs": _assignment_artifact_refs(assignment),
                }
            ],
        }

    current_index = route_roles.index(role_value)
    blocked = assignment.status.value in {"paused_limit", "paused_po", "failed"}
    completed = assignment.status.value == "completed"
    cancelled = assignment.status.value == "cancelled"
    steps: list[dict[str, Any]] = []
    for index, step in enumerate(route):
        state = "not started"
        if index < current_index:
            state = "done"
        elif index == current_index:
            if completed:
                state = "done"
            elif cancelled:
                state = "skipped/not applicable"
            elif blocked:
                state = "blocked/stuck"
            else:
                state = "next"
        steps.append(
            {
                **step,
                "state": state,
                "artifact_refs": _assignment_artifact_refs(assignment) if index == current_index else [],
            }
        )

    next_step = _next_lifecycle_step(steps)
    blocked_reason = assignment.failure_reason or assignment.pause_reason
    if assignment.status.value == "paused_limit" and not blocked_reason:
        blocked_reason = "Waiting for limit capacity."
    if assignment.status.value == "paused_po" and not blocked_reason:
        blocked_reason = "Waiting for PO input."
    return {
        "needs_process_mapping": False,
        "next_expected_step": next_step,
        "blocked_reason": _redact_secret_text(blocked_reason),
        "sprint_label": "Sprint not recorded",
        "steps": steps,
    }


def _lifecycle_route() -> list[dict[str, str]]:
    return [
        {"id": "product_planning", "label": "Product Planning", "role": "product_planning"},
        {"id": "architecture", "label": "Architecture", "role": "architecture"},
        {"id": "ui_ux", "label": "UI/UX Design", "role": "ui_ux"},
        {"id": "developer", "label": "Developer", "role": "developer"},
        {"id": "frontend", "label": "Frontend", "role": "frontend"},
        {"id": "review", "label": "Review", "role": "review"},
        {"id": "tester", "label": "Tester", "role": "tester"},
        {"id": "release_manager", "label": "Regression", "role": "release_manager"},
    ]


def _next_lifecycle_step(steps: list[dict[str, Any]]) -> str:
    for step in steps:
        if step["state"] in {"next", "blocked/stuck"}:
            return step["label"]
    for step in steps:
        if step["state"] == "not started":
            return step["label"]
    return "Release acceptance"


def _limit_window_summaries(record: Any) -> list[dict[str, Any]]:
    if record is None:
        return []
    return [
        {
            "label": label,
            "window_id": window.window_id,
            "status": window.status.value,
            "remaining_percent": window.remaining_percent,
            "reset_at": window.reset_at,
            "observation_source": window.observation_source.value,
            "observed_at": window.observed_at,
        }
        for label, window in codex_limit_windows_for_display(record)
    ]


def _codex_limits_body(
    data_root: Path,
    *,
    account_scope_id: str = "",
    bucket_id: str = "",
    stale_after_seconds: int | None = None,
    future_tolerance_seconds: int = 30,
) -> dict[str, Any]:
    limit_store = FileCodexLimitAvailabilityStore(data_root / "codex-limits")
    latest_limit = limit_store.latest_record(
        account_scope_id=account_scope_id,
        bucket_id=bucket_id,
    )
    return _codex_limits_body_from_record(
        latest_limit,
        stale_after_seconds=stale_after_seconds,
        future_tolerance_seconds=future_tolerance_seconds,
    )


def _codex_limits_body_from_record(
    latest_limit: CodexLimitAvailabilityRecord | None,
    *,
    stale_after_seconds: int | None = None,
    future_tolerance_seconds: int = 30,
) -> dict[str, Any]:
    gate = decide_codex_limit_gate(
        latest_limit,
        now=_utc_now(),
        stale_after_seconds=stale_after_seconds,
        future_tolerance_seconds=future_tolerance_seconds,
    )
    return _redact_values(
        {
            "latest_record": codex_limit_availability_record_to_dict(latest_limit) if latest_limit else None,
            "gate": {
                "allowed": gate.allowed,
                "action": gate.action.value,
                "reason": gate.reason,
                "resume_after": gate.resume_after,
            },
            "windows": _limit_window_summaries(latest_limit),
            "generated_at": _utc_now(),
        }
    )


def _codex_limit_record_from_update_body(
    body: Mapping[str, Any],
    *,
    default_account_scope_id: str = "",
    default_bucket_id: str = "",
) -> CodexLimitAvailabilityRecord:
    now = _utc_now()
    record_id = _optional_text(body.get("id"), _limit_record_id(now))
    plan_mode = _codex_limit_plan_mode(body.get("plan_mode"))
    windows = _codex_limit_windows_from_body(
        body,
        observed_at=now,
        default_bucket_id=default_bucket_id,
    )
    note = _redact_secret_text(_optional_text(body.get("note")))
    account_scope_id = _configured_limit_scope_value(
        body.get("account_scope_id"),
        configured_value=default_account_scope_id,
        fallback="default",
        field_name="account_scope_id",
    )

    if plan_mode is CodexLimitPlanMode.SINGLE_POOL:
        if len(windows) != 1:
            raise ValueError("Single-pool limit updates must include exactly one window.")
        return build_single_pool_codex_limit_availability_record(
            record_id=record_id,
            pool=windows[0],
            note=note,
            account_scope_id=account_scope_id,
        )

    if len(windows) < 2:
        raise ValueError("Dual-window limit updates must include short and broad windows.")
    return build_codex_limit_availability_record(
        record_id=record_id,
        short_window=windows[0],
        broad_quota=windows[1],
        plan_mode=plan_mode,
        windows=windows,
        note=note,
        account_scope_id=account_scope_id,
    )


def _codex_limit_windows_from_body(
    body: Mapping[str, Any],
    *,
    observed_at: str,
    default_bucket_id: str = "",
) -> tuple[CodexLimitWindowAvailability, ...]:
    windows_data = body.get("windows")
    if windows_data is None:
        windows_data = [body.get("short_window"), body.get("broad_quota")]
    if not isinstance(windows_data, list):
        raise ValueError("Codex limit update field 'windows' must be a list.")

    windows: list[CodexLimitWindowAvailability] = []
    for index, item in enumerate(windows_data):
        if not isinstance(item, Mapping):
            raise ValueError(f"Codex limit window {index} must be an object.")
        windows.append(
            _codex_limit_window_from_body(
                item,
                index=index,
                observed_at=observed_at,
                default_bucket_id=default_bucket_id,
            )
        )
    if not windows:
        raise ValueError("Codex limit update requires at least one window.")
    return tuple(windows)


def _codex_limit_window_from_body(
    body: Mapping[str, Any],
    *,
    index: int,
    observed_at: str,
    default_bucket_id: str = "",
) -> CodexLimitWindowAvailability:
    status = CodexLimitWindowStatus(_required_text(body, "status"))
    return CodexLimitWindowAvailability(
        status=status,
        remaining_percent=_optional_percent(body.get("remaining_percent"), required=status is not CodexLimitWindowStatus.UNKNOWN),
        reset_at=_optional_text(body.get("reset_at")),
        observation_source=CodexLimitObservationSource.OPERATOR,
        observed_at=observed_at,
        window_id=_optional_text(body.get("window_id"), "agentic_pool" if index == 0 else f"window_{index + 1}"),
        label=_optional_text(body.get("label"), "Current plan" if index == 0 else f"Window {index + 1}"),
        authoritative=_optional_bool(body.get("authoritative"), default=index == 0),
        bucket_id=_configured_limit_scope_value(
            body.get("bucket_id"),
            configured_value=default_bucket_id,
            fallback="",
            field_name="bucket_id",
        ),
        window_name=_optional_text(body.get("window_name")),
        window_duration_minutes=_optional_positive_int(
            body.get("window_duration_minutes"),
            field_name="window_duration_minutes",
        ),
    )


def _configured_limit_scope_value(
    value: Any,
    *,
    configured_value: str,
    fallback: str,
    field_name: str,
) -> str:
    explicit = _optional_text(value)
    configured = _optional_text(configured_value)
    if explicit and configured and explicit != configured:
        raise ValueError(f"{field_name} does not match the Local API configured scope.")
    return configured or explicit or fallback


def _resolve_operator_limit_default_bucket_id(
    store: FileCodexLimitAvailabilityStore,
    body: Mapping[str, Any],
    *,
    account_scope_id: str,
    configured_bucket_id: str,
) -> str:
    configured = _optional_text(configured_bucket_id)
    windows_data = body.get("windows")
    if windows_data is None:
        windows_data = [body.get("short_window"), body.get("broad_quota")]
    has_explicit_bucket = isinstance(windows_data, list) and any(
        isinstance(window, Mapping) and _optional_text(window.get("bucket_id"))
        for window in windows_data
    )
    if configured or has_explicit_bucket:
        return configured

    try:
        return resolve_codex_limit_write_bucket_id(
            store.list_records(),
            account_scope_id=account_scope_id,
        )
    except CodexLimitAvailabilitySelectionError as error:
        raise ValueError(
            "Codex quota bucket is ambiguous; provide bucket_id explicitly or "
            "configure CODEX_LIMIT_BUCKET_ID."
        ) from error


def _write_idempotent_operator_limit_record(
    store: FileCodexLimitAvailabilityStore,
    record: CodexLimitAvailabilityRecord,
) -> CodexLimitAvailabilityRecord:
    try:
        store.write_record(record)
        return record
    except ConflictingCodexLimitAvailabilityRecordError:
        existing = store.read_record(record.id)
    if _operator_limit_record_semantics(existing) == _operator_limit_record_semantics(record):
        return existing
    raise ConflictingCodexLimitAvailabilityRecordError(
        "Operator Codex limit record conflicts with the immutable stored observation."
    )


def _operator_limit_record_semantics(
    record: CodexLimitAvailabilityRecord,
) -> dict[str, Any]:
    windows = record.windows or (record.short_window, record.broad_quota)
    return {
        "id": record.id,
        "account_scope_id": record.account_scope_id,
        "plan_mode": record.plan_mode.value,
        "note": record.note,
        "windows": [
            {
                "status": window.status.value,
                "remaining_percent": window.remaining_percent,
                "reset_at": window.reset_at,
                "observation_source": window.observation_source.value,
                "window_id": window.window_id,
                "label": window.label,
                "authoritative": window.authoritative,
                "bucket_id": window.bucket_id,
                "window_name": window.window_name,
                "window_duration_minutes": window.window_duration_minutes,
            }
            for window in windows
        ],
    }


def _codex_limit_plan_mode(value: Any) -> CodexLimitPlanMode:
    if value is None:
        return CodexLimitPlanMode.DUAL_WINDOW
    return CodexLimitPlanMode(_optional_text(value))


def _optional_percent(value: Any, *, required: bool) -> int | None:
    if value is None or value == "":
        if required:
            raise ValueError("Known Codex limit windows require remaining_percent.")
        return None
    try:
        percent = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("remaining_percent must be an integer from 0 to 100.") from exc
    if percent < 0 or percent > 100:
        raise ValueError("remaining_percent must be an integer from 0 to 100.")
    return percent


def _optional_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    lowered = str(value).strip().casefold()
    if lowered in {"1", "true", "yes"}:
        return True
    if lowered in {"0", "false", "no"}:
        return False
    raise ValueError("Boolean fields must be true or false.")


def _optional_positive_int(value: Any, *, field_name: str) -> int | None:
    if value is None or value == "":
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a positive integer.") from exc
    if parsed <= 0:
        raise ValueError(f"{field_name} must be a positive integer.")
    return parsed


def _optional_string_list(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if not isinstance(value, list):
        raise ValueError("List fields must be arrays of strings.")
    values: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError("List fields must contain only strings.")
        item = item.strip()
        if item:
            values.append(item)
    return values


def _limit_record_id(timestamp: str) -> str:
    safe_timestamp = timestamp.replace("-", "").replace(":", "")
    return f"operator-{safe_timestamp}-{uuid.uuid4().hex[:12]}"


def _recent_log_entries(log_root: Path, *, limit: int = 12) -> list[dict[str, Any]]:
    if not log_root.exists():
        return []
    files = [path for path in log_root.rglob("*") if path.is_file()]
    files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    entries: list[dict[str, Any]] = []
    for path in files[:limit]:
        stat = path.stat()
        entries.append(
            {
                "name": path.name,
                "relative_path": path.relative_to(log_root).as_posix(),
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc)
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z"),
            }
        )
    return entries


def _infer_data_root(inbox_root: Path) -> Path:
    return inbox_root.parent if inbox_root.name in {"po-inbox", "po_inbox"} else inbox_root


def _redact_values(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): "[redacted]" if _is_secret_key(str(key)) else _redact_values(nested)
            for key, nested in value.items()
        }
    if isinstance(value, list):
        return [_redact_values(item) for item in value]
    if isinstance(value, str):
        return _redact_secret_text(value)
    return value


def _is_secret_key(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in ("token", "secret", "password", "credential", "api_key"))


def _redact_secret_text(value: str) -> str:
    redacted = redact_evidence_text(value)
    if redacted != value:
        return "[redacted]"
    lowered = value.lower()
    if any(marker in lowered for marker in ("authorization", "token", "secret", "password", "credential", "api_key")):
        return "[redacted]"
    return value


def _read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    content_length = int(handler.headers.get("Content-Length", "0"))
    if content_length == 0:
        return {}
    raw_body = handler.rfile.read(content_length)
    if not raw_body:
        return {}
    data = json.loads(raw_body.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("JSON request body must be an object.")
    return data


def _required_text(body: Mapping[str, Any], field_name: str) -> str:
    value = _optional_text(body.get(field_name))
    if not value:
        raise ValueError(f"Missing required field: {field_name}.")
    return value


def _optional_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if not isinstance(value, str):
        raise ValueError("Text fields must be strings.")
    value = value.strip()
    return value if value else default


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _error_response(status_code: int, code: str, message: str) -> APIResponse:
    return APIResponse(status_code=status_code, body={"error": {"code": code, "message": message}})
