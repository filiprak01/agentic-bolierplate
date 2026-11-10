from pathlib import Path


DESIGN_DOC = Path("docs/design/worker-dashboard-assignment-visibility-design.md")
DESIGN_HTML = Path("docs/design/worker-dashboard-assignment-visibility-options.html")


def test_worker_dashboard_design_documents_selected_option_and_references() -> None:
    text = DESIGN_DOC.read_text(encoding="utf-8")

    assert "AGENT-671" in text
    assert "Implementation references: `AGENT-638`, `AGENT-675`, `AGENT-676`, `AGENT-679`" in text
    assert "Selected option: Option A - Split Dashboard With Lifecycle Rail And Timeline" in text
    assert "Design Reference:" in text
    assert "Product Owner sprint execution override" in text


def test_worker_dashboard_design_covers_assignment_and_lifecycle_states() -> None:
    text = DESIGN_DOC.read_text(encoding="utf-8")

    for phrase in (
        "Active worker",
        "Blocked assignment",
        "Waiting for PO",
        "Waiting for dependency",
        "Waiting for limit capacity",
        "Failed assignment",
        "Completed assignment",
        "Resumed assignment",
        "Stale lock",
        "Next expected step",
        "Skipped/not applicable",
        "Blocked/stuck",
    ):
        assert phrase in text


def test_worker_dashboard_design_covers_timeline_graph_and_artifacts() -> None:
    text = DESIGN_DOC.read_text(encoding="utf-8")

    for phrase in (
        "Orchestrator `resume_request`",
        "refused to resume",
        "PO inbox question",
        "Required node types",
        "Required edge labels",
        "Pull request",
        "Test evidence file",
        "AgileTest record",
        "PO inbox item",
    ):
        assert phrase in text


def test_worker_dashboard_html_contains_reviewable_layout_terms() -> None:
    text = DESIGN_HTML.read_text(encoding="utf-8")

    for phrase in (
        "Option A - Split Dashboard With Lifecycle Rail And Timeline",
        "Agent Status",
        "Assignments",
        "Lifecycle",
        "Timeline",
        "Graph",
        "Blocked/stuck",
        "Waiting for limit capacity",
        "Request worker resume",
        "Release stale lock",
    ):
        assert phrase in text


def test_worker_dashboard_design_artifacts_are_ascii_safe() -> None:
    for path in (DESIGN_DOC, DESIGN_HTML):
        path.read_text(encoding="ascii")
