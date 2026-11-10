from pathlib import Path


NOTES = Path("docs/release-notes/release-1.1.0.md")
REGRESSION = Path("docs/release-notes/release-1.1.0-regression-scope.md")
RETRO = Path("docs/release-notes/release-1.1.0-retro-and-r12-followups.md")
APPROVAL = Path("docs/release-notes/release-1.1.0-po-approval-report.md")


def _read(project_root: Path, path: Path) -> str:
    return (project_root / path).read_text(encoding="utf-8")


def test_release_1_1_notes_summarize_completed_and_excluded_work(project_root: Path) -> None:
    text = _read(project_root, NOTES)

    for key in ("AGENT-424", "AGENT-438", "AGENT-442", "AGENT-452", "AGENT-548"):
        assert key in text

    for deferred in ("AGENT-446", "AGENT-448", "AGENT-449", "AGENT-466", "AGENT-467"):
        assert deferred in text

    assert "Excluded Or Deferred Work" in text
    assert "Unapproved Funnel items are listed as excluded work" in text


def test_release_1_1_regression_scope_covers_required_areas(project_root: Path) -> None:
    text = _read(project_root, REGRESSION)

    required_areas = (
        "PO inbox",
        "First-project setup validation",
        "Codex limit",
        "Role instruction files",
        "Docker worker requirements",
        "secret redaction",
        "sprint closure automation",
    )

    for area in required_areas:
        assert area in text

    assert "Full Python suite: 616 passed" in text


def test_release_1_1_retro_feeds_release_1_2_docker_automation(project_root: Path) -> None:
    text = _read(project_root, RETRO)

    assert "Release 1.2 Docker Automation Candidates" in text
    assert "Detached worker trigger handoff" in text
    assert "Automatic wait/resume scheduling" in text
    assert "Assignment lock implementation" in text
    assert "Multi-project operator inbox" in text


def test_release_1_1_po_approval_report_is_confluence_ready(project_root: Path) -> None:
    text = _read(project_root, APPROVAL)

    assert "Confluence-ready approval summary" in text
    assert "Approve Release 1.1.0 scope as a whole" in text
    assert "Delivered Value" in text
    assert "Evidence To Review" in text
    assert "Product Owner Decision" in text


def test_release_1_1_dependency_gate_summary_keeps_closure_last(project_root: Path) -> None:
    text = _read(project_root, NOTES)

    assert "R11-S31 is release closure and must be last" in text
    assert "R11-S19 precedes session-mode validation stories" in text
    assert "R11-S24 precedes any future lock implementation" in text
