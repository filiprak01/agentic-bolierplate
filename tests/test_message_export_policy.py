from agentic_boilerplate.domain import (
    MessagePublicationChannel,
    MessageRecordCategory,
    MessageRetentionAction,
    MessageSensitivityKind,
    evaluate_message_export_policy,
    find_message_export_sensitivity,
    format_message_export_policy_findings,
    redact_message_export_payload,
    retention_action_for_message_status,
)


def test_safe_po_inbox_export_keeps_project_identity_and_warns_for_json_export() -> None:
    decision = evaluate_message_export_policy(
        payload={
            "project_id": "AP",
            "message_type": "blocking_question",
            "message": "Should sprint scope include the UI design gate?",
        },
        category=MessageRecordCategory.PO_INBOX_ITEM,
        status="open",
        active_project_id="AP",
    )

    assert decision.allowed is True
    assert decision.requires_warning is True
    assert MessagePublicationChannel.JSON_EXPORT in decision.channels
    assert decision.retention_action is MessageRetentionAction.KEEP_ACTIVE
    assert decision.findings == ()


def test_policy_finds_and_redacts_secret_fields_values_paths_and_database_urls() -> None:
    payload = {
        "project_id": "AP",
        "github_token": "github_" "pat_abcdefghijklmnopqrstuvwxyz1234567890",
        "message": "Use postgresql://user:pass@localhost:5432/app for local testing.",
        "context_pack_path": "/home/user/business/private-project/data/context.json",
        "nested": {"ssh_key": "-----BEGIN" " OPENSSH PRIVATE KEY-----"},
    }

    findings = find_message_export_sensitivity(payload=payload, active_project_id="AP")
    redacted = redact_message_export_payload(payload)
    rendered_findings = format_message_export_policy_findings(findings)

    assert {
        MessageSensitivityKind.SECRET_FIELD,
        MessageSensitivityKind.SECRET_VALUE,
        MessageSensitivityKind.DATABASE_URL,
        MessageSensitivityKind.UNSAFE_ABSOLUTE_PATH,
    }.issubset({finding.kind for finding in findings})
    assert redacted["github_token"] == "[redacted]"
    assert "postgresql://user:pass" not in redacted["message"]
    assert "/home/user" not in redacted["context_pack_path"]
    assert redacted["nested"]["ssh_key"] == "[redacted]"
    assert "github_pat_" not in rendered_findings
    assert "postgresql://user:pass" not in rendered_findings


def test_multi_project_exports_require_matching_project_identity() -> None:
    missing = evaluate_message_export_policy(
        payload={"message": "Missing project id."},
        category=MessageRecordCategory.AGENT_MESSAGE,
        status="answered",
        active_project_id="AP",
    )
    mismatched = evaluate_message_export_policy(
        payload={"project_id": "OTHER", "message": "Wrong project."},
        category=MessageRecordCategory.AGENT_MESSAGE,
        status="answered",
        active_project_id="AP",
        allowed_project_ids=("AP",),
    )
    allowed = evaluate_message_export_policy(
        payload={"project_id": "OTHER", "message": "Part of an approved multi-project export."},
        category=MessageRecordCategory.AGENT_MESSAGE,
        status="answered",
        active_project_id="AP",
        allowed_project_ids=("AP", "OTHER"),
    )

    assert missing.allowed is False
    assert missing.findings[0].kind is MessageSensitivityKind.MISSING_PROJECT_IDENTITY
    assert mismatched.allowed is False
    assert mismatched.findings[0].kind is MessageSensitivityKind.PROJECT_IDENTITY_MISMATCH
    assert allowed.allowed is True


def test_retention_status_defaults_are_explicit() -> None:
    assert retention_action_for_message_status("open") is MessageRetentionAction.KEEP_ACTIVE
    assert retention_action_for_message_status("accepted/done") is MessageRetentionAction.ARCHIVE_TERMINAL
    assert retention_action_for_message_status("stale") is MessageRetentionAction.REVIEW_STALE
    assert retention_action_for_message_status("custom") is MessageRetentionAction.KEEP_LOCAL_ONLY


def test_secret_field_detection_does_not_flag_normal_author_metadata() -> None:
    findings = find_message_export_sensitivity(
        payload={"project_id": "AP", "author": "planner", "message": "Looks good."},
        active_project_id="AP",
    )

    assert findings == ()
