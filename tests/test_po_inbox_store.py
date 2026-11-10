from pathlib import Path

import pytest

from agentic_boilerplate.domain import (
    AgentRole,
    InboxAuditEvent,
    InboxMessageType,
    InboxSchemaError,
    InboxStatus,
    POInboxItem,
)
from agentic_boilerplate.storage import (
    FilePOInboxStore,
    InboxItemAlreadyExistsError,
    InboxItemNotFoundError,
    InvalidInboxItemIdError,
    POInboxStoreError,
)


def test_store_creates_status_directories_in_schema_order(tmp_path: Path) -> None:
    store = FilePOInboxStore(tmp_path)

    directories = store.ensure_directories()

    assert [directory.name for directory in directories] == [
        "open",
        "answered",
        "approved",
        "rejected",
        "archived",
    ]
    assert all(directory.is_dir() for directory in directories)


def test_item_paths_are_deterministic(tmp_path: Path) -> None:
    store = FilePOInboxStore(tmp_path)

    path = store.item_path("question-001", InboxStatus.OPEN)

    assert path == tmp_path / "open" / "question-001.json"


def test_item_id_rejects_path_traversal(tmp_path: Path) -> None:
    store = FilePOInboxStore(tmp_path)

    with pytest.raises(InvalidInboxItemIdError):
        store.item_path("../escape", InboxStatus.OPEN)


def test_create_and_read_item_from_status_folder(tmp_path: Path) -> None:
    store = FilePOInboxStore(tmp_path)
    item = _open_question()

    location = store.create(item)
    restored = store.read(item.id)

    assert location.path == tmp_path / "open" / "question-001.json"
    assert restored == item


def test_list_items_returns_items_by_status_order(tmp_path: Path) -> None:
    store = FilePOInboxStore(tmp_path)
    store.create(_open_question())
    store.create(
        POInboxItem(
            id="fyi-001",
            message_type=InboxMessageType.FYI,
            status=InboxStatus.OPEN,
            title="Build finished",
            message="The worker finished a task.",
            agent_role=AgentRole.PLATFORM,
            created_at="2026-06-07T15:00:00Z",
        )
    )
    store.move("fyi-001", InboxStatus.ARCHIVED)

    all_items = store.list_items()
    archived_items = store.list_items(status=InboxStatus.ARCHIVED)

    assert [item.id for item in all_items] == ["question-001", "fyi-001"]
    assert [item.id for item in archived_items] == ["fyi-001"]


def test_list_items_can_filter_by_project_id(tmp_path: Path) -> None:
    store = FilePOInboxStore(tmp_path)
    store.create(POInboxItem(**{**_open_question().__dict__, "id": "ap-question", "project_id": "AP"}))
    store.create(POInboxItem(**{**_open_question().__dict__, "id": "agent-question", "project_id": "AGENT"}))

    assert [item.id for item in store.list_items(project_id="AP")] == ["ap-question"]
    assert [item.id for item in store.list_items(project_id="AGENT")] == ["agent-question"]


def test_create_rejects_duplicate_item_id_across_status_folders(tmp_path: Path) -> None:
    store = FilePOInboxStore(tmp_path)
    item = _open_question()
    store.create(item)

    answered = _answered_question()

    with pytest.raises(InboxItemAlreadyExistsError):
        store.create(answered)


def test_read_missing_item_raises_not_found(tmp_path: Path) -> None:
    store = FilePOInboxStore(tmp_path)

    with pytest.raises(InboxItemNotFoundError):
        store.read("missing")


def test_update_moves_item_between_status_folders_and_preserves_audit(tmp_path: Path) -> None:
    store = FilePOInboxStore(tmp_path)
    store.create(_open_question())

    location = store.update(
        "question-001",
        lambda item: POInboxItem(
            **{
                **item.__dict__,
                "status": InboxStatus.ANSWERED,
                "answer": "Use FUNNEL.",
                "answered_at": "2026-06-07T16:00:00Z",
                "audit": item.audit
                + (
                    InboxAuditEvent(
                        timestamp="2026-06-07T16:00:00Z",
                        actor="po",
                        action="answered",
                    ),
                ),
            }
        ),
    )

    restored = store.read("question-001")

    assert location.path == tmp_path / "answered" / "question-001.json"
    assert not (tmp_path / "open" / "question-001.json").exists()
    assert restored.status == InboxStatus.ANSWERED
    assert restored.answer == "Use FUNNEL."
    assert [event.action for event in restored.audit] == ["created", "answered"]


def test_move_changes_status_folder(tmp_path: Path) -> None:
    store = FilePOInboxStore(tmp_path)
    fyi = POInboxItem(
        id="fyi-001",
        message_type=InboxMessageType.FYI,
        status=InboxStatus.OPEN,
        title="Build finished",
        message="The worker finished a task.",
        agent_role=AgentRole.PLATFORM,
        created_at="2026-06-07T15:00:00Z",
    )
    store.create(fyi)

    location = store.move("fyi-001", InboxStatus.ARCHIVED)

    assert location.path == tmp_path / "archived" / "fyi-001.json"
    assert store.read("fyi-001").status == InboxStatus.ARCHIVED


def test_update_rejects_id_changes(tmp_path: Path) -> None:
    store = FilePOInboxStore(tmp_path)
    store.create(_open_question())

    with pytest.raises(POInboxStoreError):
        store.update("question-001", lambda item: POInboxItem(**{**item.__dict__, "id": "other"}))


def test_invalid_schema_file_is_rejected_on_read(tmp_path: Path) -> None:
    store = FilePOInboxStore(tmp_path)
    store.ensure_directories()
    (tmp_path / "open" / "bad.json").write_text('{"id":"bad"}', encoding="utf-8")

    with pytest.raises(InboxSchemaError):
        store.read("bad")


def _open_question() -> POInboxItem:
    return POInboxItem(
        id="question-001",
        message_type=InboxMessageType.BLOCKING_QUESTION,
        status=InboxStatus.OPEN,
        title="Choose approval behavior",
        message="Should stories be created in Jira?",
        agent_role=AgentRole.PRODUCT_PLANNING,
        created_at="2026-06-07T15:00:00Z",
        business_impact="Controls PO review flow.",
        recommendation="Create in FUNNEL.",
        audit=(
            InboxAuditEvent(
                timestamp="2026-06-07T15:00:00Z",
                actor="planner",
                action="created",
            ),
        ),
    )


def _answered_question() -> POInboxItem:
    return POInboxItem(
        **{
            **_open_question().__dict__,
            "status": InboxStatus.ANSWERED,
            "answer": "Create in FUNNEL.",
            "answered_at": "2026-06-07T16:00:00Z",
        }
    )
