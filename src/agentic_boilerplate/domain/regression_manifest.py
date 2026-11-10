"""Regression manifest builder for sprint and release executions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from agentic_boilerplate.domain.regression_classification import ClassifiedTestIssue
from agentic_boilerplate.domain.tester_manual_test_workflow import RegressionClassification


class RegressionManifestError(ValueError):
    """Raised when regression manifest input is incomplete or inconsistent."""


class RegressionExecutionMode(str, Enum):
    """How a reusable Test Case was executed."""

    MANUAL = "manual"
    AUTOMATED = "automated"
    SUPPORTING_VALIDATION = "supporting-validation"


class RegressionExecutionResult(str, Enum):
    """Execution result recorded in a manifest."""

    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"
    NOT_RUN = "not-run"


@dataclass(frozen=True)
class AutomatedCoverageReference:
    """Automated command, file, or function that covers a Test Case."""

    command: str = ""
    test_file: str = ""
    test_function: str = ""


@dataclass(frozen=True)
class RegressionManifestRecord:
    """One reusable Test Case execution record in a regression manifest."""

    test_case_key: str
    covered_issue_key: str
    source_sprint: str
    labels: tuple[str, ...]
    execution_mode: RegressionExecutionMode
    result: RegressionExecutionResult
    evidence_path: str
    classifications: tuple[RegressionClassification, ...]
    automated_reference: AutomatedCoverageReference | None = None


@dataclass(frozen=True)
class RegressionManifestReferences:
    """Jira/AgileTest records that should reference the manifest."""

    overview_task_key: str
    agiletest_execution_key: str = ""
    agiletest_cycle_key: str = ""


@dataclass(frozen=True)
class RegressionManifest:
    """Durable sprint or release regression manifest."""

    manifest_key: str
    release_key: str
    source_sprint: str
    generated_at: str
    records: tuple[RegressionManifestRecord, ...]
    references: RegressionManifestReferences


def build_regression_manifest_record(
    *,
    test_issue: ClassifiedTestIssue,
    source_sprint: str,
    execution_mode: RegressionExecutionMode,
    result: RegressionExecutionResult,
    evidence_path: str,
    automated_reference: AutomatedCoverageReference | None = None,
) -> RegressionManifestRecord:
    """Build one manifest record from a classified Test issue."""

    _validate_classified_test(test_issue)
    _require_text("source_sprint", source_sprint)
    _require_text("evidence_path", evidence_path)
    if not isinstance(execution_mode, RegressionExecutionMode):
        raise RegressionManifestError("execution_mode must be RegressionExecutionMode")
    if not isinstance(result, RegressionExecutionResult):
        raise RegressionManifestError("result must be RegressionExecutionResult")
    if execution_mode is RegressionExecutionMode.AUTOMATED:
        _validate_automated_reference(automated_reference)
    return RegressionManifestRecord(
        test_case_key=test_issue.test_issue_key,
        covered_issue_key=test_issue.covered_issue_key,
        source_sprint=source_sprint.strip(),
        labels=tuple(sorted(test_issue.labels)),
        execution_mode=execution_mode,
        result=result,
        evidence_path=evidence_path.strip(),
        classifications=test_issue.classifications,
        automated_reference=automated_reference,
    )


def build_regression_manifest(
    *,
    manifest_key: str,
    release_key: str,
    source_sprint: str,
    generated_at: str,
    records: tuple[RegressionManifestRecord, ...],
    references: RegressionManifestReferences,
    include_one_time_validations: bool = False,
) -> RegressionManifest:
    """Build a durable manifest, excluding one-time validations by default."""

    _require_text("manifest_key", manifest_key)
    _require_text("release_key", release_key)
    _require_text("source_sprint", source_sprint)
    _require_text("generated_at", generated_at)
    _validate_references(references)
    if not records:
        raise RegressionManifestError("records is required")
    filtered: list[RegressionManifestRecord] = []
    for record in records:
        _validate_record(record)
        if (
            RegressionClassification.ONE_TIME_VALIDATION in record.classifications
            and not include_one_time_validations
        ):
            continue
        filtered.append(record)
    if not filtered:
        raise RegressionManifestError("at least one reusable regression record is required")
    return RegressionManifest(
        manifest_key=manifest_key.strip(),
        release_key=release_key.strip(),
        source_sprint=source_sprint.strip(),
        generated_at=generated_at.strip(),
        records=tuple(filtered),
        references=references,
    )


def regression_manifest_to_dict(manifest: RegressionManifest) -> dict[str, object]:
    """Convert manifest to JSON-compatible data."""

    _validate_manifest(manifest)
    return {
        "manifest_key": manifest.manifest_key,
        "release_key": manifest.release_key,
        "source_sprint": manifest.source_sprint,
        "generated_at": manifest.generated_at,
        "references": {
            "overview_task_key": manifest.references.overview_task_key,
            "agiletest_execution_key": manifest.references.agiletest_execution_key,
            "agiletest_cycle_key": manifest.references.agiletest_cycle_key,
        },
        "records": [
            {
                "test_case_key": record.test_case_key,
                "covered_issue_key": record.covered_issue_key,
                "source_sprint": record.source_sprint,
                "labels": list(record.labels),
                "execution_mode": record.execution_mode.value,
                "result": record.result.value,
                "evidence_path": record.evidence_path,
                "classifications": [classification.value for classification in record.classifications],
                "automated_reference": None
                if record.automated_reference is None
                else {
                    "command": record.automated_reference.command,
                    "test_file": record.automated_reference.test_file,
                    "test_function": record.automated_reference.test_function,
                },
            }
            for record in manifest.records
        ],
    }


def render_regression_manifest_markdown(manifest: RegressionManifest) -> str:
    """Render manifest for local evidence, Jira comments, or Confluence sync."""

    _validate_manifest(manifest)
    lines = [
        f"# Regression Manifest - {manifest.manifest_key}",
        "",
        f"- Release: {manifest.release_key}",
        f"- Source sprint: {manifest.source_sprint}",
        f"- Generated at: {manifest.generated_at}",
        f"- Overview Task: {manifest.references.overview_task_key}",
        f"- AgileTest Execution: {manifest.references.agiletest_execution_key or 'not set'}",
        "",
        "## Records",
    ]
    for record in manifest.records:
        labels = ", ".join(record.labels)
        classifications = ", ".join(classification.value for classification in record.classifications)
        lines.append(f"- {record.test_case_key} -> {record.covered_issue_key}")
        lines.append(f"  - Source sprint: {record.source_sprint}")
        lines.append(f"  - Labels: {labels}")
        lines.append(f"  - Classifications: {classifications}")
        lines.append(f"  - Execution mode: {record.execution_mode.value}")
        lines.append(f"  - Result: {record.result.value}")
        lines.append(f"  - Evidence: {record.evidence_path}")
        if record.automated_reference is not None:
            lines.append(f"  - Command: {record.automated_reference.command or 'not set'}")
            lines.append(f"  - Test file: {record.automated_reference.test_file or 'not set'}")
            lines.append(f"  - Test function: {record.automated_reference.test_function or 'not set'}")
    return "\n".join(lines)


def _validate_manifest(manifest: RegressionManifest) -> None:
    _require_text("manifest_key", manifest.manifest_key)
    _require_text("release_key", manifest.release_key)
    _require_text("source_sprint", manifest.source_sprint)
    _require_text("generated_at", manifest.generated_at)
    _validate_references(manifest.references)
    if not manifest.records:
        raise RegressionManifestError("records is required")
    for record in manifest.records:
        _validate_record(record)


def _validate_record(record: RegressionManifestRecord) -> None:
    _require_text("record.test_case_key", record.test_case_key)
    _require_text("record.covered_issue_key", record.covered_issue_key)
    _require_text("record.source_sprint", record.source_sprint)
    _require_text("record.evidence_path", record.evidence_path)
    if not record.labels:
        raise RegressionManifestError("record.labels is required")
    for index, label in enumerate(record.labels):
        _require_text(f"record.labels[{index}]", label)
    if not isinstance(record.execution_mode, RegressionExecutionMode):
        raise RegressionManifestError("record.execution_mode must be RegressionExecutionMode")
    if not isinstance(record.result, RegressionExecutionResult):
        raise RegressionManifestError("record.result must be RegressionExecutionResult")
    if not record.classifications:
        raise RegressionManifestError("record.classifications is required")
    if record.execution_mode is RegressionExecutionMode.AUTOMATED:
        _validate_automated_reference(record.automated_reference)


def _validate_references(references: RegressionManifestReferences) -> None:
    _require_text("references.overview_task_key", references.overview_task_key)


def _validate_classified_test(test_issue: ClassifiedTestIssue) -> None:
    _require_text("test_issue.test_issue_key", test_issue.test_issue_key)
    _require_text("test_issue.covered_issue_key", test_issue.covered_issue_key)
    if not test_issue.labels:
        raise RegressionManifestError("test_issue.labels is required")
    if not test_issue.classifications:
        raise RegressionManifestError("test_issue.classifications is required")


def _validate_automated_reference(reference: AutomatedCoverageReference | None) -> None:
    if reference is None:
        raise RegressionManifestError("automated_reference is required for automated execution")
    if not any((reference.command.strip(), reference.test_file.strip(), reference.test_function.strip())):
        raise RegressionManifestError(
            "automated_reference must include command, test_file, or test_function"
        )


def _require_text(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RegressionManifestError(f"{name} is required")
    return value.strip()
