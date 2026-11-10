from pathlib import Path


DESIGN_DOC = Path("docs/design/codex-limits-form-design.md")
DESIGN_HTML = Path("docs/design/codex-limits-form-options.html")


def test_codex_limits_design_documents_selected_option_and_reference() -> None:
    text = DESIGN_DOC.read_text(encoding="utf-8")

    assert "AGENT-670" in text
    assert "Implementation reference: `AGENT-664`" in text
    assert (
        "Selected option: Option A - Adaptive Limit Windows With Atomic Save Panel"
        in text
    )
    assert "Design Reference:" in text
    assert "Product Owner sprint execution override" in text


def test_codex_limits_design_covers_single_and_multi_window_models() -> None:
    text = DESIGN_DOC.read_text(encoding="utf-8")

    for phrase in (
        "one combined subscription limit",
        "separate short and broad quota windows",
        "Current plan",
        "Short window",
        "Broad window",
        "single-pool Pro behavior",
    ):
        assert phrase in text


def test_codex_limits_design_covers_required_form_states() -> None:
    text = DESIGN_DOC.read_text(encoding="utf-8")

    for phrase in (
        "Status selector",
        "Used percentage numeric input",
        "Reset datetime input",
        "Cutoff percentage numeric input",
        "Save all rows atomically",
        "Stale record",
        "Unknown window",
        "Save failure",
        "without secrets or local paths",
    ):
        assert phrase in text


def test_codex_limits_design_html_contains_review_options_and_states() -> None:
    text = DESIGN_HTML.read_text(encoding="utf-8")

    for phrase in (
        "Option A - Adaptive Limit Windows With Atomic Save Panel",
        "Option B - Split Summary And Wizard",
        "Current plan",
        "Short window",
        "Unknown window",
        "Atomic update",
        "Save limit record",
        "Loading",
        "Validation error",
    ):
        assert phrase in text


def test_codex_limits_design_artifacts_are_ascii_safe() -> None:
    for path in (DESIGN_DOC, DESIGN_HTML):
        path.read_text(encoding="ascii")
