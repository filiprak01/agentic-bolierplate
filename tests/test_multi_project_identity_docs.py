from pathlib import Path


def test_multi_project_identity_doc_defines_fields_and_filters() -> None:
    text = Path("docs/multi-project-identity.md").read_text()

    for required in [
        "project_id",
        "project_name",
        "project_root",
        "repository",
        "jira_project_key",
        "agentic po-inbox list --project-id AP",
        "agentic worker status --project-id AP",
        "agentic orchestration-events list --project-id AP",
        "GET /po-inbox?status=open&project_id=AP",
        "Existing single-project records",
    ]:
        assert required in text


def test_project_identity_policy_is_referenced_by_message_surfaces() -> None:
    for path in [
        "docs/po-inbox-schema.md",
        "docs/po-inbox-api.md",
        "docs/orchestration-event-queue.md",
    ]:
        assert "docs/multi-project-identity.md" in Path(path).read_text()
