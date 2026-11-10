"""Durable test evidence artifact workflow."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath


class TestEvidenceArtifactError(ValueError):
    """Raised when test evidence artifact input is incomplete."""

    __test__ = False


class EvidenceCriterionResult(str, Enum):
    """Acceptance criterion result in tester evidence."""

    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"
    NOT_RUN = "not-run"


@dataclass(frozen=True)
class EvidenceAcceptanceCriterion:
    """Acceptance criterion result captured in evidence."""

    text: str
    result: EvidenceCriterionResult
    notes: str = ""


@dataclass(frozen=True)
class EvidenceCommandOutput:
    """Command and relevant output captured for evidence."""

    command: str
    output: str
    exit_code: int = 0


@dataclass(frozen=True)
class EvidenceLinkedBug:
    """Bug linked from failed or blocked testing."""

    bug_key: str
    summary: str = ""


@dataclass(frozen=True)
class TestEvidenceArtifact:
    """Non-simple story test evidence artifact."""

    __test__ = False

    jira_issue_key: str
    test_issue_key: str
    tester_role: str
    executed_at: str
    acceptance_criteria: tuple[EvidenceAcceptanceCriterion, ...]
    commands: tuple[EvidenceCommandOutput, ...]
    evidence_path: str
    linked_bugs: tuple[EvidenceLinkedBug, ...] = ()
    concise_jira_only: bool = False


@dataclass(frozen=True)
class TestEvidencePathPlan:
    """Deterministic durable paths for test evidence."""

    __test__ = False

    root: str
    issue_key: str
    filename: str
    path: str


@dataclass(frozen=True)
class JiraEvidenceCommentReference:
    """Mockable Jira comment payload reference for evidence."""

    issue_key: str
    test_issue_key: str
    evidence_path: str
    summary: str


SECRET_PATTERNS = (
    re.compile(r"(?i)(token|api[_-]?key|secret|password)(\s*[:=]\s*)([^\s]+)"),
    re.compile(r"(?i)(bearer\s+)([A-Za-z0-9._~+/=-]+)"),
)


def build_test_evidence_path(
    *,
    root: str,
    jira_issue_key: str,
    timestamp: str,
) -> TestEvidencePathPlan:
    """Build deterministic durable evidence path for a Jira issue."""

    root = _require_text("root", root)
    issue_key = _safe_segment("jira_issue_key", jira_issue_key)
    timestamp = _safe_segment("timestamp", timestamp)
    filename = f"test-evidence-{timestamp}.md"
    path = PurePosixPath(root) / issue_key / filename
    return TestEvidencePathPlan(root=root, issue_key=issue_key, filename=filename, path=str(path))


def build_jira_evidence_comment_reference(
    artifact: TestEvidenceArtifact,
) -> JiraEvidenceCommentReference:
    """Build a Jira comment reference without requiring live Jira access."""

    _validate_artifact(artifact)
    failed = tuple(
        criterion for criterion in artifact.acceptance_criteria if criterion.result is not EvidenceCriterionResult.PASSED
    )
    status = "PASSED" if not failed and not artifact.linked_bugs else "FAILED"
    return JiraEvidenceCommentReference(
        issue_key=artifact.jira_issue_key,
        test_issue_key=artifact.test_issue_key,
        evidence_path=artifact.evidence_path,
        summary=f"Tester evidence {status}: {artifact.evidence_path}",
    )


def redact_evidence_text(text: str) -> str:
    """Redact common secret values from captured output."""

    redacted = str(text)
    redacted = SECRET_PATTERNS[0].sub(lambda match: match.group(1) + match.group(2) + "[REDACTED]", redacted)
    redacted = SECRET_PATTERNS[1].sub(lambda match: match.group(1) + "[REDACTED]", redacted)
    return redacted


def render_test_evidence_markdown(artifact: TestEvidenceArtifact) -> str:
    """Render non-simple test evidence as Markdown."""

    _validate_artifact(artifact)
    lines = [
        f"# Test Evidence - {artifact.jira_issue_key}",
        "",
        f"- Story/Bug: {artifact.jira_issue_key}",
        f"- Test Case: {artifact.test_issue_key}",
        f"- Tester role: {artifact.tester_role}",
        f"- Executed at: {artifact.executed_at}",
        f"- Concise Jira only: {'yes' if artifact.concise_jira_only else 'no'}",
        "",
        "## Acceptance Criteria",
    ]
    if artifact.acceptance_criteria:
        for index, criterion in enumerate(artifact.acceptance_criteria, start=1):
            lines.append(f"{index}. {criterion.text}")
            lines.append(f"   - Result: {criterion.result.value}")
            if criterion.notes:
                lines.append(f"   - Notes: {redact_evidence_text(criterion.notes)}")
    else:
        lines.append("- Concise Jira-only evidence configured.")
    lines.extend(["", "## Commands"])
    if artifact.commands:
        for command in artifact.commands:
            lines.append(f"```text\n$ {command.command}\n{redact_evidence_text(command.output)}\n```")
            lines.append(f"Exit code: {command.exit_code}")
    else:
        lines.append("- None recorded")
    lines.extend(["", "## Linked Bugs"])
    if artifact.linked_bugs:
        for bug in artifact.linked_bugs:
            suffix = f": {bug.summary}" if bug.summary else ""
            lines.append(f"- {bug.bug_key}{suffix}")
    else:
        lines.append("- None")
    return "\n".join(lines)


def _validate_artifact(artifact: TestEvidenceArtifact) -> None:
    _require_text("jira_issue_key", artifact.jira_issue_key)
    _require_text("test_issue_key", artifact.test_issue_key)
    _require_text("tester_role", artifact.tester_role)
    _require_text("executed_at", artifact.executed_at)
    _require_text("evidence_path", artifact.evidence_path)
    if not artifact.concise_jira_only and not artifact.acceptance_criteria:
        raise TestEvidenceArtifactError("acceptance_criteria is required for non-simple evidence")
    for criterion in artifact.acceptance_criteria:
        _validate_criterion(criterion)
    for command in artifact.commands:
        _validate_command(command)
    for bug in artifact.linked_bugs:
        _require_text("linked_bugs[].bug_key", bug.bug_key)


def _validate_criterion(criterion: EvidenceAcceptanceCriterion) -> None:
    _require_text("acceptance_criteria[].text", criterion.text)
    if not isinstance(criterion.result, EvidenceCriterionResult):
        raise TestEvidenceArtifactError("acceptance_criteria[].result must be EvidenceCriterionResult")


def _validate_command(command: EvidenceCommandOutput) -> None:
    _require_text("commands[].command", command.command)


def _safe_segment(name: str, value: str) -> str:
    text = _require_text(name, value)
    if "/" in text or "\\" in text or text in {".", ".."}:
        raise TestEvidenceArtifactError(f"{name} must be a safe path segment")
    return text


def _require_text(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TestEvidenceArtifactError(f"{name} is required")
    return value.strip()
