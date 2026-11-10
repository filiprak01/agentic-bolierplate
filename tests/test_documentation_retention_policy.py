import pytest

from agentic_boilerplate.domain import (
    DocumentationArtifactKind,
    DocumentationRetentionDisposition,
    DocumentationRetentionInput,
    decide_documentation_retention,
)


def test_approved_shared_source_stays_in_repo_and_can_publish() -> None:
    decision = decide_documentation_retention(
        DocumentationRetentionInput(
            path="docs/operator-guide.md",
            artifact_kind=DocumentationArtifactKind.SHARED_SOURCE,
            approved=True,
        )
    )

    assert decision.disposition is DocumentationRetentionDisposition.KEEP_IN_REPO
    assert decision.repo_allowed is True
    assert decision.publish_allowed is True
    assert decision.recommended_target == "docs/"


def test_role_notes_and_raw_logs_stay_local_only() -> None:
    role_note = decide_documentation_retention(
        DocumentationRetentionInput(
            path="data/role-notes/developer/note.md",
            artifact_kind=DocumentationArtifactKind.ROLE_NOTE,
            approved=True,
        )
    )
    raw_log = decide_documentation_retention(
        DocumentationRetentionInput(
            path="data/agent-logs/AGENT-1/raw.log",
            artifact_kind=DocumentationArtifactKind.RAW_LOG,
            approved=True,
        )
    )

    assert role_note.disposition is DocumentationRetentionDisposition.LOCAL_DURABLE_ONLY
    assert raw_log.disposition is DocumentationRetentionDisposition.LOCAL_DURABLE_ONLY
    assert role_note.repo_allowed is False
    assert raw_log.publish_allowed is False


def test_report_artifacts_publish_only_after_approval_and_release_relevance() -> None:
    draft = decide_documentation_retention(
        DocumentationRetentionInput(
            path="data/agent-logs/SPRINT-6/regression.md",
            artifact_kind=DocumentationArtifactKind.REPORT_ARTIFACT,
            approved=False,
            release_relevant=True,
        )
    )
    approved = decide_documentation_retention(
        DocumentationRetentionInput(
            path="data/agent-logs/SPRINT-6/regression.md",
            artifact_kind=DocumentationArtifactKind.REPORT_ARTIFACT,
            approved=True,
            release_relevant=True,
            partner_visible=True,
            optional_archive_enabled=True,
        )
    )

    assert draft.disposition is DocumentationRetentionDisposition.LOCAL_DURABLE_ONLY
    assert approved.disposition is DocumentationRetentionDisposition.PUBLISH_TO_GITHUB_PAGES
    assert approved.repo_allowed is True
    assert approved.publish_allowed is True
    assert approved.optional_archive_allowed is True


def test_context_pack_repo_retention_requires_approval_and_release_relevance() -> None:
    working = decide_documentation_retention(
        DocumentationRetentionInput(
            path="data/context-packs/AGENT-1/context-pack.md",
            artifact_kind=DocumentationArtifactKind.CONTEXT_PACK,
            approved=True,
        )
    )
    release_context = decide_documentation_retention(
        DocumentationRetentionInput(
            path="docs/context-packs/AGENT-1.md",
            artifact_kind=DocumentationArtifactKind.CONTEXT_PACK,
            approved=True,
            release_relevant=True,
        )
    )

    assert working.disposition is DocumentationRetentionDisposition.LOCAL_DURABLE_ONLY
    assert release_context.disposition is DocumentationRetentionDisposition.KEEP_IN_REPO
    assert release_context.repo_allowed is True
    assert release_context.publish_allowed is False


def test_generated_site_and_secrets_are_not_repo_artifacts() -> None:
    generated = decide_documentation_retention(
        DocumentationRetentionInput(
            path="site/",
            artifact_kind=DocumentationArtifactKind.GENERATED_SITE,
            approved=True,
        )
    )
    secret = decide_documentation_retention(
        DocumentationRetentionInput(
            path=".env",
            artifact_kind=DocumentationArtifactKind.CREDENTIAL_OR_SECRET,
            approved=True,
        )
    )

    assert generated.disposition is DocumentationRetentionDisposition.REDACT_OR_GITIGNORE
    assert secret.disposition is DocumentationRetentionDisposition.REDACT_OR_GITIGNORE
    assert generated.repo_allowed is False
    assert secret.publish_allowed is False


def test_retention_input_requires_path() -> None:
    with pytest.raises(ValueError, match="path is required"):
        decide_documentation_retention(
            DocumentationRetentionInput(
                path=" ",
                artifact_kind=DocumentationArtifactKind.SHARED_SOURCE,
                approved=True,
            )
        )
