from pathlib import Path

import pytest

from agentic_boilerplate.domain import (
    AgentRole,
    INBOX_STATUS_FOLDER_NAMES,
    InboxAuditEvent,
    InboxMessageType,
    InboxOption,
    InboxSchemaError,
    InboxStatus,
    POInboxItem,
    inbox_item_from_dict,
    inbox_item_to_dict,
    require_valid_inbox_item,
    validate_inbox_item,
)


def test_blocking_question_schema_round_trips_to_json_compatible_data() -> None:
    item = POInboxItem(
        id="inbox-001",
        message_type=InboxMessageType.BLOCKING_QUESTION,
        status=InboxStatus.OPEN,
        title="Choose Jira approval behavior",
        message="Should generated stories be created in Jira immediately?",
        agent_role=AgentRole.PRODUCT_PLANNING,
        created_at="2026-06-05T16:30:00Z",
        agent_id="planner-1",
        jira_issue_key="AGENT-12",
        project_id="agentic-boilerplate",
        project_name="Agentic Boilerplate",
        project_root="/home/user/business/agentic-bolierplate",
        repository="example-org/agentic-boilerplate",
        jira_project_key="AGENT",
        confluence_page_id="458864",
        context_pack_path="data/context-packs/AGENT-12/context.json",
        business_impact="Controls Product Owner review effort before execution.",
        recommendation="Create stories in FUNNEL and let PO move them to READY TO START.",
        options=(
            InboxOption(
                id="funnel",
                label="Create in FUNNEL",
                description="Keeps PO approval explicit.",
            ),
            InboxOption(
                id="local-draft",
                label="Local draft only",
                description="Defers Jira creation.",
            ),
        ),
        audit=(
            InboxAuditEvent(
                timestamp="2026-06-05T16:30:00Z",
                actor="planner-1",
                action="created",
            ),
        ),
    )

    require_valid_inbox_item(item)
    data = inbox_item_to_dict(item)
    restored = inbox_item_from_dict(data)

    assert data["message_type"] == "blocking_question"
    assert data["status"] == "open"
    assert data["project_id"] == "agentic-boilerplate"
    assert data["repository"] == "example-org/agentic-boilerplate"
    assert data["options"][0]["id"] == "funnel"
    assert restored == item


@pytest.mark.parametrize(
    ("message_type", "status"),
    [
        (InboxMessageType.BLOCKING_QUESTION, InboxStatus.APPROVED),
        (InboxMessageType.FYI, InboxStatus.ANSWERED),
        (InboxMessageType.APPROVAL_REQUEST, InboxStatus.ANSWERED),
    ],
)
def test_message_type_status_combinations_are_validated(
    message_type: InboxMessageType,
    status: InboxStatus,
) -> None:
    item = _base_item(message_type=message_type, status=status)

    issues = validate_inbox_item(item)

    assert any(issue.field == "status" for issue in issues)


def test_terminal_status_requires_answer_and_timestamp() -> None:
    item = _base_item(
        message_type=InboxMessageType.APPROVAL_REQUEST,
        status=InboxStatus.APPROVED,
        answer="Approved for MVP.",
    )

    issues = validate_inbox_item(item)

    assert {issue.field for issue in issues} == {"answered_at"}


def test_open_status_rejects_answer_values() -> None:
    item = _base_item(
        message_type=InboxMessageType.BLOCKING_QUESTION,
        status=InboxStatus.OPEN,
        answer="This value should not exist yet.",
        answered_at="2026-06-05T16:40:00Z",
    )

    issues = validate_inbox_item(item)

    assert any(issue.field == "status" for issue in issues)


def test_required_fields_and_duplicate_options_are_reported_without_answer_content() -> None:
    item = POInboxItem(
        id="",
        message_type=InboxMessageType.BLOCKING_QUESTION,
        status=InboxStatus.ANSWERED,
        title="",
        message="",
        agent_role=AgentRole.ARCHITECTURE,
        created_at="",
        options=(
            InboxOption(id="same", label="First"),
            InboxOption(id="same", label="Second"),
        ),
        answer="Sensitive Product Owner answer.",
    )

    with pytest.raises(InboxSchemaError) as exc_info:
        require_valid_inbox_item(item)

    message = str(exc_info.value)
    assert "id" in message
    assert "title" in message
    assert "business_impact" in message
    assert "recommendation" in message
    assert "options" in message
    assert "Sensitive Product Owner answer" not in message


def test_unknown_enum_value_fails_during_dict_loading() -> None:
    data = inbox_item_to_dict(_base_item())
    data["message_type"] = "unknown"

    with pytest.raises(InboxSchemaError, match="Unsupported value"):
        inbox_item_from_dict(data)


def test_null_required_values_are_treated_as_missing_during_dict_loading() -> None:
    data = inbox_item_to_dict(_base_item())
    data["id"] = None
    data["title"] = None

    with pytest.raises(InboxSchemaError) as exc_info:
        inbox_item_from_dict(data)

    fields = {issue.field for issue in exc_info.value.issues}
    assert fields == {"id", "title"}


def test_status_folder_mapping_supports_all_statuses() -> None:
    assert INBOX_STATUS_FOLDER_NAMES == {
        InboxStatus.OPEN: "open",
        InboxStatus.ANSWERED: "answered",
        InboxStatus.APPROVED: "approved",
        InboxStatus.REJECTED: "rejected",
        InboxStatus.ARCHIVED: "archived",
    }


def test_legacy_inbox_records_without_project_identity_still_load() -> None:
    data = inbox_item_to_dict(_base_item())
    for key in ("project_id", "project_name", "project_root", "repository", "jira_project_key"):
        data.pop(key)

    restored = inbox_item_from_dict(data)

    assert restored.project_id == ""
    assert restored.project_name == ""
    assert restored.project_root == ""
    assert restored.repository == ""
    assert restored.jira_project_key == ""


def test_po_inbox_schema_documents_export_envelope() -> None:
    text = Path("docs/po-inbox-schema.md").read_text(encoding="utf-8")

    assert "Export Envelope" in text
    assert "po-inbox-export/v1" in text
    assert "scope" in text
    assert "project" in text
    assert "all_projects" in text
    assert "composite_id" in text
    assert "must not change inbox item status or audit history" in text


def _base_item(
    *,
    message_type: InboxMessageType = InboxMessageType.BLOCKING_QUESTION,
    status: InboxStatus = InboxStatus.OPEN,
    answer: str = "",
    answered_at: str = "",
) -> POInboxItem:
    return POInboxItem(
        id="inbox-001",
        message_type=message_type,
        status=status,
        title="Need PO decision",
        message="Please choose the delivery path.",
        agent_role=AgentRole.PRODUCT_PLANNING,
        created_at="2026-06-05T16:30:00Z",
        business_impact="Avoids hidden business assumptions.",
        recommendation="Use explicit PO approval.",
        answer=answer,
        answered_at=answered_at,
    )
