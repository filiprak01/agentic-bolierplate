from pathlib import Path


def _checklist(project_root: Path) -> str:
    return (project_root / "docs" / "devsecops-preflight-checklist.md").read_text(
        encoding="utf-8"
    )


def test_devsecops_preflight_checklist_covers_triggering_work(project_root: Path) -> None:
    checklist = _checklist(project_root)

    required_phrases = (
        "Authentication, authorization, account linking, or session ownership",
        "Uploads, PDF parsing, file-processing, scratch files, or temporary storage",
        "Persistence, backups, exports, retention, deletion, or recovery behavior",
        "Secrets, credentials, provider integration, deployment, exposed ports",
        "Logs, evidence artifacts, diagnostics, support bundles",
    )

    for phrase in required_phrases:
        assert phrase in checklist


def test_devsecops_preflight_checklist_keeps_po_decisions_explicit(
    project_root: Path,
) -> None:
    checklist = _checklist(project_root)

    required_phrases = (
        "does not approve residual risk",
        "Create a PO inbox item and stop",
        "Real or customer-like data may be used",
        "Identity provider, auth mode, or session-transfer behavior is undecided",
        "Production deployment, public access, exposed port, provider, or paid",
        "Product Owner risk acceptance or compliance constraint is required",
    )

    for phrase in required_phrases:
        assert phrase in checklist


def test_devsecops_preflight_checklist_carries_r3_upload_handoff(
    project_root: Path,
) -> None:
    checklist = _checklist(project_root)

    required_phrases = (
        "`AP-68`, `AP-70`, and `AP-71`",
        "`AP-79` must carry these checks forward",
        "`AP-80` must carry these checks forward",
        "Exactly one owner: registered user id or guest session id",
        "Secure HTTP-only SameSite cookies",
        "No shared guest user",
        "No permanent original PDF storage",
        "Cleanup that is idempotent",
        "does not log document contents or full",
        "Synthetic/redacted-data-only",
    )

    for phrase in required_phrases:
        assert phrase in checklist


def test_devsecops_preflight_checklist_is_linked_from_roles_and_starters(
    project_root: Path,
) -> None:
    reference = "docs/devsecops-preflight-checklist.md"
    paths = (
        project_root / "ai_agents" / "roles" / "devops_platform.md",
        project_root / "ai_agents" / "roles" / "security.md",
        project_root / "ai_agents" / "session_starters" / "README.md",
        project_root / "docs" / "session-mode-delivery-flow-validation.md",
    )

    for path in paths:
        assert reference in path.read_text(encoding="utf-8")
