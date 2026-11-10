"""Configuration validation and redaction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agentic_boilerplate.config.settings import PlatformSettings, settings_to_dict

SECRET_FIELD_NAMES = {"token", "api_token", "access_token", "ssh_private_key", "ssh_private_key_b64", "ssh_key_path"}
SECRET_FIELD_MARKERS = ("token", "secret", "password", "private_key", "credential")


@dataclass(frozen=True)
class ConfigValidationIssue:
    section: str
    field: str
    message: str

    @property
    def path(self) -> str:
        return f"{self.section}.{self.field}"


class ConfigValidationError(ValueError):
    """Raised when required configuration is missing."""

    def __init__(self, issues: list[ConfigValidationIssue]) -> None:
        self.issues = issues
        super().__init__(format_validation_issues(issues))


def validate_required_settings(settings: PlatformSettings) -> list[ConfigValidationIssue]:
    """Return missing required setting issues without exposing values."""

    checks = {
        "github": ("token", "repository", "default_branch"),
        "jira": ("base_url", "project_key", "board_id", "email", "api_token"),
        "documentation": ("provider",),
        "codex": ("default_model", "default_reasoning", "default_speed"),
        "paths": (
            "po_inbox",
            "context_packs",
            "codex_jobs",
            "codex_results",
            "agent_logs",
            "po_decisions",
            "sprints",
            "confluence_mirror",
        ),
    }

    issues: list[ConfigValidationIssue] = []
    for section, field_names in checks.items():
        section_value = getattr(settings, section)
        for field_name in field_names:
            if not str(getattr(section_value, field_name, "")).strip():
                issues.append(
                    ConfigValidationIssue(
                        section=section,
                        field=field_name,
                        message="Required configuration value is missing.",
                    )
                )
    valid_providers = {"github_pages", "confluence", "both", "offline"}
    if settings.documentation.provider not in valid_providers:
        issues.append(
            ConfigValidationIssue(
                section="documentation",
                field="provider",
                message="DOCUMENTATION_PROVIDER must be one of github_pages, confluence, both, or offline.",
            )
        )
    if settings.documentation.uses_github_pages:
        for field_name in ("github_pages_branch", "github_pages_source_dir", "github_pages_deployment_mode"):
            if not str(getattr(settings.documentation, field_name, "")).strip():
                issues.append(
                    ConfigValidationIssue(
                        section="documentation",
                        field=field_name,
                        message="Required GitHub Pages documentation setting is missing.",
                    )
                )
    if settings.documentation.uses_confluence:
        for field_name in ("base_url", "space_key", "parent_page_id", "email", "api_token"):
            if not str(getattr(settings.confluence, field_name, "")).strip():
                issues.append(
                    ConfigValidationIssue(
                        section="confluence",
                        field=field_name,
                        message="Required Confluence setting is missing because DOCUMENTATION_PROVIDER includes confluence.",
                    )
                )
    return issues


def require_valid_settings(settings: PlatformSettings) -> PlatformSettings:
    """Raise a redacted validation error when required settings are missing."""

    issues = validate_required_settings(settings)
    if issues:
        raise ConfigValidationError(issues)
    return settings


def format_validation_issues(issues: list[ConfigValidationIssue]) -> str:
    """Format validation issues without including secret values."""

    if not issues:
        return "Configuration is valid."
    lines = ["Configuration validation failed:"]
    lines.extend(f"- {issue.path}: {issue.message}" for issue in issues)
    return "\n".join(lines)


def redacted_settings(settings: PlatformSettings) -> dict[str, Any]:
    """Return settings as a dictionary with secret fields masked."""

    return _redact(settings_to_dict(settings))


def _redact(value: Any, *, field_name: str = "") -> Any:
    if isinstance(value, dict):
        return {key: _redact(item, field_name=key) for key, item in value.items()}
    lowered = field_name.lower()
    if field_name in SECRET_FIELD_NAMES or any(marker in lowered for marker in SECRET_FIELD_MARKERS):
        return "***REDACTED***" if value else ""
    return value
