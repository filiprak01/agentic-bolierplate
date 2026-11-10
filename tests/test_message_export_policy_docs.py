from pathlib import Path


def test_message_export_policy_doc_covers_story_acceptance_criteria() -> None:
    text = Path("docs/message-retention-redaction-export-policy.md").read_text()
    lower_text = text.lower()

    for required in [
        "Local durable store",
        "Confluence summary",
        "JSON export",
        "Archive terminal",
        "Tokens, credentials, passwords",
        "Database URLs",
        "Every exported message payload must include explicit project identity",
        "warn before exporting message data",
        "agent communication channel",
        "PO-to-agent message",
    ]:
        assert required in text
    assert "unsafe local absolute paths" in lower_text


def test_existing_message_surfaces_reference_export_policy() -> None:
    policy_path = "docs/message-retention-redaction-export-policy.md"

    for path in [
        "docs/po-inbox-schema.md",
        "docs/operator-ui.md",
        "docs/orchestration-event-queue.md",
    ]:
        assert policy_path in Path(path).read_text()
