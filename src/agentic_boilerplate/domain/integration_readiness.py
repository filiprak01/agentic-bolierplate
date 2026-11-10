"""Integration readiness diagnostics for worker assignment gates."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class IntegrationReadinessStatus(str, Enum):
    """Machine-readable status for one integration diagnostic check."""

    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"
    SKIPPED = "skipped"


class IntegrationReadinessName(str, Enum):
    """Supported integration readiness groups."""

    JIRA = "jira"
    GITHUB = "github"
    CONFLUENCE = "confluence"
    AGILETEST = "agiletest"
    FIGMA = "figma"
    TARGET_REPOSITORY = "target_repository"


BLOCKING_READINESS_STATUSES = frozenset({IntegrationReadinessStatus.FAIL})


@dataclass(frozen=True)
class IntegrationReadinessCheck:
    """One redacted, PO-visible readiness check result."""

    integration: IntegrationReadinessName
    name: str
    status: IntegrationReadinessStatus
    message: str
    remediation: str = ""

    @property
    def blocking(self) -> bool:
        return self.status in BLOCKING_READINESS_STATUSES


@dataclass(frozen=True)
class IntegrationReadinessReport:
    """Aggregated readiness report used by setup diagnostics and assignment gates."""

    checks: tuple[IntegrationReadinessCheck, ...]

    @property
    def assignment_allowed(self) -> bool:
        return not any(check.blocking for check in self.checks)

    @property
    def blocking_checks(self) -> tuple[IntegrationReadinessCheck, ...]:
        return tuple(check for check in self.checks if check.blocking)

    @property
    def warning_checks(self) -> tuple[IntegrationReadinessCheck, ...]:
        return tuple(check for check in self.checks if check.status == IntegrationReadinessStatus.WARNING)


def build_integration_readiness_report(
    checks: tuple[IntegrationReadinessCheck, ...],
) -> IntegrationReadinessReport:
    """Build a readiness report with all messages redacted."""

    return IntegrationReadinessReport(checks=tuple(_redacted_check(check) for check in checks))


def integration_readiness_report_to_dict(report: IntegrationReadinessReport) -> dict[str, object]:
    """Convert a readiness report to machine-readable JSON-safe data."""

    return {
        "assignment_allowed": report.assignment_allowed,
        "checks": [
            {
                "integration": check.integration.value,
                "name": check.name,
                "status": check.status.value,
                "blocking": check.blocking,
                "message": check.message,
                "remediation": check.remediation,
            }
            for check in report.checks
        ],
    }


def format_integration_readiness_report(report: IntegrationReadinessReport) -> str:
    """Render a readable readiness report without exposing credentials."""

    lines = [
        "Live integration readiness:",
        f"- Assignment allowed: {'yes' if report.assignment_allowed else 'no'}",
    ]
    for check in report.checks:
        marker = check.status.value.upper()
        lines.append(f"- [{marker}] {check.integration.value}.{check.name}: {check.message}")
        if check.remediation:
            lines.append(f"  Remediation: {check.remediation}")
    return "\n".join(lines)


def redact_integration_readiness_text(text: str) -> str:
    """Redact token-like values from readiness messages."""

    redacted = text
    redacted = re.sub(r"github_pat_[A-Za-z0-9_]+", "***REDACTED***", redacted)
    redacted = re.sub(r"gh[pousr]_[A-Za-z0-9_]+", "***REDACTED***", redacted)
    redacted = re.sub(r"(?i)(token|secret|password|api[_-]?token)=([^\\s]+)", r"\1=***REDACTED***", redacted)
    redacted = re.sub(r"(?i)(Bearer|Basic)\\s+[A-Za-z0-9._~+/=-]+", r"\1 ***REDACTED***", redacted)
    return redacted


def _redacted_check(check: IntegrationReadinessCheck) -> IntegrationReadinessCheck:
    return IntegrationReadinessCheck(
        integration=check.integration,
        name=check.name,
        status=check.status,
        message=redact_integration_readiness_text(check.message),
        remediation=redact_integration_readiness_text(check.remediation),
    )
