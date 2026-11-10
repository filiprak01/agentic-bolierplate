"""Durable release E2E runner output storage."""

from __future__ import annotations

from pathlib import Path

from agentic_boilerplate.domain.release_e2e_runner import (
    ReleaseE2EExecutionReport,
    render_release_e2e_execution_report,
)


def write_release_e2e_execution_report(
    report: ReleaseE2EExecutionReport,
    directory: Path,
) -> Path:
    """Persist release E2E execution output and return the markdown path."""

    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{_safe_path_segment(report.release_key)}-e2e-execution.md"
    path.write_text(render_release_e2e_execution_report(report), encoding="utf-8")
    return path


def _safe_path_segment(value: str) -> str:
    normalized = "".join(character.lower() if character.isalnum() else "-" for character in value.strip())
    while "--" in normalized:
        normalized = normalized.replace("--", "-")
    return normalized.strip("-") or "release"
