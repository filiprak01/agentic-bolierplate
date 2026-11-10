from pathlib import Path


def _handoff(project_root: Path) -> str:
    return (project_root / "docs" / "ui-v1-frontend-handoff.md").read_text(
        encoding="utf-8"
    )


def test_ui_v1_frontend_handoff_references_approved_sources(
    project_root: Path,
) -> None:
    handoff = _handoff(project_root)

    required_phrases = (
        "AP-71 - Define parsed, verified, and export data model requirements",
        "AP-73 - Create low-fidelity UI V1 wireframes for approved screens",
        "AP-74 - Create visual mockups for the first UI implementation slice",
        "AP-160 - Tested metric taxonomy and dashboard placement handoff",
        "04-release-scope/release-2-ui-v1-product-discovery.md",
        "03-nfr/ui-v1-privacy-security-product-requirements.md",
        "01-architecture/release-2-ui-v1-architecture-plan.md",
        "01-architecture/adr-002-ui-v1-parsed-verified-export-data-boundaries.md",
        "01-architecture/ui-v1-pdf-lifecycle-and-guest-ownership.md",
    )

    for phrase in required_phrases:
        assert phrase in handoff


def test_ui_v1_frontend_handoff_covers_required_acceptance_checklist(
    project_root: Path,
) -> None:
    handoff = _handoff(project_root)

    required_phrases = (
        "### Design Match",
        "### Responsive Requirements",
        "### Required State Coverage",
        "### Privacy And Copy Obligations",
        "### Accessibility Requirements",
        "Import / Parse:",
        "Parsed Summary:",
        "Delegation Editor:",
        "Export / Reports:",
        "320 CSS pixels and 200 percent zoom",
        "Every implementation story must include empty, loading, error, and success",
        "not affiliated with, endorsed",
        "operated by any airline or employer",
    )

    for phrase in required_phrases:
        assert phrase in handoff


def test_ui_v1_frontend_handoff_keeps_architecture_blockers_visible(
    project_root: Path,
) -> None:
    handoff = _handoff(project_root)

    required_phrases = (
        "## Architecture-Blocked Frontend Stories",
        "Upload API contract for guest mode",
        "Parser result contract for period/person summary",
        "Typed delegation row schema",
        "CSV/XLSX/PDF export API",
        "Authentication mode, account/session transfer contract",
        "Registered-user persistence model",
        "Hosting/provider decision",
        "No frontend implementation story should move to `READY TO START`",
    )

    for phrase in required_phrases:
        assert phrase in handoff


def test_ui_v1_frontend_handoff_preserves_v2_and_acceptance_trace(
    project_root: Path,
) -> None:
    handoff = _handoff(project_root)

    required_phrases = (
        "## V2 Or Later Candidates",
        "Full analytics Dashboard beyond AP-160 must-have metric placement",
        "Native Apple Numbers export",
        "Public launch, marketing pages, public demo mode, or public user profiles",
        "Payroll, allowance, entitlement, official accounting, contract",
        "R2-P1-S7-AC1",
        "R2-P1-S7-AC2",
        "R2-P1-S7-AC3",
        "R2-P1-S7-AC4",
    )

    for phrase in required_phrases:
        assert phrase in handoff
