import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Barrier, Lock, Thread

from agentic_boilerplate.api import local as local_api_module
from agentic_boilerplate.api import LocalAPI, make_request_handler
from agentic_boilerplate.domain import (
    AgentRole,
    CodexLimitObservationSource,
    CodexLimitWindowAvailability,
    CodexLimitWindowStatus,
    InboxAuditEvent,
    InboxMessageType,
    InboxStatus,
    POInboxItem,
    build_codex_limit_availability_record,
)
from agentic_boilerplate.domain.agent_communication import (
    AgentCommunicationChannel,
    AgentMessageType,
    agent_message_idempotency_key,
    build_agent_message,
)
from agentic_boilerplate.domain.agent_assignment import (
    AgentAssignment,
    AssignmentPaths,
    AssignmentStackMetadata,
    AssignmentStatus,
    WorkerInstance,
    WorkerStatus,
)
from agentic_boilerplate.storage.agent_communication import FileAgentCommunicationStore
from agentic_boilerplate.storage.agent_assignment import FileAgentAssignmentStore
from agentic_boilerplate.storage.codex_limit_availability import FileCodexLimitAvailabilityStore
from agentic_boilerplate.storage.po_inbox import FilePOInboxStore


def test_health_endpoint_does_not_check_external_systems(tmp_path: Path) -> None:
    api = LocalAPI(tmp_path)

    response = api.handle_request("GET", "/health")

    assert response.status_code == 200
    assert response.body == {
        "status": "ok",
        "service": "agentic-boilerplate",
        "external_systems_checked": False,
        "po_inbox_ready": True,
    }


def test_api_create_list_read_and_answer_inbox_item(tmp_path: Path) -> None:
    api = LocalAPI(tmp_path)

    created = api.handle_request("POST", "/po-inbox", _question_body())

    assert created.status_code == 201
    assert created.body["item"]["id"] == "question-001"
    assert created.body["item"]["status"] == "open"
    assert created.body["item"]["project_id"] == "AP"

    listed = api.handle_request("GET", "/po-inbox?status=open")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.body["items"]] == ["question-001"]
    ap_listed = api.handle_request("GET", "/po-inbox?status=open&project_id=AP")
    other_listed = api.handle_request("GET", "/po-inbox?status=open&project_id=OTHER")
    assert [item["id"] for item in ap_listed.body["items"]] == ["question-001"]
    assert other_listed.body["items"] == []

    read = api.handle_request("GET", "/po-inbox/question-001")
    assert read.status_code == 200
    assert read.body["item"]["title"] == "Choose Jira status"

    answered = api.handle_request("POST", "/po-inbox/question-001/answer", {"answer": "Use FUNNEL."})

    assert answered.status_code == 200
    assert answered.body["item"]["status"] == "answered"
    assert answered.body["item"]["answer"] == "Use FUNNEL."
    assert [event["action"] for event in answered.body["item"]["audit"]] == ["created", "answered"]


def test_api_aggregates_multi_project_inboxes_with_composite_item_ids(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    ap_root = data_root / "projects" / "ap" / "po-inbox"
    agent_root = data_root / "projects" / "agent" / "po-inbox"
    _write_operator_projects_config(data_root, ap_root=ap_root, agent_root=agent_root)
    FilePOInboxStore(ap_root).create(
        _project_question(
            item_id="shared-question",
            project_id="AP",
            project_name="Airline POC",
            jira_project_key="AP",
            jira_issue_key="AP-29",
            created_at="2026-08-10T10:00:00Z",
        )
    )
    FilePOInboxStore(agent_root).create(
        _project_question(
            item_id="shared-question",
            project_id="AGENT",
            project_name="Agentic Boilerplate",
            jira_project_key="AGENT",
            jira_issue_key="AGENT-637",
            created_at="2026-08-10T09:00:00Z",
        )
    )

    api = LocalAPI(data_root / "po-inbox", data_root=data_root)

    listed = api.handle_request("GET", "/po-inbox?status=open")
    assert listed.status_code == 200
    assert [item["composite_id"] for item in listed.body["items"]] == [
        "AP::shared-question",
        "AGENT::shared-question",
    ]
    assert listed.body["items"][0]["source_item_id"] == "shared-question"
    assert listed.body["items"][0]["project_identity"] == "Airline POC (AP)"
    assert {project["project_id"] for project in listed.body["projects"]} == {"AP", "AGENT"}

    ap_only = api.handle_request("GET", "/po-inbox?status=open&project_id=AP")
    assert [item["composite_id"] for item in ap_only.body["items"]] == ["AP::shared-question"]

    filtered = api.handle_request(
        "GET",
        "/po-inbox?status=open&agent_role=architecture&message_type=blocking_question&jira_issue_key=AGENT-637",
    )
    assert [item["composite_id"] for item in filtered.body["items"]] == ["AGENT::shared-question"]

    read = api.handle_request("GET", "/po-inbox/AP%3A%3Ashared-question")
    assert read.status_code == 200
    assert read.body["item"]["jira_issue_key"] == "AP-29"
    assert read.body["item"]["project_root"] == ""

    answered = api.handle_request(
        "POST",
        "/po-inbox/AP%3A%3Ashared-question/answer",
        {"answer": "Use the AP-specific deployment path."},
    )
    assert answered.status_code == 200
    assert answered.body["item"]["status"] == "answered"
    assert FilePOInboxStore(ap_root).read("shared-question").status == InboxStatus.ANSWERED
    assert FilePOInboxStore(agent_root).read("shared-question").status == InboxStatus.OPEN


def test_api_preserves_healthy_project_items_when_one_project_inbox_fails(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    ap_root = data_root / "projects" / "ap" / "po-inbox"
    bad_root = data_root / "projects" / "bad" / "po-inbox"
    _write_operator_projects_config(data_root, ap_root=ap_root, agent_root=bad_root, agent_project_id="BAD")
    FilePOInboxStore(ap_root).create(
        _project_question(
            item_id="ap-question",
            project_id="AP",
            project_name="Airline POC",
            jira_project_key="AP",
            jira_issue_key="AP-29",
            created_at="2026-08-10T10:00:00Z",
        )
    )
    (bad_root / "open").mkdir(parents=True)
    (bad_root / "open" / "bad-question.json").write_text('{"id":"bad-question"}', encoding="utf-8")

    response = LocalAPI(data_root / "po-inbox", data_root=data_root).handle_request("GET", "/po-inbox?status=open")

    assert response.status_code == 200
    assert [item["composite_id"] for item in response.body["items"]] == ["AP::ap-question"]
    assert len(response.body["project_errors"]) == 1
    error = response.body["project_errors"][0]
    assert error["project_id"] == "BAD"
    assert error["project_name"] == "Agentic Boilerplate"
    assert error["jira_project_key"] == "AGENT"
    assert error["repository"] == "example-org/agentic-boilerplate"
    assert error["message"] == "Project inbox could not be loaded safely."
    assert "inbox_root" not in error


def test_api_exports_project_scoped_and_all_project_inbox_json(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    ap_root = data_root / "projects" / "ap" / "po-inbox"
    agent_root = data_root / "projects" / "agent" / "po-inbox"
    _write_operator_projects_config(data_root, ap_root=ap_root, agent_root=agent_root)
    FilePOInboxStore(ap_root).create(
        _project_question(
            item_id="shared-question",
            project_id="AP",
            project_name="Airline POC",
            jira_project_key="AP",
            jira_issue_key="AP-29",
            created_at="2026-08-10T10:00:00Z",
        )
    )
    FilePOInboxStore(agent_root).create(
        _project_question(
            item_id="shared-question",
            project_id="AGENT",
            project_name="Agentic Boilerplate",
            jira_project_key="AGENT",
            jira_issue_key="AGENT-637",
            created_at="2026-08-10T09:00:00Z",
        )
    )
    api = LocalAPI(data_root / "po-inbox", data_root=data_root)

    project_export = api.handle_request("GET", "/po-inbox/export?status=open&project_id=AP")
    all_export = api.handle_request("GET", "/po-inbox/export?status=open")

    assert project_export.status_code == 200
    assert project_export.body["schema_version"] == "po-inbox-export/v1"
    assert project_export.body["scope"] == "project"
    assert project_export.body["filters"]["project_id"] == "AP"
    assert project_export.body["project"]["project_id"] == "AP"
    assert [item["composite_id"] for item in project_export.body["items"]] == ["AP::shared-question"]

    assert all_export.status_code == 200
    assert all_export.body["scope"] == "all_projects"
    assert [project["project"]["project_id"] for project in all_export.body["projects"]] == ["AP", "AGENT"]
    all_item_ids = [
        item["composite_id"]
        for project in all_export.body["projects"]
        for item in project["items"]
    ]
    assert all_item_ids == ["AP::shared-question", "AGENT::shared-question"]
    assert FilePOInboxStore(ap_root).read("shared-question").status == InboxStatus.OPEN
    assert FilePOInboxStore(agent_root).read("shared-question").status == InboxStatus.OPEN


def test_api_export_includes_safe_project_errors_without_paths(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    ap_root = data_root / "projects" / "ap" / "po-inbox"
    bad_root = data_root / "projects" / "bad" / "po-inbox"
    _write_operator_projects_config(data_root, ap_root=ap_root, agent_root=bad_root, agent_project_id="BAD")
    FilePOInboxStore(ap_root).create(
        _project_question(
            item_id="ap-question",
            project_id="AP",
            project_name="Airline POC",
            jira_project_key="AP",
            jira_issue_key="AP-29",
            created_at="2026-08-10T10:00:00Z",
        )
    )
    (bad_root / "open").mkdir(parents=True)
    (bad_root / "open" / "bad-question.json").write_text('{"id":"bad-question"}', encoding="utf-8")

    response = LocalAPI(data_root / "po-inbox", data_root=data_root).handle_request("GET", "/po-inbox/export?status=open")

    assert response.status_code == 200
    assert response.body["schema_version"] == "po-inbox-export/v1"
    assert response.body["projects"][0]["project"]["project_id"] == "AP"
    assert response.body["errors"][0]["project_id"] == "BAD"
    combined = json.dumps(response.body)
    assert str(bad_root) not in combined
    assert "token" not in combined.lower()


def test_api_approval_and_resolve_decisions(tmp_path: Path) -> None:
    api = LocalAPI(tmp_path)

    assert api.handle_request("POST", "/po-inbox", _approval_body("approval-001", "Approve draft")).status_code == 201
    approved = api.handle_request("POST", "/po-inbox/approval-001/approve", {"answer": "Approved."})
    assert approved.status_code == 200
    assert approved.body["item"]["status"] == "approved"

    assert api.handle_request("POST", "/po-inbox", _approval_body("approval-002", "Reject draft")).status_code == 201
    rejected = api.handle_request("POST", "/po-inbox/approval-002/reject", {"answer": "Rejected."})
    assert rejected.status_code == 200
    assert rejected.body["item"]["status"] == "rejected"

    assert (
        api.handle_request(
            "POST",
            "/po-inbox",
            {
                "id": "fyi-001",
                "message_type": "fyi",
                "title": "Build finished",
                "message": "Worker finished.",
            },
        ).status_code
        == 201
    )
    resolved = api.handle_request("POST", "/po-inbox/fyi-001/resolve", {"note": "Seen."})
    assert resolved.status_code == 200
    assert resolved.body["item"]["status"] == "archived"


def test_api_errors_are_clear_and_do_not_print_secrets(tmp_path: Path) -> None:
    api = LocalAPI(tmp_path)

    missing = api.handle_request("GET", "/po-inbox/missing")
    invalid = api.handle_request("POST", "/po-inbox", {"id": "bad"})
    unknown = api.handle_request("GET", "/unknown")

    assert missing.status_code == 404
    assert missing.body["error"]["code"] == "not_found"
    assert invalid.status_code == 400
    assert invalid.body["error"]["code"] == "bad_request"
    assert unknown.status_code == 404

    combined_messages = " ".join(
        [
            missing.body["error"]["message"],
            invalid.body["error"]["message"],
            unknown.body["error"]["message"],
        ]
    )
    assert "JIRA_API_TOKEN" not in combined_messages
    assert "GITHUB_TOKEN" not in combined_messages


def test_operator_status_endpoint_lists_workers_assignments_limits_and_logs(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    inbox_root = data_root / "po-inbox"
    assignment_store = FileAgentAssignmentStore(data_root / "agent-state")
    assignment_store.create_worker(
        WorkerInstance(
            id="developer-1",
            role=AgentRole.DEVELOPER,
            status=WorkerStatus.ASSIGNED,
            display_name="Developer 1",
            current_assignment_id="assignment-AGENT-438",
            updated_at="2026-07-12T11:00:00Z",
        )
    )
    assignment_store.create_assignment(
        AgentAssignment(
            id="assignment-AGENT-438",
            jira_issue_key="AGENT-438",
            role=AgentRole.DEVELOPER,
            status=AssignmentStatus.IN_PROGRESS,
            paths=AssignmentPaths(
                context_pack_path="data/context-packs/AGENT-438/context.json",
                codex_job_path="data/codex-jobs/AGENT-438/job.json",
                output_path="data/codex-results/AGENT-438/result.json",
            ),
            worker_id="developer-1",
            codex_job_id="codex-job-AGENT-438",
            branch_name="feature/AGENT-438-token-leak",
            project_id="AGENT",
            project_name="Agentic Boilerplate",
            project_root="/home/user/business/agentic-bolierplate",
            repository="example-org/agentic-boilerplate",
            jira_project_key="AGENT",
            stack_metadata=AssignmentStackMetadata(
                stack_id="r12-s7-stack-a",
                lane_id="lane-1",
                stack_mode="stacked-dependent",
                resolved_path_version="resolver-v1",
                current_layer=2,
                expected_next_agent="review",
            ),
            pause_reason="Authorization: Bearer live-token",
            failure_reason="api_token=super-secret",
            created_at="2026-07-12T11:00:00Z",
            updated_at="2026-07-12T11:00:00Z",
        )
    )
    FileCodexLimitAvailabilityStore(data_root / "codex-limits").write_record(
        build_codex_limit_availability_record(
            record_id="availability-20260712T110000Z",
            short_window=CodexLimitWindowAvailability(
                status=CodexLimitWindowStatus.AVAILABLE,
                remaining_percent=92,
                reset_at="2026-07-12T16:00:00Z",
                observation_source=CodexLimitObservationSource.OPERATOR,
                observed_at="2026-07-12T11:00:00Z",
            ),
            broad_quota=CodexLimitWindowAvailability(
                status=CodexLimitWindowStatus.AVAILABLE,
                remaining_percent=88,
                reset_at="2026-07-19T11:00:00Z",
                observation_source=CodexLimitObservationSource.OPERATOR,
                observed_at="2026-07-12T11:00:00Z",
            ),
        )
    )
    log_path = data_root / "agent-logs" / "AGENT-438" / "test-evidence.md"
    log_path.parent.mkdir(parents=True)
    log_path.write_text("passed without token values", encoding="utf-8")

    response = LocalAPI(inbox_root).handle_request("GET", "/operator-status")

    assert response.status_code == 200
    assert response.body["workers"][0]["id"] == "developer-1"
    assert response.body["assignments"][0]["jira_issue_key"] == "AGENT-438"
    assert response.body["assignments"][0]["project_id"] == "AGENT"
    assert response.body["assignments"][0]["repository"] == "example-org/agentic-boilerplate"
    assert response.body["assignments"][0]["project_root"] == "[redacted]"
    assert response.body["assignments"][0]["story_lifecycle"]["next_expected_step"] == "Developer"
    assert response.body["assignments"][0]["story_lifecycle"]["steps"][3]["state"] == "next"
    assert response.body["assignments"][0]["stack_metadata"]["stack_id"] == "r12-s7-stack-a"
    assert response.body["stack_lanes"][0]["stack_id"] == "r12-s7-stack-a"
    assert response.body["stack_lanes"][0]["lane_id"] == "lane-1"
    assert response.body["stack_lanes"][0]["stories"][0]["jira_issue_key"] == "AGENT-438"
    assert response.body["stack_lanes"][0]["stories"][0]["layer_order"] == 2
    assert response.body["stack_lanes"][0]["stories"][0]["next_step"] == "review"
    assert response.body["stack_lanes"][0]["stories"][0]["evidence_state"] == "blocked"
    assert {
        artifact["kind"]
        for artifact in response.body["assignments"][0]["artifact_refs"]
    } >= {"context_pack", "codex_job", "output", "branch"}
    assert response.body["codex_limit"]["short_window"]["remaining_percent"] == 92
    assert response.body["codex_limit_gate"]["allowed"] is True
    assert response.body["codex_limit_windows"][0]["label"] == "Primary window"
    assert response.body["codex_limit_windows"][0]["observation_source"] == "operator"
    assert response.body["recent_logs"][0]["relative_path"] == "AGENT-438/test-evidence.md"
    combined = str(response.body).lower()
    assert "token" not in combined
    assert "live-token" not in combined
    assert "super-secret" not in combined
    assert "context_pack_path" not in str(response.body)
    assert "workspace_path" not in str(response.body)


def test_agent_messages_endpoint_lists_filters_and_graph_safely(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    assignment_store = FileAgentAssignmentStore(data_root / "agent-state")
    assignment_store.create_assignment(
        AgentAssignment(
            id="assignment-AP-29-dev",
            jira_issue_key="AP-29",
            role=AgentRole.DEVELOPER,
            status=AssignmentStatus.QUEUED,
            paths=AssignmentPaths(
                context_pack_path="data/context-packs/AP-29/context.json",
                codex_job_path="data/codex-jobs/AP-29/job.json",
                output_path="data/codex-results/AP-29/result.json",
            ),
            project_id="AP",
            project_name="Airline POC",
            repository="example-org/airline-poc",
            jira_project_key="AP",
            created_at="2026-08-10T12:00:00Z",
            updated_at="2026-08-10T12:00:00Z",
        )
    )
    message_store = FileAgentCommunicationStore(data_root / "agent-state")
    message_store.publish_message(
        build_agent_message(
            message_id="AP-29-resume",
            message_type=AgentMessageType.RESUME_REQUEST,
            idempotency_key=agent_message_idempotency_key(
                message_type=AgentMessageType.RESUME_REQUEST,
                project_id="AP",
                jira_issue_key="AP-29",
                assignment_id="assignment-AP-29-dev",
                target_role=AgentRole.DEVELOPER,
                target_channel=AgentCommunicationChannel.ROLE,
            ),
            source_role=AgentRole.SCHEDULER,
            target_role=AgentRole.DEVELOPER,
            target_channel=AgentCommunicationChannel.ROLE,
            created_at="2026-08-10T12:05:00Z",
            project_id="AP",
            project_name="Airline POC",
            project_root="/home/user/business/airline-poc",
            repository="example-org/airline-poc",
            jira_project_key="AP",
            jira_issue_key="AP-29",
            assignment_id="assignment-AP-29-dev",
            payload={"gate": {"allowed": False, "reason": "Authorization token leaked", "blockers": ["codex_limit_gate_closed"]}},
            artifact_refs=("/home/user/business/airline-poc/data/evidence.md",),
        )
    )
    message_store.publish_message(
        build_agent_message(
            message_id="AGENT-1-status",
            message_type=AgentMessageType.STATUS_UPDATE,
            idempotency_key="status:AGENT:AGENT-1",
            source_role=AgentRole.PLATFORM,
            target_channel=AgentCommunicationChannel.PROJECT,
            created_at="2026-08-10T12:07:00Z",
            project_id="AGENT",
            jira_issue_key="AGENT-1",
        )
    )

    response = LocalAPI(data_root / "po-inbox", data_root=data_root).handle_request(
        "GET",
        "/agent-messages?project_id=AP&role=scheduler&message_type=resume_request",
    )
    read = LocalAPI(data_root / "po-inbox", data_root=data_root).handle_request("GET", "/agent-messages/AP-29-resume")

    assert response.status_code == 200
    assert [item["id"] for item in response.body["items"]] == ["AP-29-resume"]
    assert response.body["items"][0]["project_identity"] == "Airline POC (AP)"
    assert response.body["items"][0]["resume_gate"]["allowed"] is False
    assert response.body["items"][0]["resume_gate"]["blockers"] == ["codex_limit_gate_closed"]
    assert response.body["items"][0]["linked_refs"][0]["kind"] == "jira_issue"
    assert any(node["id"] == "assignment:assignment-AP-29-dev" for node in response.body["graph"]["nodes"])
    assert any(edge["label"] == "resume_request" for edge in response.body["graph"]["edges"])
    assert read.status_code == 200
    assert read.body["item"]["id"] == "AP-29-resume"
    combined = json.dumps(response.body)
    assert "/home/user" not in combined
    assert "Authorization token leaked" not in combined
    assert "token" not in combined.lower()


def test_agent_messages_endpoint_creates_po_messages_actions_and_responses_without_mutating_inbox(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    inbox_store = FilePOInboxStore(data_root / "po-inbox")
    inbox_store.create(
        _project_question(
            item_id="po-question",
            project_id="AP",
            project_name="Airline POC",
            jira_project_key="AP",
            jira_issue_key="AP-29",
            created_at="2026-08-10T12:00:00Z",
        )
    )
    api = LocalAPI(data_root / "po-inbox", data_root=data_root)

    created = api.handle_request(
        "POST",
        "/agent-messages",
        {
            "id": "po-to-dev",
            "message_type": "po_question_to_agent",
            "project_id": "AP",
            "project_name": "Airline POC",
            "jira_project_key": "AP",
            "target_role": "developer",
            "target_channel": "role",
            "jira_issue_key": "AP-29",
            "assignment_id": "assignment-AP-29-dev",
            "subject": "Clarify endpoint",
            "body": "Please explain the API choice without token=secret-value.",
            "references": ["data/agent-logs/AP-29/evidence.md"],
            "response_requested": True,
        },
    )
    acknowledged = api.handle_request("POST", "/agent-messages/po-to-dev/acknowledge", {"actor": "developer"})
    response = api.handle_request(
        "POST",
        "/agent-messages/po-to-dev/respond",
        {
            "id": "dev-response",
            "source_role": "developer",
            "subject": "Endpoint clarification",
            "body": "The implementation uses the local API boundary.",
        },
    )
    consumed = api.handle_request("POST", "/agent-messages/po-to-dev/consume", {"actor": "developer"})
    listed = api.handle_request("GET", "/agent-messages?project_id=AP")

    assert created.status_code == 201
    assert created.body["item"]["id"] == "po-to-dev"
    assert created.body["item"]["display_lane"] == "product_owner"
    assert created.body["item"]["payload"]["body"] == "[redacted]"
    assert acknowledged.status_code == 200
    assert acknowledged.body["item"]["status"] == "acknowledged"
    assert response.status_code == 201
    assert response.body["item"]["message_type"] == "agent_response_to_po"
    assert response.body["item"]["causation_id"] == "po-to-dev"
    assert consumed.status_code == 200
    assert consumed.body["item"]["status"] == "consumed"
    assert {item["id"] for item in listed.body["items"]} == {"po-to-dev", "dev-response"}
    assert inbox_store.read("po-question").status == InboxStatus.OPEN
    combined = json.dumps(listed.body).lower()
    assert "secret-value" not in combined
    assert "token" not in combined


def test_operator_rescue_lists_safe_actions_and_applies_requeue_with_audit_and_message(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    assignment_store = FileAgentAssignmentStore(data_root / "agent-state")
    assignment_store.create_assignment(
        AgentAssignment(
            id="assignment-AP-29-dev",
            jira_issue_key="AP-29",
            role=AgentRole.DEVELOPER,
            status=AssignmentStatus.FAILED,
            paths=AssignmentPaths(
                context_pack_path="data/context-packs/AP-29/context.json",
                codex_job_path="data/codex-jobs/AP-29/job.json",
                output_path="data/codex-results/AP-29/result.json",
            ),
            worker_id="developer-1",
            codex_job_id="codex-job-AP-29",
            project_id="AP",
            project_name="Airline POC",
            repository="example-org/airline-poc",
            jira_project_key="AP",
            failure_reason="Worker failed after hidden token value.",
            attempt_count=1,
            created_at="2026-08-10T12:00:00Z",
            updated_at="2026-08-10T12:00:00Z",
        )
    )
    FileCodexLimitAvailabilityStore(data_root / "codex-limits").write_record(
        build_codex_limit_availability_record(
            record_id="availability-20260810T120000Z",
            short_window=CodexLimitWindowAvailability(
                status=CodexLimitWindowStatus.AVAILABLE,
                remaining_percent=93,
                reset_at="2026-08-10T16:00:00Z",
                observation_source=CodexLimitObservationSource.OPERATOR,
                observed_at="2026-08-10T12:00:00Z",
            ),
            broad_quota=CodexLimitWindowAvailability(
                status=CodexLimitWindowStatus.AVAILABLE,
                remaining_percent=91,
                reset_at="2026-08-17T12:00:00Z",
                observation_source=CodexLimitObservationSource.OPERATOR,
                observed_at="2026-08-10T12:00:00Z",
            ),
        )
    )
    api = LocalAPI(data_root / "po-inbox", data_root=data_root)

    listed = api.handle_request("GET", "/operator-rescue?project_id=AP")
    applied = api.handle_request(
        "POST",
        "/operator-rescue/assignment-AP-29-dev/retry",
        {"actor": "po", "reason": "Retry after operator review."},
    )

    assert listed.status_code == 200
    retry_action = next(action for action in listed.body["items"][0]["actions"] if action["action"] == "retry")
    assert retry_action["allowed"] is True
    assert listed.body["items"][0]["assignment"]["project_root"] == ""
    assert listed.body["codex_limit_gate"]["allowed"] is True

    assert applied.status_code == 200
    assert applied.body["previous_status"] == "failed"
    assert applied.body["assignment"]["status"] == "queued"
    assert applied.body["assignment"]["attempt_count"] == 2
    assert applied.body["audit_written"] is True
    assert applied.body["audit_ref"].startswith("agent-state/operator-rescue-audit/")
    assert applied.body["message_written"] is True
    assert applied.body["message_created"] is True
    assert applied.body["message_id"].startswith("operator-rescue-assignment-AP-29-dev-retry")

    stored_assignment = assignment_store.read_assignment("assignment-AP-29-dev")
    assert stored_assignment.status is AssignmentStatus.QUEUED
    assert stored_assignment.failure_reason == ""
    messages = FileAgentCommunicationStore(data_root / "agent-state").list_messages(assignment_id="assignment-AP-29-dev")
    assert len(messages) == 1
    assert messages[0].message_type is AgentMessageType.RESUME_REQUEST
    assert messages[0].payload["operator_action"] == "retry"
    assert (data_root / applied.body["audit_ref"]).is_file()
    combined = json.dumps(applied.body).lower()
    assert "hidden token value" not in combined
    assert "token" not in combined


def test_operator_rescue_blocks_duplicate_resume_and_fresh_stale_lock_clear(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    fresh_updated_at = (datetime.now(UTC) - timedelta(minutes=1)).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )
    assignment_store = FileAgentAssignmentStore(data_root / "agent-state")
    assignment_store.create_assignment(
        AgentAssignment(
            id="assignment-AP-30-paused",
            jira_issue_key="AP-30",
            role=AgentRole.DEVELOPER,
            status=AssignmentStatus.PAUSED_LIMIT,
            paths=AssignmentPaths(
                context_pack_path="data/context-packs/AP-30/context.json",
                codex_job_path="data/codex-jobs/AP-30/job.json",
                output_path="data/codex-results/AP-30/result.json",
                failed_request_path="data/codex-limits/failed/AP-30.json",
            ),
            worker_id="developer-1",
            codex_job_id="codex-job-AP-30",
            project_id="AP",
            project_name="Airline POC",
            jira_project_key="AP",
            pause_reason="Waiting for quota.",
            created_at="2026-08-10T12:00:00Z",
            updated_at=fresh_updated_at,
        )
    )
    assignment_store.create_assignment(
        AgentAssignment(
            id="assignment-AP-30-active",
            jira_issue_key="AP-30",
            role=AgentRole.DEVELOPER,
            status=AssignmentStatus.QUEUED,
            paths=AssignmentPaths(
                context_pack_path="data/context-packs/AP-30/context-2.json",
                codex_job_path="data/codex-jobs/AP-30/job-2.json",
                output_path="data/codex-results/AP-30/result-2.json",
            ),
            project_id="AP",
            project_name="Airline POC",
            jira_project_key="AP",
            created_at="2026-08-10T12:01:00Z",
            updated_at="2026-08-10T12:01:00Z",
        )
    )
    FileCodexLimitAvailabilityStore(data_root / "codex-limits").write_record(
        build_codex_limit_availability_record(
            record_id="availability-20260810T125900Z",
            short_window=CodexLimitWindowAvailability(
                status=CodexLimitWindowStatus.AVAILABLE,
                remaining_percent=90,
                reset_at="2026-08-10T16:00:00Z",
                observation_source=CodexLimitObservationSource.OPERATOR,
                observed_at="2026-08-10T12:59:00Z",
            ),
            broad_quota=CodexLimitWindowAvailability(
                status=CodexLimitWindowStatus.AVAILABLE,
                remaining_percent=90,
                reset_at="2026-08-17T12:00:00Z",
                observation_source=CodexLimitObservationSource.OPERATOR,
                observed_at="2026-08-10T12:59:00Z",
            ),
        )
    )
    api = LocalAPI(data_root / "po-inbox", data_root=data_root)

    resume = api.handle_request("POST", "/operator-rescue/assignment-AP-30-paused/resume", {"reason": "Resume."})
    stale_lock = api.handle_request(
        "POST",
        "/operator-rescue/assignment-AP-30-paused/clear-stale-lock",
        {"reason": "Clear lock."},
    )

    assert resume.status_code == 409
    assert "Another active assignment" in resume.body["decision"]["blockers"][0]
    assert stale_lock.status_code == 409
    assert "less than 60 minutes" in stale_lock.body["decision"]["blockers"][0]
    assert any("Another active assignment" in blocker for blocker in stale_lock.body["decision"]["blockers"])
    assert assignment_store.read_assignment("assignment-AP-30-paused").status is AssignmentStatus.PAUSED_LIMIT
    assert FileAgentCommunicationStore(data_root / "agent-state").list_messages() == ()


def test_codex_limits_endpoint_reads_and_writes_single_pool_records(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    api = LocalAPI(data_root / "po-inbox", data_root=data_root)

    empty = api.handle_request("GET", "/codex-limits")
    assert empty.status_code == 200
    assert empty.body["latest_record"] is None
    assert empty.body["gate"]["allowed"] is False
    assert empty.body["gate"]["action"] == "ask_product_owner"

    saved = api.handle_request(
        "POST",
        "/codex-limits/records",
        {
            "id": "operator-20260810T100000Z",
            "plan_mode": "single_pool",
            "account_scope_id": "chatgpt-primary",
            "note": "Pro plan single visible pool.",
            "windows": [
                {
                    "window_id": "agentic_pool",
                    "label": "Current plan",
                    "status": "available",
                    "remaining_percent": 82,
                    "reset_at": "2026-08-11T04:00:00Z",
                    "authoritative": True,
                    "bucket_id": "codex",
                    "window_name": "primary",
                    "window_duration_minutes": 10080,
                }
            ],
        },
    )

    assert saved.status_code == 201
    assert saved.body["latest_record"]["id"] == "operator-20260810T100000Z"
    assert saved.body["latest_record"]["plan_mode"] == "single_pool"
    assert saved.body["latest_record"]["recommended_action"] == "resume"
    assert saved.body["gate"]["allowed"] is True
    assert saved.body["windows"][0]["label"] == "Current plan"
    assert saved.body["location"]["path"] == "[redacted]"

    stored = FileCodexLimitAvailabilityStore(data_root / "codex-limits").read_record("operator-20260810T100000Z")
    assert stored.plan_mode.value == "single_pool"
    assert stored.account_scope_id == "chatgpt-primary"
    assert stored.short_window.remaining_percent == 82
    assert stored.short_window.bucket_id == "codex"
    assert stored.short_window.window_name == "primary"
    assert stored.short_window.window_duration_minutes == 10080
    assert stored.broad_quota.remaining_percent == 82


def test_codex_limits_endpoint_writes_dual_window_records_atomically(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    api = LocalAPI(data_root / "po-inbox", data_root=data_root)

    saved = api.handle_request(
        "POST",
        "/codex-limits/records",
        {
            "id": "operator-20260810T101500Z",
            "plan_mode": "dual_window",
            "note": "Authorization token should be redacted",
            "windows": [
                {
                    "window_id": "short",
                    "label": "Short window",
                    "status": "available",
                    "remaining_percent": 8,
                    "reset_at": "2026-08-10T16:00:00Z",
                    "authoritative": True,
                },
                {
                    "window_id": "broad",
                    "label": "Broad quota",
                    "status": "available",
                    "remaining_percent": 90,
                    "reset_at": "2026-08-17T16:00:00Z",
                    "authoritative": False,
                },
            ],
        },
    )

    assert saved.status_code == 201
    assert saved.body["latest_record"]["recommended_action"] == "wait"
    assert saved.body["latest_record"]["note"] == "[redacted]"
    assert [window["label"] for window in saved.body["windows"]] == ["Short window", "Broad quota"]
    assert "token" not in json.dumps(saved.body).lower()

    invalid = api.handle_request(
        "POST",
        "/codex-limits/records",
        {
            "id": "operator-20260810T101600Z",
            "plan_mode": "dual_window",
            "windows": [
                {
                    "label": "Short window",
                    "status": "available",
                    "remaining_percent": 101,
                    "reset_at": "2026-08-10T16:00:00Z",
                }
            ],
        },
    )

    assert invalid.status_code == 400
    assert "remaining_percent" in invalid.body["error"]["message"]
    records = FileCodexLimitAvailabilityStore(data_root / "codex-limits").list_records()
    assert [record.id for record in records] == ["operator-20260810T101500Z"]


def test_operator_api_uses_configured_scope_and_observation_order(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    store = FileCodexLimitAvailabilityStore(data_root / "codex-limits")

    def record(
        record_id: str,
        *,
        account_scope_id: str,
        observed_at: str,
        remaining_percent: int,
    ):
        window = CodexLimitWindowAvailability(
            status=CodexLimitWindowStatus.AVAILABLE,
            remaining_percent=remaining_percent,
            reset_at="2026-09-03T10:00:00Z",
            observation_source=CodexLimitObservationSource.OPERATOR,
            observed_at=observed_at,
            bucket_id="codex",
        )
        return build_codex_limit_availability_record(
            record_id=record_id,
            short_window=window,
            broad_quota=window,
            account_scope_id=account_scope_id,
        )

    store.write_record(
        record(
            "z-older",
            account_scope_id="chatgpt-primary",
            observed_at="2026-09-02T12:00:00Z",
            remaining_percent=90,
        )
    )
    store.write_record(
        record(
            "a-newer",
            account_scope_id="chatgpt-primary",
            observed_at="2026-09-02T13:00:00Z",
            remaining_percent=5,
        )
    )
    store.write_record(
        record(
            "other-account",
            account_scope_id="chatgpt-secondary",
            observed_at="2026-09-02T14:00:00Z",
            remaining_percent=100,
        )
    )
    api = LocalAPI(
        data_root / "po-inbox",
        data_root=data_root,
        limit_account_scope_id="chatgpt-primary",
        limit_bucket_id="codex",
    )

    limits = api.handle_request("GET", "/codex-limits")
    status = api.handle_request("GET", "/operator-status")

    assert limits.body["latest_record"]["id"] == "a-newer"
    assert limits.body["gate"]["allowed"] is False
    assert status.body["codex_limit"]["id"] == "a-newer"
    assert status.body["codex_limit_gate"]["allowed"] is False


def test_codex_limit_update_inherits_configured_scope_and_selects_manual_limit(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    older_provider_window = CodexLimitWindowAvailability(
        status=CodexLimitWindowStatus.AVAILABLE,
        remaining_percent=95,
        reset_at="2026-09-03T10:00:00Z",
        observation_source=CodexLimitObservationSource.CODEX_APP_SERVER,
        observed_at="2026-09-01T10:00:00Z",
        bucket_id="codex",
    )
    FileCodexLimitAvailabilityStore(data_root / "codex-limits").write_record(
        build_codex_limit_availability_record(
            record_id="older-provider-available",
            short_window=older_provider_window,
            broad_quota=older_provider_window,
            account_scope_id="chatgpt-primary",
        )
    )
    api = LocalAPI(
        data_root / "po-inbox",
        data_root=data_root,
        limit_account_scope_id="chatgpt-primary",
        limit_bucket_id="codex",
    )

    saved = api.handle_request(
        "POST",
        "/codex-limits/records",
        {
            "id": "operator-scoped-limit",
            "plan_mode": "single_pool",
            "windows": [
                {
                    "status": "limited",
                    "remaining_percent": 2,
                    "reset_at": "2026-09-03T10:00:00Z",
                    "authoritative": True,
                }
            ],
        },
    )

    assert saved.status_code == 201
    assert saved.body["latest_record"]["id"] == "operator-scoped-limit"
    assert saved.body["latest_record"]["account_scope_id"] == "chatgpt-primary"
    assert saved.body["latest_record"]["windows"][0]["bucket_id"] == "codex"
    assert saved.body["gate"]["allowed"] is False
    assert saved.body["gate"]["action"] == "wait"

    stored = FileCodexLimitAvailabilityStore(data_root / "codex-limits").read_record("operator-scoped-limit")
    assert stored.account_scope_id == "chatgpt-primary"
    assert stored.short_window.bucket_id == "codex"


def test_codex_limit_update_infers_sole_provider_bucket_when_api_unconfigured(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    provider_window = CodexLimitWindowAvailability(
        status=CodexLimitWindowStatus.AVAILABLE,
        remaining_percent=95,
        reset_at="2026-09-03T10:00:00Z",
        observation_source=CodexLimitObservationSource.CODEX_APP_SERVER,
        observed_at="2026-09-01T10:00:00Z",
        bucket_id="codex",
    )
    store = FileCodexLimitAvailabilityStore(data_root / "codex-limits")
    store.write_record(
        build_codex_limit_availability_record(
            record_id="provider-available",
            short_window=provider_window,
            broad_quota=provider_window,
            account_scope_id="chatgpt-primary",
        )
    )
    api = LocalAPI(
        data_root / "po-inbox",
        data_root=data_root,
        limit_account_scope_id="chatgpt-primary",
    )

    saved = api.handle_request(
        "POST",
        "/codex-limits/records",
        {
            "id": "operator-inferred-limit",
            "plan_mode": "single_pool",
            "windows": [
                {
                    "status": "limited",
                    "remaining_percent": 2,
                    "reset_at": "2026-09-03T10:00:00Z",
                    "authoritative": True,
                }
            ],
        },
    )

    stored = store.read_record("operator-inferred-limit")
    assert saved.status_code == 201
    assert saved.body["latest_record"]["id"] == "operator-inferred-limit"
    assert saved.body["gate"]["allowed"] is False
    assert stored.short_window.bucket_id == "codex"


def test_concurrent_first_provider_bucket_does_not_hide_manual_stop(
    tmp_path: Path,
    monkeypatch,
) -> None:
    data_root = tmp_path / "data"
    store = FileCodexLimitAvailabilityStore(data_root / "codex-limits")
    api = LocalAPI(
        data_root / "po-inbox",
        data_root=data_root,
        limit_account_scope_id="chatgpt-primary",
    )
    clock_lock = Lock()
    clock = datetime(2026, 9, 2, 10, 1, 0, tzinfo=UTC)

    def tick() -> str:
        nonlocal clock
        with clock_lock:
            value = clock.isoformat().replace("+00:00", "Z")
            clock += timedelta(seconds=1)
            return value

    manual_bucket_inferred = Barrier(2)
    provider_persisted = Barrier(2)
    provider_errors: list[BaseException] = []
    original_resolve = local_api_module.resolve_codex_limit_write_bucket_id

    def synchronized_resolve(records, *, account_scope_id="", configured_bucket_id=""):
        resolved = original_resolve(
            records,
            account_scope_id=account_scope_id,
            configured_bucket_id=configured_bucket_id,
        )
        manual_bucket_inferred.wait(timeout=3)
        provider_persisted.wait(timeout=3)
        return resolved

    def write_first_provider_bucket() -> None:
        try:
            manual_bucket_inferred.wait(timeout=3)
            provider_window = CodexLimitWindowAvailability(
                status=CodexLimitWindowStatus.AVAILABLE,
                remaining_percent=95,
                reset_at="2026-09-03T10:00:00Z",
                observation_source=CodexLimitObservationSource.CODEX_APP_SERVER,
                observed_at="2026-09-02T10:00:00Z",
                bucket_id="codex",
            )
            store.write_record(
                build_codex_limit_availability_record(
                    record_id="provider-first-bucket",
                    short_window=provider_window,
                    broad_quota=provider_window,
                    account_scope_id="chatgpt-primary",
                )
            )
            provider_persisted.wait(timeout=3)
        except BaseException as error:
            provider_errors.append(error)
            raise

    monkeypatch.setattr(local_api_module, "_utc_now", tick)
    monkeypatch.setattr(
        local_api_module,
        "resolve_codex_limit_write_bucket_id",
        synchronized_resolve,
    )
    provider_thread = Thread(target=write_first_provider_bucket)
    provider_thread.start()

    saved = api.handle_request(
        "POST",
        "/codex-limits/records",
        {
            "id": "operator-manual-stop",
            "plan_mode": "single_pool",
            "windows": [
                {
                    "status": "limited",
                    "remaining_percent": 2,
                    "reset_at": "2026-09-03T10:00:00Z",
                    "authoritative": True,
                }
            ],
        },
    )
    provider_thread.join(timeout=3)

    assert not provider_thread.is_alive()
    assert provider_errors == []
    assert saved.status_code == 201
    assert saved.body["latest_record"]["id"] == "operator-manual-stop"
    assert saved.body["latest_record"]["windows"][0]["bucket_id"] == ""
    assert saved.body["gate"]["allowed"] is False
    assert saved.body["gate"]["action"] == "wait"

    stored_manual = store.read_record("operator-manual-stop")
    stored_provider = store.read_record("provider-first-bucket")
    assert stored_manual.short_window.bucket_id == ""
    assert stored_provider.short_window.bucket_id == "codex"

    later = api.handle_request("GET", "/codex-limits")
    assert later.body["latest_record"]["id"] == "operator-manual-stop"
    assert later.body["gate"]["allowed"] is False

def test_codex_limit_update_preserves_default_bucket_without_provider_identity(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    api = LocalAPI(
        data_root / "po-inbox",
        data_root=data_root,
        limit_account_scope_id="chatgpt-primary",
    )

    saved = api.handle_request(
        "POST",
        "/codex-limits/records",
        {
            "id": "operator-legacy-default",
            "plan_mode": "single_pool",
            "windows": [
                {
                    "status": "available",
                    "remaining_percent": 90,
                    "reset_at": "2026-09-03T10:00:00Z",
                    "authoritative": True,
                }
            ],
        },
    )

    stored = FileCodexLimitAvailabilityStore(data_root / "codex-limits").read_record(
        "operator-legacy-default"
    )
    assert saved.status_code == 201
    assert saved.body["latest_record"]["id"] == "operator-legacy-default"
    assert saved.body["gate"]["allowed"] is True
    assert stored.short_window.bucket_id == ""


def test_codex_limit_update_with_explicit_multi_bucket_record_fails_closed(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    store = FileCodexLimitAvailabilityStore(data_root / "codex-limits")
    older_window = CodexLimitWindowAvailability(
        status=CodexLimitWindowStatus.AVAILABLE,
        remaining_percent=95,
        reset_at="2026-09-03T10:00:00Z",
        observation_source=CodexLimitObservationSource.OPERATOR,
        observed_at="2026-09-02T10:00:00Z",
    )
    store.write_record(
        build_codex_limit_availability_record(
            record_id="older-available",
            short_window=older_window,
            broad_quota=older_window,
            account_scope_id="chatgpt-primary",
        )
    )
    api = LocalAPI(
        data_root / "po-inbox",
        data_root=data_root,
        limit_account_scope_id="chatgpt-primary",
    )

    saved = api.handle_request(
        "POST",
        "/codex-limits/records",
        {
            "id": "operator-multi-bucket",
            "plan_mode": "dual_window",
            "windows": [
                {
                    "status": "available",
                    "remaining_percent": 90,
                    "reset_at": "2026-09-03T10:00:00Z",
                    "bucket_id": "codex",
                    "authoritative": True,
                },
                {
                    "status": "available",
                    "remaining_percent": 80,
                    "reset_at": "2026-09-04T10:00:00Z",
                    "bucket_id": "credits",
                    "authoritative": True,
                },
            ],
        },
    )
    follow_up = api.handle_request("GET", "/codex-limits")

    assert saved.status_code == 201
    assert saved.body["latest_record"]["id"] == "selection-failure"
    assert saved.body["gate"]["allowed"] is False
    assert saved.body["gate"]["action"] == "ask_product_owner"
    assert store.read_record("operator-multi-bucket").windows[1].bucket_id == "credits"
    assert follow_up.body["latest_record"]["id"] == "selection-failure"
    assert follow_up.body["gate"]["allowed"] is False


def test_codex_limit_update_requires_explicit_bucket_when_provider_scope_is_ambiguous(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    store = FileCodexLimitAvailabilityStore(data_root / "codex-limits")
    for record_id, bucket_id in (("provider-codex", "codex"), ("provider-other", "other")):
        window = CodexLimitWindowAvailability(
            status=CodexLimitWindowStatus.AVAILABLE,
            remaining_percent=95,
            reset_at="2026-09-03T10:00:00Z",
            observation_source=CodexLimitObservationSource.CODEX_APP_SERVER,
            observed_at="2026-09-01T10:00:00Z",
            bucket_id=bucket_id,
        )
        store.write_record(
            build_codex_limit_availability_record(
                record_id=record_id,
                short_window=window,
                broad_quota=window,
                account_scope_id="chatgpt-primary",
            )
        )
    api = LocalAPI(
        data_root / "po-inbox",
        data_root=data_root,
        limit_account_scope_id="chatgpt-primary",
    )

    response = api.handle_request(
        "POST",
        "/codex-limits/records",
        {
            "id": "operator-ambiguous",
            "plan_mode": "single_pool",
            "windows": [
                {
                    "status": "limited",
                    "remaining_percent": 2,
                    "reset_at": "2026-09-03T10:00:00Z",
                    "authoritative": True,
                }
            ],
        },
    )

    assert response.status_code == 400
    assert response.body["error"] == {
        "code": "bad_request",
        "message": (
            "Codex quota bucket is ambiguous; provide bucket_id explicitly or "
            "configure CODEX_LIMIT_BUCKET_ID."
        ),
    }
    assert "operator-ambiguous" not in {record.id for record in store.list_records()}


def test_codex_limit_update_rejects_explicit_scope_outside_api_configuration(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    api = LocalAPI(
        data_root / "po-inbox",
        data_root=data_root,
        limit_account_scope_id="chatgpt-primary",
        limit_bucket_id="codex",
    )
    base_body = {
        "plan_mode": "single_pool",
        "windows": [
            {
                "status": "available",
                "remaining_percent": 90,
                "reset_at": "2026-09-03T10:00:00Z",
                "authoritative": True,
            }
        ],
    }

    wrong_account = api.handle_request(
        "POST",
        "/codex-limits/records",
        {**base_body, "id": "wrong-account", "account_scope_id": "chatgpt-secondary"},
    )
    wrong_bucket = api.handle_request(
        "POST",
        "/codex-limits/records",
        {
            **base_body,
            "id": "wrong-bucket",
            "windows": [{**base_body["windows"][0], "bucket_id": "other"}],
        },
    )

    assert wrong_account.status_code == 400
    assert wrong_account.body["error"]["code"] == "bad_request"
    assert wrong_bucket.status_code == 400
    assert wrong_bucket.body["error"]["code"] == "bad_request"
    assert FileCodexLimitAvailabilityStore(data_root / "codex-limits").list_records() == ()


def test_codex_limit_update_rejects_unsafe_ids_with_sanitized_400(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    api = LocalAPI(data_root / "po-inbox", data_root=data_root)
    base_body = {
        "plan_mode": "single_pool",
        "windows": [
            {
                "status": "available",
                "remaining_percent": 90,
                "reset_at": "2026-09-03T10:00:00Z",
                "authoritative": True,
            }
        ],
    }

    for unsafe_id in ("../outside", "token=must-not-leak"):
        response = api.handle_request(
            "POST",
            "/codex-limits/records",
            {**base_body, "id": unsafe_id},
        )
        serialized = json.dumps(response.body)

        assert response.status_code == 400
        assert response.body["error"] == {
            "code": "bad_request",
            "message": "Codex limit record id is invalid.",
        }
        assert unsafe_id not in serialized
        assert "must-not-leak" not in serialized

    assert FileCodexLimitAvailabilityStore(data_root / "codex-limits").list_records() == ()


def test_codex_limit_update_is_idempotent_and_conflict_is_sanitized(tmp_path: Path, monkeypatch) -> None:
    data_root = tmp_path / "data"
    clock = datetime(2026, 9, 2, 10, 0, 0, tzinfo=UTC)

    def tick() -> str:
        nonlocal clock
        value = clock.isoformat().replace("+00:00", "Z")
        clock += timedelta(seconds=1)
        return value

    monkeypatch.setattr(local_api_module, "_utc_now", tick)
    api = LocalAPI(
        data_root / "po-inbox",
        data_root=data_root,
        limit_account_scope_id="chatgpt-primary",
        limit_bucket_id="codex",
    )
    record_id = "credential-super-secret"
    body = {
        "id": record_id,
        "plan_mode": "single_pool",
        "windows": [
            {
                "status": "available",
                "remaining_percent": 90,
                "reset_at": "2026-09-03T10:00:00Z",
                "authoritative": True,
            }
        ],
    }

    created = api.handle_request("POST", "/codex-limits/records", body)
    identical_retry = api.handle_request("POST", "/codex-limits/records", body)
    conflicting_retry = api.handle_request(
        "POST",
        "/codex-limits/records",
        {
            **body,
            "windows": [{**body["windows"][0], "remaining_percent": 20}],
        },
    )

    assert created.status_code == 201
    assert identical_retry.status_code == 201
    assert identical_retry.body["latest_record"] == created.body["latest_record"]
    assert conflicting_retry.status_code == 409
    assert conflicting_retry.body["error"] == {
        "code": "immutable_record_conflict",
        "message": "A Codex limit record with this id already exists with different immutable content.",
    }
    assert "super-secret" not in json.dumps(conflicting_retry.body)
    records = FileCodexLimitAvailabilityStore(data_root / "codex-limits").list_records()
    assert len(records) == 1
    assert records[0].short_window.remaining_percent == 90


def test_concurrent_identical_codex_limit_updates_are_idempotent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    data_root = tmp_path / "data"
    generated_times: list[str] = []
    clock_lock = Lock()
    clock = datetime(2026, 9, 2, 10, 0, 0, tzinfo=UTC)

    def tick() -> str:
        nonlocal clock
        with clock_lock:
            value = clock.isoformat().replace("+00:00", "Z")
            clock += timedelta(seconds=1)
            generated_times.append(value)
            return value

    record_id = "concurrent-identical"
    write_barrier = Barrier(2)
    original_write_record = FileCodexLimitAvailabilityStore.write_record

    def synchronized_write(store, record):
        if record.id == record_id:
            write_barrier.wait(timeout=3)
        return original_write_record(store, record)

    monkeypatch.setattr(local_api_module, "_utc_now", tick)
    monkeypatch.setattr(
        FileCodexLimitAvailabilityStore,
        "write_record",
        synchronized_write,
    )
    api = LocalAPI(
        data_root / "po-inbox",
        data_root=data_root,
        limit_account_scope_id="chatgpt-primary",
        limit_bucket_id="codex",
    )
    body = {
        "id": record_id,
        "plan_mode": "single_pool",
        "note": "Operator-confirmed capacity.",
        "windows": [
            {
                "status": "available",
                "remaining_percent": 90,
                "reset_at": "2026-09-03T10:00:00Z",
                "authoritative": True,
            }
        ],
    }

    responses = _concurrent_api_posts(api, body, body)

    assert [status for status, _ in responses] == [201, 201]
    assert responses[0][1]["latest_record"] == responses[1][1]["latest_record"]
    assert generated_times[:2] == [
        "2026-09-02T10:00:00Z",
        "2026-09-02T10:00:01Z",
    ]
    records = FileCodexLimitAvailabilityStore(data_root / "codex-limits").list_records()
    assert len(records) == 1
    assert records[0].account_scope_id == "chatgpt-primary"
    assert records[0].short_window.bucket_id == "codex"
    assert records[0].short_window.observed_at in generated_times[:2]


def test_concurrent_conflicting_codex_limit_updates_return_sanitized_409(
    tmp_path: Path,
    monkeypatch,
) -> None:
    data_root = tmp_path / "data"
    barriers: dict[str, Barrier] = {}
    original_write_record = FileCodexLimitAvailabilityStore.write_record

    def synchronized_write(store, record):
        barrier = barriers.get(record.id)
        if barrier is not None:
            barrier.wait(timeout=3)
        return original_write_record(store, record)

    monkeypatch.setattr(
        FileCodexLimitAvailabilityStore,
        "write_record",
        synchronized_write,
    )
    api = LocalAPI(data_root / "po-inbox", data_root=data_root)
    base_window = {
        "status": "available",
        "remaining_percent": 90,
        "reset_at": "2026-09-03T10:00:00Z",
        "authoritative": True,
    }
    base_body = {
        "plan_mode": "single_pool",
        "note": "baseline",
        "windows": [base_window],
    }
    cases = {
        "status": {
            **base_body,
            "windows": [{**base_window, "status": "limited"}],
        },
        "capacity": {
            **base_body,
            "windows": [{**base_window, "remaining_percent": 20}],
        },
        "reset": {
            **base_body,
            "windows": [{**base_window, "reset_at": "2026-09-04T10:00:00Z"}],
        },
        "scope": {
            **base_body,
            "account_scope_id": "other-account",
        },
        "bucket": {
            **base_body,
            "windows": [{**base_window, "bucket_id": "other-bucket"}],
        },
        "plan": {
            **base_body,
            "plan_mode": "dual_window",
            "windows": [
                base_window,
                {
                    **base_window,
                    "window_id": "secondary",
                    "label": "Secondary quota",
                },
            ],
        },
        "note": {
            **base_body,
            "note": "different note",
        },
    }

    for case, conflicting_body in cases.items():
        record_id = f"credential-super-secret-{case}"
        barriers[record_id] = Barrier(2)
        responses = _concurrent_api_posts(
            api,
            {**base_body, "id": record_id},
            {**conflicting_body, "id": record_id},
        )
        statuses = sorted(status for status, _ in responses)
        conflict_body = next(body for status, body in responses if status == 409)

        assert statuses == [201, 409]
        assert conflict_body["error"] == {
            "code": "immutable_record_conflict",
            "message": "A Codex limit record with this id already exists with different immutable content.",
        }
        assert "super-secret" not in json.dumps(conflict_body)
        assert len(
            [
                record
                for record in FileCodexLimitAvailabilityStore(
                    data_root / "codex-limits"
                ).list_records()
                if record.id == record_id
            ]
        ) == 1


def test_codex_limit_update_rejects_source_change_with_sanitized_409(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    record_id = "credential-super-secret-source"
    provider_window = CodexLimitWindowAvailability(
        status=CodexLimitWindowStatus.AVAILABLE,
        remaining_percent=90,
        reset_at="2026-09-03T10:00:00Z",
        observation_source=CodexLimitObservationSource.CODEX_APP_SERVER,
        observed_at="2026-09-02T10:00:00Z",
        window_id="agentic_pool",
        label="Current plan",
        authoritative=True,
    )
    FileCodexLimitAvailabilityStore(data_root / "codex-limits").write_record(
        build_codex_limit_availability_record(
            record_id=record_id,
            short_window=provider_window,
            broad_quota=provider_window,
            plan_mode="single_pool",
            windows=(provider_window,),
        )
    )
    api = LocalAPI(data_root / "po-inbox", data_root=data_root)

    response = api.handle_request(
        "POST",
        "/codex-limits/records",
        {
            "id": record_id,
            "plan_mode": "single_pool",
            "windows": [
                {
                    "status": "available",
                    "remaining_percent": 90,
                    "reset_at": "2026-09-03T10:00:00Z",
                    "authoritative": True,
                }
            ],
        },
    )

    assert response.status_code == 409
    assert response.body["error"] == {
        "code": "immutable_record_conflict",
        "message": "A Codex limit record with this id already exists with different immutable content.",
    }
    assert "super-secret" not in json.dumps(response.body)


def test_request_handler_supports_browser_cors_and_health(tmp_path: Path) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_request_handler(LocalAPI(tmp_path)))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        options = HTTPConnection(host, port, timeout=2)
        options.request(
            "OPTIONS",
            "/po-inbox",
            headers={
                "Origin": "http://127.0.0.1:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        options_response = options.getresponse()
        assert options_response.status == 204
        assert options_response.getheader("Access-Control-Allow-Origin") == "*"
        assert "GET" in (options_response.getheader("Access-Control-Allow-Methods") or "")
        options.close()

        health = HTTPConnection(host, port, timeout=2)
        health.request("GET", "/health")
        health_response = health.getresponse()
        assert health_response.status == 200
        assert health_response.getheader("Access-Control-Allow-Origin") == "*"
        assert b'"status": "ok"' in health_response.read()
        health.close()
    finally:
        server.shutdown()
        server.server_close()


def test_request_handler_returns_sanitized_400_for_unsafe_codex_limit_ids(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    api = LocalAPI(data_root / "po-inbox", data_root=data_root)
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_request_handler(api))
    server_thread = Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    host, port = server.server_address
    base_body = {
        "plan_mode": "single_pool",
        "windows": [
            {
                "status": "available",
                "remaining_percent": 90,
                "reset_at": "2026-09-03T10:00:00Z",
                "authoritative": True,
            }
        ],
    }

    try:
        for unsafe_id in ("../../outside", "authorization=must-not-leak"):
            connection = HTTPConnection(host, port, timeout=5)
            try:
                connection.request(
                    "POST",
                    "/codex-limits/records",
                    body=json.dumps({**base_body, "id": unsafe_id}),
                    headers={"Content-Type": "application/json"},
                )
                response = connection.getresponse()
                response_body = json.loads(response.read())
            finally:
                connection.close()

            serialized = json.dumps(response_body)
            assert response.status == 400
            assert response_body["error"] == {
                "code": "bad_request",
                "message": "Codex limit record id is invalid.",
            }
            assert unsafe_id not in serialized
            assert "must-not-leak" not in serialized
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5)


def _concurrent_api_posts(
    api: LocalAPI,
    first_body: dict[str, object],
    second_body: dict[str, object],
) -> list[tuple[int, dict[str, object]]]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_request_handler(api))
    server_thread = Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    host, port = server.server_address

    def post(body: dict[str, object]) -> tuple[int, dict[str, object]]:
        connection = HTTPConnection(host, port, timeout=5)
        try:
            connection.request(
                "POST",
                "/codex-limits/records",
                body=json.dumps(body),
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(post, first_body),
                executor.submit(post, second_body),
            ]
            return [future.result(timeout=5) for future in futures]
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5)


def _question_body() -> dict[str, str]:
    return {
        "id": "question-001",
        "message_type": "blocking_question",
        "title": "Choose Jira status",
        "message": "Which status should drafts use?",
        "business_impact": "Controls PO workflow.",
        "recommendation": "Use FUNNEL.",
        "project_id": "AP",
        "project_name": "Airline POC",
        "repository": "example-org/airline-poc",
        "jira_project_key": "AP",
    }


def _approval_body(item_id: str, title: str) -> dict[str, str]:
    return {
        "id": item_id,
        "message_type": "approval_request",
        "title": title,
        "message": "Approve this draft?",
        "business_impact": "Controls implementation.",
        "recommendation": "Approve.",
    }


def _project_question(
    *,
    item_id: str,
    project_id: str,
    project_name: str,
    jira_project_key: str,
    jira_issue_key: str,
    created_at: str,
) -> POInboxItem:
    return POInboxItem(
        id=item_id,
        message_type=InboxMessageType.BLOCKING_QUESTION,
        status=InboxStatus.OPEN,
        title=f"Question for {jira_project_key}",
        message="Which delivery path should the agent use?",
        agent_role=AgentRole.ARCHITECTURE,
        created_at=created_at,
        jira_issue_key=jira_issue_key,
        project_id=project_id,
        project_name=project_name,
        repository=f"example-org/{project_id.lower()}",
        jira_project_key=jira_project_key,
        business_impact="Controls project-specific agent work.",
        recommendation="Use the configured project path.",
        audit=(
            InboxAuditEvent(
                timestamp=created_at,
                actor="architecture",
                action="created",
            ),
        ),
    )


def _write_operator_projects_config(
    data_root: Path,
    *,
    ap_root: Path,
    agent_root: Path,
    agent_project_id: str = "AGENT",
) -> None:
    data_root.mkdir(parents=True, exist_ok=True)
    (data_root / "operator-projects.json").write_text(
        json.dumps(
            {
                "projects": [
                    {
                        "project_id": "AP",
                        "project_name": "Airline POC",
                        "jira_project_key": "AP",
                        "repository": "example-org/ap",
                        "inbox_root": str(ap_root.relative_to(data_root)),
                    },
                    {
                        "project_id": agent_project_id,
                        "project_name": "Agentic Boilerplate",
                        "jira_project_key": "AGENT",
                        "repository": "example-org/agentic-boilerplate",
                        "inbox_root": str(agent_root.relative_to(data_root)),
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
