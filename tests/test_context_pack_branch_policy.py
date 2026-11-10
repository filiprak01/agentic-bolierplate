from agentic_boilerplate.domain.context_pack_branch_policy import (
    ContextBranchClass,
    ContextPackReference,
    ContextPackValidationIssueKind,
    ContextSourceDocument,
    classify_context_branch,
    context_branch_name,
    is_delivery_visible_in_jira,
    redact_context_pack_text,
    render_context_pack_artifact_note,
    validate_context_pack_reference,
)


def test_branch_classification_distinguishes_delivery_and_non_delivery_work() -> None:
    feature = classify_context_branch("feature/AGENT-1014-context-branch-policy")
    context = classify_context_branch("context/AGENT/developer/sprint-r12-s8")
    docs = classify_context_branch("docs/release-1.2.0")
    process = classify_context_branch("process/AGENT-1050-ci-check-gate")

    assert feature.branch_class is ContextBranchClass.DELIVERY
    assert context.branch_class is ContextBranchClass.CONTEXT
    assert docs.branch_class is ContextBranchClass.DOCS
    assert process.branch_class is ContextBranchClass.PROCESS
    assert is_delivery_visible_in_jira(feature.branch_name) is True
    assert is_delivery_visible_in_jira(context.branch_name) is False
    assert is_delivery_visible_in_jira(docs.branch_name) is False
    assert is_delivery_visible_in_jira(process.branch_name) is True


def test_context_branch_builder_normalizes_project_role_and_scope() -> None:
    assert context_branch_name("ap", "docs_confluence", "Sprint R12 S8") == "context/AP/docs-confluence/sprint-r12-s8"


def test_context_pack_reference_allows_current_project_context_ref() -> None:
    reference = ContextPackReference(
        project_key="AGENT",
        agent_role="developer",
        sprint_or_story="sprint-r12-s8",
        branch_name="context/AGENT/developer/sprint-r12-s8",
        revision="96545f539ac789bd41c66972ea6ad3c17fce5d9c",
        context_pack_hash="sha256:context-pack-hash",
        generated_from_main_sha="96545f539ac789bd41c66972ea6ad3c17fce5d9c",
        source_documents=(
            ContextSourceDocument(
                path="docs/context-pack-generator.md",
                description="Approved context pack rules.",
                project_key="AGENT",
            ),
        ),
    )

    result = validate_context_pack_reference(
        reference,
        current_main_sha="96545f539ac789bd41c66972ea6ad3c17fce5d9c",
    )

    assert result.allowed is True
    assert result.issues == ()
    assert "context/AGENT/developer/sprint-r12-s8" in render_context_pack_artifact_note(reference)


def test_context_pack_reference_blocks_secret_and_unresolved_assumption() -> None:
    reference = ContextPackReference(
        project_key="AGENT",
        agent_role="developer",
        sprint_or_story="sprint-r12-s8",
        branch_name="context/AGENT/developer/sprint-r12-s8",
        revision="96545f5",
        context_pack_hash="sha256:context-pack-hash",
        generated_from_main_sha="96545f5",
        source_documents=(
            ContextSourceDocument(
                path="docs/product.md",
                description="token=" + "gh" + "p_exampleSecretValue123456",
                project_key="AGENT",
            ),
        ),
        unresolved_assumptions=("Need PO to confirm final host path.",),
    )

    result = validate_context_pack_reference(reference)

    assert result.allowed is False
    assert {issue.kind for issue in result.issues} == {
        ContextPackValidationIssueKind.SECRET_LIKE_CONTENT,
        ContextPackValidationIssueKind.UNRESOLVED_ASSUMPTION,
    }
    assert redact_context_pack_text("token=" + "gh" + "p_exampleSecretValue123456") == "token=<redacted>"


def test_context_pack_redacts_standalone_github_token() -> None:
    text = "Use " + "github_" + "pat_exampleSecretValue1234567890 only in local env."

    assert redact_context_pack_text(text) == "Use <redacted> only in local env."


def test_context_pack_reference_detects_stale_context_and_cross_project_memory() -> None:
    reference = ContextPackReference(
        project_key="AGENT",
        agent_role="tester",
        sprint_or_story="sprint-r12-s8",
        branch_name="context/AP/tester/sprint-r12-s8",
        revision="96545f539ac789bd41c66972ea6ad3c17fce5d9c",
        context_pack_hash="sha256:context-pack-hash",
        generated_from_main_sha="96545f539ac789bd41c66972ea6ad3c17fce5d9c",
        source_documents=(
            ContextSourceDocument(
                path="docs/ap-only.md",
                description="AP-specific source doc.",
                project_key="AP",
            ),
        ),
        memory_project_key="AP",
    )

    result = validate_context_pack_reference(
        reference,
        current_main_sha="e97d1dc7277f1b1fad2d13eb59b251a702187e93",
    )

    assert result.allowed is False
    assert ContextPackValidationIssueKind.PROJECT_MISMATCH in {issue.kind for issue in result.issues}
    assert ContextPackValidationIssueKind.STALE_CONTEXT in {issue.kind for issue in result.issues}
    assert ContextPackValidationIssueKind.CROSS_PROJECT_MEMORY in {issue.kind for issue in result.issues}


def test_context_pack_reference_requires_context_branch_revision_hash_and_sources() -> None:
    reference = ContextPackReference(
        project_key="AGENT",
        agent_role="developer",
        sprint_or_story="sprint-r12-s8",
        branch_name="feature/AGENT-1014-context-branch-policy",
        revision="main",
        context_pack_hash="",
        generated_from_main_sha="",
        source_documents=(),
    )

    result = validate_context_pack_reference(reference)

    assert result.allowed is False
    assert {issue.kind for issue in result.issues} == {
        ContextPackValidationIssueKind.INVALID_BRANCH,
        ContextPackValidationIssueKind.MISSING_REVISION,
        ContextPackValidationIssueKind.MISSING_BASELINE_REVISION,
        ContextPackValidationIssueKind.MISSING_CONTEXT_HASH,
        ContextPackValidationIssueKind.MISSING_SOURCE_DOCUMENT,
    }
