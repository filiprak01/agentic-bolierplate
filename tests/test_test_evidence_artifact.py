from agentic_boilerplate.domain import (
    EvidenceAcceptanceCriterion,
    EvidenceCommandOutput,
    EvidenceCriterionResult,
    EvidenceLinkedBug,
    TestEvidenceArtifact,
    TestEvidenceArtifactError,
    build_jira_evidence_comment_reference,
    build_test_evidence_path,
    redact_evidence_text,
    render_test_evidence_markdown,
)


def test_evidence_markdown_includes_required_audit_fields_and_redacts_secrets() -> None:
    artifact = TestEvidenceArtifact(
        jira_issue_key="AGENT-84",
        test_issue_key="AGENT-330",
        tester_role="Tester Agent",
        executed_at="2026-07-04T20:00:00Z",
        evidence_path="data/agent-logs/AGENT-84/test-evidence-20260704T200000Z.md",
        acceptance_criteria=(
            EvidenceAcceptanceCriterion(
                text="Evidence artifact schema includes audit fields.",
                result=EvidenceCriterionResult.PASSED,
                notes="token=abc123 was available in env",
            ),
        ),
        commands=(
            EvidenceCommandOutput(
                command="PYTHONPATH=src python -m pytest -q tests/test_test_evidence_artifact.py",
                output="Authorization: Bearer secret-token\n1 passed",
            ),
        ),
        linked_bugs=(EvidenceLinkedBug("AGENT-331", "Evidence bug"),),
    )

    markdown = render_test_evidence_markdown(artifact)

    assert "# Test Evidence - AGENT-84" in markdown
    assert "Test Case: AGENT-330" in markdown
    assert "Tester role: Tester Agent" in markdown
    assert "Evidence artifact schema includes audit fields." in markdown
    assert "token=[REDACTED]" in markdown
    assert "Bearer [REDACTED]" in markdown
    assert "secret-token" not in markdown
    assert "AGENT-331: Evidence bug" in markdown


def test_evidence_path_is_deterministic_per_story_and_timestamp() -> None:
    path = build_test_evidence_path(
        root="data/agent-logs",
        jira_issue_key="AGENT-84",
        timestamp="20260704T200000Z",
    )

    assert path.root == "data/agent-logs"
    assert path.issue_key == "AGENT-84"
    assert path.filename == "test-evidence-20260704T200000Z.md"
    assert path.path == "data/agent-logs/AGENT-84/test-evidence-20260704T200000Z.md"


def test_jira_comment_reference_can_be_prepared_without_live_jira() -> None:
    artifact = TestEvidenceArtifact(
        jira_issue_key="AGENT-84",
        test_issue_key="AGENT-330",
        tester_role="Tester Agent",
        executed_at="2026-07-04T20:00:00Z",
        evidence_path="data/agent-logs/AGENT-84/test-evidence-20260704T200000Z.md",
        acceptance_criteria=(
            EvidenceAcceptanceCriterion(
                text="Evidence writer can prepare comment references.",
                result=EvidenceCriterionResult.PASSED,
            ),
        ),
        commands=(),
    )

    reference = build_jira_evidence_comment_reference(artifact)

    assert reference.issue_key == "AGENT-84"
    assert reference.test_issue_key == "AGENT-330"
    assert reference.summary == (
        "Tester evidence PASSED: data/agent-logs/AGENT-84/test-evidence-20260704T200000Z.md"
    )


def test_concise_jira_only_evidence_allows_simple_story_without_criteria() -> None:
    artifact = TestEvidenceArtifact(
        jira_issue_key="AGENT-1",
        test_issue_key="AGENT-2",
        tester_role="Tester Agent",
        executed_at="2026-07-04T20:00:00Z",
        evidence_path="jira://AGENT-1/comment",
        acceptance_criteria=(),
        commands=(),
        concise_jira_only=True,
    )

    markdown = render_test_evidence_markdown(artifact)

    assert "Concise Jira-only evidence configured." in markdown


def test_non_simple_evidence_requires_acceptance_criteria() -> None:
    try:
        render_test_evidence_markdown(
            TestEvidenceArtifact(
                jira_issue_key="AGENT-84",
                test_issue_key="AGENT-330",
                tester_role="Tester Agent",
                executed_at="2026-07-04T20:00:00Z",
                evidence_path="data/agent-logs/AGENT-84/test-evidence-20260704T200000Z.md",
                acceptance_criteria=(),
                commands=(),
            )
        )
    except TestEvidenceArtifactError as error:
        assert "acceptance_criteria is required" in str(error)
    else:
        raise AssertionError("Expected non-simple evidence without criteria to fail")


def test_redaction_covers_common_secret_shapes() -> None:
    text = "password: p4ss\napi_key=abc\nBearer xyz"

    redacted = redact_evidence_text(text)

    assert "p4ss" not in redacted
    assert "abc" not in redacted
    assert "xyz" not in redacted
    assert redacted.count("[REDACTED]") == 3
