"""Guided release intake readiness model."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from agentic_boilerplate.config import PlatformSettings
from agentic_boilerplate.domain.codex_limit_availability import (
    CodexLimitAvailabilityRecord,
    decide_codex_limit_gate,
)


RELEASE_INTAKE_SCHEMA_VERSION = "release-intake-report/v1"


class ReleaseIntakeCheckStatus(str, Enum):
    """Readiness state for one intake check."""

    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"


@dataclass(frozen=True)
class ReleaseIntakePath:
    """One operator-supplied path used by the release intake."""

    name: str
    path: Path
    purpose: str
    required: bool


@dataclass(frozen=True)
class ReleaseIntakeCheck:
    """One release intake readiness check."""

    name: str
    status: ReleaseIntakeCheckStatus
    message: str
    required: bool = True

    @property
    def blocks_readiness(self) -> bool:
        return self.required and self.status is ReleaseIntakeCheckStatus.FAILED


@dataclass(frozen=True)
class ReleaseIntakePOQuestion:
    """Actionable Product Owner/operator question produced by intake."""

    id: str
    title: str
    message: str
    business_impact: str
    recommendation: str
    related_check: str


@dataclass(frozen=True)
class ReleaseIntakeReport:
    """Durable release/project intake report."""

    schema_version: str
    project_id: str
    project_name: str
    release_id: str
    generated_at: str
    project_root: Path
    target_repository: str
    jira_project_key: str
    jira_board_id: str
    paths: tuple[ReleaseIntakePath, ...]
    checks: tuple[ReleaseIntakeCheck, ...]
    po_questions: tuple[ReleaseIntakePOQuestion, ...]

    @property
    def ready(self) -> bool:
        return not any(check.blocks_readiness for check in self.checks)


@dataclass(frozen=True)
class ReleaseIntakeInput:
    """Input values for a guided release intake."""

    project_id: str
    project_name: str
    release_id: str
    generated_at: str
    project_root: Path
    target_repository: str
    jira_project_key: str
    jira_board_id: str
    product_docs_root: Path
    architecture_root: Path
    evidence_root: Path
    durable_data_root: Path
    report_root: Path
    require_confluence: bool = False
    require_agiletest: bool = True


def build_release_intake_report(
    settings: PlatformSettings,
    intake: ReleaseIntakeInput,
    *,
    latest_limit_record: CodexLimitAvailabilityRecord | None = None,
) -> ReleaseIntakeReport:
    """Build a non-secret readiness report before creating project scope."""

    project_root = _resolve_path(intake.project_root, Path.cwd())
    paths = (
        ReleaseIntakePath(
            name="product_docs_root",
            path=_resolve_path(intake.product_docs_root, project_root),
            purpose="Product Owner source documents used by Product Planning and Architecture agents.",
            required=True,
        ),
        ReleaseIntakePath(
            name="architecture_root",
            path=_resolve_path(intake.architecture_root, project_root),
            purpose="Architecture inputs, decisions, NFRs, and generated architecture artifacts.",
            required=True,
        ),
        ReleaseIntakePath(
            name="evidence_root",
            path=_resolve_path(intake.evidence_root, project_root),
            purpose="Durable validation, test, regression, retro, and release evidence.",
            required=True,
        ),
        ReleaseIntakePath(
            name="durable_data_root",
            path=_resolve_path(intake.durable_data_root, project_root),
            purpose="Durable platform state shared by local workers and operator surfaces.",
            required=True,
        ),
        ReleaseIntakePath(
            name="report_root",
            path=_resolve_path(intake.report_root, project_root),
            purpose="Generated intake reports and associated operator handoff files.",
            required=True,
        ),
    )

    checks: list[ReleaseIntakeCheck] = []
    checks.append(_directory_check("project_root", project_root, "Project root exists."))
    checks.append(_repository_check(intake.target_repository))
    checks.extend(_jira_checks(intake.jira_project_key, intake.jira_board_id, settings))
    checks.extend(_confluence_checks(settings, required=intake.require_confluence))
    checks.extend(_agiletest_checks(settings, required=intake.require_agiletest))
    checks.extend(_path_checks(paths))
    checks.append(_product_docs_content_check(paths[0].path))
    checks.append(_architecture_content_check(paths[1].path))
    checks.append(
        _codex_limit_check(
            latest_limit_record,
            stale_after_seconds=settings.codex_limit_sentinel.stale_after_seconds,
            future_tolerance_seconds=settings.codex_limit_sentinel.future_tolerance_seconds,
        )
    )

    po_questions = tuple(
        _question_for_failed_check(
            check,
            project_id=intake.project_id,
            release_id=intake.release_id,
        )
        for check in checks
        if check.blocks_readiness
    )

    return ReleaseIntakeReport(
        schema_version=RELEASE_INTAKE_SCHEMA_VERSION,
        project_id=intake.project_id,
        project_name=intake.project_name,
        release_id=intake.release_id,
        generated_at=intake.generated_at,
        project_root=project_root,
        target_repository=intake.target_repository,
        jira_project_key=intake.jira_project_key,
        jira_board_id=intake.jira_board_id,
        paths=paths,
        checks=tuple(checks),
        po_questions=po_questions,
    )


def release_intake_report_to_dict(report: ReleaseIntakeReport) -> dict[str, Any]:
    """Convert the report into JSON-compatible data."""

    return {
        "schema_version": report.schema_version,
        "ready": report.ready,
        "project_id": report.project_id,
        "project_name": report.project_name,
        "release_id": report.release_id,
        "generated_at": report.generated_at,
        "project_root": str(report.project_root),
        "target_repository": report.target_repository,
        "jira_project_key": report.jira_project_key,
        "jira_board_id": report.jira_board_id,
        "paths": [
            {
                "name": path.name,
                "path": str(path.path),
                "purpose": path.purpose,
                "required": path.required,
            }
            for path in report.paths
        ],
        "checks": [
            {
                "name": check.name,
                "status": check.status.value,
                "required": check.required,
                "blocks_readiness": check.blocks_readiness,
                "message": check.message,
            }
            for check in report.checks
        ],
        "po_questions": [
            {
                "id": question.id,
                "title": question.title,
                "message": question.message,
                "business_impact": question.business_impact,
                "recommendation": question.recommendation,
                "related_check": question.related_check,
            }
            for question in report.po_questions
        ],
    }


def format_release_intake_report(report: ReleaseIntakeReport) -> str:
    """Format the report for CLI output and durable Markdown."""

    lines = [
        f"# Release Intake Report - {report.project_id} {report.release_id}",
        "",
        f"- Ready: {'yes' if report.ready else 'no'}",
        f"- Project: {report.project_name or report.project_id}",
        f"- Project root: `{report.project_root}`",
        f"- Target repository: `{report.target_repository}`",
        f"- Jira project key: `{report.jira_project_key}`",
        f"- Jira board id: `{report.jira_board_id}`",
        "",
        "## Paths",
    ]
    for path in report.paths:
        required = "required" if path.required else "optional"
        lines.append(f"- `{path.name}` ({required}): `{path.path}` - {path.purpose}")
    lines.extend(["", "## Checks"])
    for check in report.checks:
        marker = {
            ReleaseIntakeCheckStatus.PASSED: "PASS",
            ReleaseIntakeCheckStatus.WARNING: "WARN",
            ReleaseIntakeCheckStatus.FAILED: "FAIL",
        }[check.status]
        required = "required" if check.required else "optional"
        lines.append(f"- [{marker}] `{check.name}` ({required}): {check.message}")
    if report.po_questions:
        lines.extend(["", "## PO Inbox Questions"])
        for question in report.po_questions:
            lines.append(f"- `{question.id}`: {question.title}")
    return "\n".join(lines) + "\n"


def release_intake_report_markdown(report: ReleaseIntakeReport) -> str:
    """Alias kept explicit for call sites that write durable Markdown."""

    return format_release_intake_report(report)


def release_intake_report_paths(
    report: ReleaseIntakeReport,
    *,
    report_root: Path,
) -> tuple[Path, Path]:
    """Return deterministic JSON and Markdown paths for an intake report."""

    safe_project = _safe_id(report.project_id)
    safe_release = _safe_id(report.release_id)
    safe_timestamp = _safe_id(report.generated_at.replace(":", "").replace("-", ""))
    directory = report_root / safe_project / safe_release
    stem = f"intake-report-{safe_timestamp}"
    return directory / f"{stem}.json", directory / f"{stem}.md"


def _path_checks(paths: Sequence[ReleaseIntakePath]) -> tuple[ReleaseIntakeCheck, ...]:
    checks: list[ReleaseIntakeCheck] = []
    for intake_path in paths:
        if intake_path.name in {"product_docs_root", "architecture_root"}:
            checks.append(
                _directory_check(
                    intake_path.name,
                    intake_path.path,
                    f"{intake_path.name} exists.",
                    required=intake_path.required,
                )
            )
            continue
        checks.append(_creatable_directory_check(intake_path.name, intake_path.path, required=intake_path.required))
    return tuple(checks)


def _repository_check(repository: str) -> ReleaseIntakeCheck:
    repository = repository.strip()
    if _is_owner_repo(repository):
        return ReleaseIntakeCheck("target_repository", ReleaseIntakeCheckStatus.PASSED, "Repository uses owner/name.")
    return ReleaseIntakeCheck(
        "target_repository",
        ReleaseIntakeCheckStatus.FAILED,
        "Set the target repository as owner/name before story creation.",
    )


def _jira_checks(project_key: str, board_id: str, settings: PlatformSettings) -> tuple[ReleaseIntakeCheck, ...]:
    return (
        _present_check("jira.project_key", project_key, "Jira project key is configured."),
        _present_check("jira.board_id", board_id, "Jira board id is configured."),
        _present_check("jira.email", settings.jira.email, "Jira integration user email is configured."),
        _present_check("jira.api_token", settings.jira.api_token, "Jira API token is configured."),
    )


def _confluence_checks(settings: PlatformSettings, *, required: bool) -> tuple[ReleaseIntakeCheck, ...]:
    if settings.confluence.space_key and settings.confluence.parent_page_id:
        return (
            ReleaseIntakeCheck(
                "confluence",
                ReleaseIntakeCheckStatus.PASSED,
                "Confluence publication target is configured.",
                required=required,
            ),
        )
    status = ReleaseIntakeCheckStatus.FAILED if required else ReleaseIntakeCheckStatus.WARNING
    return (
        ReleaseIntakeCheck(
            "confluence",
            status,
            "Confluence is not fully configured; GitHub Pages/local Markdown can be used unless Confluence is required.",
            required=required,
        ),
    )


def _agiletest_checks(settings: PlatformSettings, *, required: bool) -> tuple[ReleaseIntakeCheck, ...]:
    if not required:
        return (
            ReleaseIntakeCheck(
                "agiletest",
                ReleaseIntakeCheckStatus.WARNING,
                "AgileTest readiness was explicitly marked optional for this intake.",
                required=False,
            ),
        )
    return (
        _present_check("agiletest.client_id", settings.agiletest.client_id, "AgileTest client id is configured."),
        _present_check("agiletest.api_token", settings.agiletest.api_token, "AgileTest API token is configured."),
    )


def _codex_limit_check(
    record: CodexLimitAvailabilityRecord | None,
    *,
    stale_after_seconds: int | None,
    future_tolerance_seconds: int,
) -> ReleaseIntakeCheck:
    gate = decide_codex_limit_gate(
        record,
        stale_after_seconds=stale_after_seconds,
        future_tolerance_seconds=future_tolerance_seconds,
    )
    if gate.allowed:
        return ReleaseIntakeCheck("codex_limits.latest", ReleaseIntakeCheckStatus.PASSED, gate.reason)
    message = gate.reason
    if gate.resume_after:
        message = f"{message} Resume after {gate.resume_after}."
    return ReleaseIntakeCheck("codex_limits.latest", ReleaseIntakeCheckStatus.FAILED, message)


def _product_docs_content_check(path: Path) -> ReleaseIntakeCheck:
    if not path.is_dir():
        return ReleaseIntakeCheck(
            "product_docs.content",
            ReleaseIntakeCheckStatus.FAILED,
            "Product docs root must exist before checking source documents.",
        )
    if _contains_markdown(path):
        return ReleaseIntakeCheck(
            "product_docs.content",
            ReleaseIntakeCheckStatus.PASSED,
            "Product docs root contains Markdown source documents.",
        )
    return ReleaseIntakeCheck(
        "product_docs.content",
        ReleaseIntakeCheckStatus.FAILED,
        "Add at least one Markdown product/source document before creating epics and stories.",
    )


def _architecture_content_check(path: Path) -> ReleaseIntakeCheck:
    if not path.is_dir():
        return ReleaseIntakeCheck(
            "architecture.content",
            ReleaseIntakeCheckStatus.FAILED,
            "Architecture root must exist before checking architecture inputs.",
        )
    if _contains_markdown(path):
        return ReleaseIntakeCheck(
            "architecture.content",
            ReleaseIntakeCheckStatus.PASSED,
            "Architecture root contains Markdown inputs or decisions.",
            required=False,
        )
    return ReleaseIntakeCheck(
        "architecture.content",
        ReleaseIntakeCheckStatus.WARNING,
        "Architecture root is available but has no Markdown inputs yet; Architecture Agent may create them after PO review.",
        required=False,
    )


def _directory_check(name: str, path: Path, success_message: str, *, required: bool = True) -> ReleaseIntakeCheck:
    if path.is_dir():
        return ReleaseIntakeCheck(name, ReleaseIntakeCheckStatus.PASSED, success_message, required=required)
    return ReleaseIntakeCheck(
        name,
        ReleaseIntakeCheckStatus.FAILED,
        f"{name} must exist and be a directory: {path}",
        required=required,
    )


def _creatable_directory_check(name: str, path: Path, *, required: bool = True) -> ReleaseIntakeCheck:
    if path.is_dir():
        return ReleaseIntakeCheck(name, ReleaseIntakeCheckStatus.PASSED, f"{name} exists.", required=required)
    nearest = _nearest_existing_parent(path)
    if nearest is not None:
        return ReleaseIntakeCheck(
            name,
            ReleaseIntakeCheckStatus.PASSED,
            f"{name} can be created under existing parent {nearest}.",
            required=required,
        )
    return ReleaseIntakeCheck(
        name,
        ReleaseIntakeCheckStatus.FAILED,
        f"{name} cannot be created because no parent directory exists: {path}",
        required=required,
    )


def _present_check(name: str, value: str, success_message: str) -> ReleaseIntakeCheck:
    if value.strip():
        return ReleaseIntakeCheck(name, ReleaseIntakeCheckStatus.PASSED, success_message)
    return ReleaseIntakeCheck(name, ReleaseIntakeCheckStatus.FAILED, "Required setup value is missing.")


def _question_for_failed_check(
    check: ReleaseIntakeCheck,
    *,
    project_id: str,
    release_id: str,
) -> ReleaseIntakePOQuestion:
    safe_check = _safe_id(check.name)
    question_id = f"intake-{_safe_id(project_id)}-{_safe_id(release_id)}-{safe_check}"
    return ReleaseIntakePOQuestion(
        id=question_id,
        title=f"Resolve intake blocker: {check.name}",
        message=(
            f"The guided release intake cannot mark {project_id} {release_id} ready because "
            f"`{check.name}` failed. {check.message}"
        ),
        business_impact="Agents may create incorrect scope, miss dependencies, or lose work without this setup item.",
        recommendation="Provide or correct the required configuration/path, then rerun `agentic setup intake`.",
        related_check=check.name,
    )


def _resolve_path(path: Path, base: Path) -> Path:
    expanded = Path(path).expanduser()
    if expanded.is_absolute():
        return expanded.resolve()
    return (base / expanded).resolve()


def _nearest_existing_parent(path: Path) -> Path | None:
    current = path
    while current != current.parent:
        if current.exists():
            return current if current.is_dir() else None
        current = current.parent
    return current if current.exists() and current.is_dir() else None


def _contains_markdown(path: Path) -> bool:
    return any(candidate.is_file() for candidate in path.rglob("*.md"))


def _is_owner_repo(value: str) -> bool:
    parts = value.strip().split("/")
    return len(parts) == 2 and all(part.strip() for part in parts)


def _safe_id(value: str) -> str:
    safe = "".join(character if character.isalnum() or character in {"-", "_", "."} else "-" for character in value)
    safe = safe.strip("-._")
    return safe or "unknown"


def release_intake_summary_table(report: ReleaseIntakeReport) -> Mapping[str, object]:
    """Return a compact summary useful for CLI JSON output."""

    return {
        "ready": report.ready,
        "project_id": report.project_id,
        "release_id": report.release_id,
        "failed_checks": [check.name for check in report.checks if check.blocks_readiness],
        "warning_checks": [
            check.name for check in report.checks if check.status is ReleaseIntakeCheckStatus.WARNING
        ],
        "po_questions": [question.id for question in report.po_questions],
    }
