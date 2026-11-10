from pathlib import Path


def _guide(project_root: Path) -> str:
    return (project_root / "docs" / "session-mode-delivery-flow-validation.md").read_text(
        encoding="utf-8"
    )


def test_delivery_flow_validation_links_delivery_role_workflows(project_root: Path) -> None:
    guide = _guide(project_root)

    required_references = (
        "docs/session-mode-validation-playbook.md",
        "docs/session-mode-planning-handoff-validation.md",
        "docs/developer-subtask-workflow.md",
        "docs/review-agent-pr-workflow.md",
        "docs/tester-manual-test-workflow.md",
        "docs/tester-bug-retest-workflow.md",
        "docs/sprint-regression-overview-workflow.md",
        "docs/sprint-closure-publication-workflow.md",
        "docs/devsecops-preflight-checklist.md",
    )

    for reference in required_references:
        assert reference in guide


def test_delivery_flow_validation_starts_developer_from_approved_jira_story(
    project_root: Path,
) -> None:
    guide = _guide(project_root)

    assert "approved Jira Story or Bug in `READY TO START`" in guide
    assert "Checks dependency eligibility and Codex limits before implementation" in guide
    assert "Creates visible Jira subtasks before changing files" in guide
    assert "feature/{JIRA_KEY}-{short-slug}" in guide
    assert "Moves the parent issue to `DEV COMPLETED`" in guide


def test_delivery_flow_validation_requires_diff_first_review(project_root: Path) -> None:
    guide = _guide(project_root)

    assert "Reviews the pull request diff first" in guide
    assert "Verifies validation evidence and Jira pull request visibility" in guide
    assert "Checks mergeability and conflict status" in guide
    assert "Merges only after review findings, checks, and conflicts are clean" in guide


def test_delivery_flow_validation_tests_after_merge_and_records_evidence(
    project_root: Path,
) -> None:
    guide = _guide(project_root)

    assert "Starts only after the story is merged to `main`" in guide
    assert "Moves the story to `IN TESTING`" in guide
    assert "Tests each acceptance criterion" in guide
    assert "data/agent-logs/<JIRA_ISSUE>/" in guide
    assert "Moves the story to `TEST COMPLETED`" in guide


def test_delivery_flow_validation_covers_release_manager_regression_and_closure(
    project_root: Path,
) -> None:
    guide = _guide(project_root)

    assert "Builds regression scope from reusable Test issues and changed behavior" in guide
    assert "Runs or records sprint regression evidence" in guide
    assert "Creates closure notes with delivered scope" in guide
    assert "Closes the sprint only after tested scope" in guide


def test_delivery_flow_validation_routes_bugs_po_questions_and_future_requirements(
    project_root: Path,
) -> None:
    guide = _guide(project_root)

    required_phrases = (
        "Tester-created bugs link to the failed story and Test issue",
        "Failed stories move back to `DEV COMPLETED`",
        "Product questions are written to the durable PO inbox",
        "Release 1.1 fix",
        "Release 1.2 Docker requirement",
        "FUNNEL",
    )

    for phrase in required_phrases:
        assert phrase in guide


def test_delivery_flow_validation_requires_devsecops_preflight_for_sensitive_work(
    project_root: Path,
) -> None:
    guide = _guide(project_root)

    required_phrases = (
        "DevSecOps preflight is complete",
        "auth/session ownership",
        "upload/file-processing",
        "persistence, secrets, deployment",
        "provider review, logs, exports, backups, or cleanup",
        "Security routing is required",
        "synthetic/redacted-data-only",
        "no permanent original document storage",
        "no document-content logging",
        "no full-filename logging",
        "Product Owner explicitly approves",
    )

    for phrase in required_phrases:
        assert phrase in guide
