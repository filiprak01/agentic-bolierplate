"""Startup validation for local workers."""

from __future__ import annotations

import importlib.util
import shutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from agentic_boilerplate.config import (
    PlatformSettings,
    validate_required_settings,
)
from agentic_boilerplate.domain import AgentRole
from agentic_boilerplate.domain.worker_instruction_bundle import platform_agents_instruction_path
from agentic_boilerplate.integrations.git_ssh_auth import git_ssh_auth_config_from_settings, validate_git_ssh_auth
from agentic_boilerplate.storage import (
    FileAgentAssignmentStore,
    FileAssignmentLockStore,
    FileCodexLimitAvailabilityStore,
    FilePOInboxStore,
    durable_directories,
    initialize_durable_directories,
)

IntegrationProbe = Callable[[], bool]


class StartupDiagnosticCategory(str, Enum):
    """Stable categories used by operators and workers to route startup failures."""

    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    CONNECTOR_STATE = "connector_state"
    NETWORK = "network"
    CONFIGURATION = "configuration"
    PATH = "path"
    SCHEMA_MIGRATION = "schema_migration"
    SERVICE_HEALTH = "service_health"
    ROLE_BOOTSTRAP = "role_bootstrap"
    REPOSITORY = "repository"
    CODEX_GATEWAY = "codex_gateway"
    ASSIGNMENT_RECOVERY = "assignment_recovery"


class StartupDiagnosticSeverity(str, Enum):
    """Severity for one startup diagnostic."""

    INFO = "info"
    WARNING = "warning"
    BLOCKER = "blocker"


class StartupRepairAction(str, Enum):
    """Allowlisted bounded startup repairs."""

    NONE = "none"
    CREATE_DIRECTORY = "create_directory"
    ENSURE_PO_INBOX_STATUS_DIRECTORIES = "ensure_po_inbox_status_directories"
    ENSURE_RUNTIME_STORE_DIRECTORIES = "ensure_runtime_store_directories"
    MANUAL_REPAIR_REQUIRED = "manual_repair_required"


@dataclass(frozen=True)
class StartupCheck:
    name: str
    passed: bool
    message: str
    category: StartupDiagnosticCategory = StartupDiagnosticCategory.SERVICE_HEALTH
    severity: StartupDiagnosticSeverity = StartupDiagnosticSeverity.BLOCKER
    remediation: str = ""
    repair_action: StartupRepairAction = StartupRepairAction.NONE


@dataclass(frozen=True)
class StartupValidationResult:
    checks: tuple[StartupCheck, ...]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def failed_checks(self) -> tuple[StartupCheck, ...]:
        return tuple(check for check in self.checks if not check.passed)

    @property
    def repair_actions(self) -> tuple[StartupCheck, ...]:
        return tuple(check for check in self.checks if check.repair_action is not StartupRepairAction.NONE)


class StartupValidationError(RuntimeError):
    """Raised when startup validation fails."""

    def __init__(self, result: StartupValidationResult) -> None:
        self.result = result
        super().__init__(format_startup_checklist(result))


def validate_startup(
    settings: PlatformSettings,
    *,
    check_integrations: bool = False,
    integration_probes: Mapping[str, IntegrationProbe] | None = None,
) -> StartupValidationResult:
    """Validate settings, durable persistence, worker roles, and optional integrations."""

    checks: list[StartupCheck] = []
    _add_entrypoint_checks(checks)
    _add_required_config_checks(checks, settings)
    _add_worker_role_checks(checks, settings)
    _add_documentation_provider_checks(checks, settings)
    _add_codex_gateway_checks(checks, settings)
    _add_git_auth_checks(checks, settings)
    _add_target_project_path_checks(checks, settings)
    _add_runtime_state_store_checks(checks, settings)
    _add_durable_directory_checks(checks, settings)

    if check_integrations:
        _add_integration_checks(checks, settings, integration_probes or {})

    return StartupValidationResult(checks=tuple(checks))


def require_startup_ready(
    settings: PlatformSettings,
    *,
    check_integrations: bool = False,
    integration_probes: Mapping[str, IntegrationProbe] | None = None,
) -> PlatformSettings:
    """Raise when workers should not start."""

    result = validate_startup(
        settings,
        check_integrations=check_integrations,
        integration_probes=integration_probes,
    )
    if not result.passed:
        raise StartupValidationError(result)
    return settings


def build_worker_startup_message(
    role: AgentRole | str,
    *,
    instruction_root: Path | str = ".",
    assignment_context_pack_path: str = "",
    project_id: str = "",
    jira_issue_key: str = "",
    repository: str = "",
    worker_id: str = "",
) -> str:
    """Build the deterministic first prompt a role worker should execute."""

    role_value = AgentRole(role)
    root = Path(instruction_root)
    lines = [
        f"Read {platform_agents_instruction_path(root)} first.",
        f"Act as {role_value.value} Agent for the configured assignment.",
        f"Load role instructions from {root / 'ai_agents' / 'roles' / f'{role_value.value}.md'}.",
        "Run startup diagnostics, Codex limit checks, dependency checks, and PO inbox checks before work.",
    ]
    if assignment_context_pack_path:
        lines.append(f"Load assignment context pack: {assignment_context_pack_path}.")
    if project_id:
        lines.append(f"Project id: {project_id}.")
    if jira_issue_key:
        lines.append(f"Jira issue: {jira_issue_key}.")
    if repository:
        lines.append(f"Repository: {repository}.")
    if worker_id:
        lines.append(f"Worker id: {worker_id}.")
    lines.append("If any required data is missing or ambiguous, create a durable PO inbox blocker and stop.")
    return "\n".join(lines)


def format_startup_checklist(result: StartupValidationResult) -> str:
    """Format startup checks without exposing configured values."""

    lines = ["Startup validation checklist:"]
    for check in result.checks:
        marker = "PASS" if check.passed else "FAIL"
        lines.append(f"- [{marker}] {check.name}: {check.message}")
    return "\n".join(lines)


def startup_validation_to_dict(result: StartupValidationResult) -> dict[str, object]:
    """Return a redaction-safe machine-readable startup diagnostic payload."""

    return {
        "passed": result.passed,
        "checks": [
            {
                "name": check.name,
                "passed": check.passed,
                "message": check.message,
                "category": check.category.value,
                "severity": check.severity.value,
                "remediation": check.remediation,
                "repair_action": check.repair_action.value,
            }
            for check in result.checks
        ],
    }


def _add_entrypoint_checks(checks: list[StartupCheck]) -> None:
    command_path = shutil.which("agentic")
    module_spec = importlib.util.find_spec("agentic_boilerplate.cli")
    available = bool(command_path or module_spec)
    checks.append(
        StartupCheck(
            "runtime.entrypoint",
            available,
            "agentic command or Python module entrypoint is available."
            if available
            else "Neither agentic command nor Python module entrypoint is available.",
            category=StartupDiagnosticCategory.SERVICE_HEALTH,
            remediation="Install the package into the image or run with PYTHONPATH=src python -m agentic_boilerplate.cli.",
        )
    )


def _add_required_config_checks(checks: list[StartupCheck], settings: PlatformSettings) -> None:
    issues = validate_required_settings(settings)
    if not issues:
        checks.append(
            StartupCheck(
                "configuration.required",
                True,
                "Required configuration is present.",
                category=StartupDiagnosticCategory.CONFIGURATION,
            )
        )
        return

    for issue in issues:
        checks.append(
            StartupCheck(
                name=f"configuration.{issue.path}",
                passed=False,
                message=issue.message,
                category=StartupDiagnosticCategory.CONFIGURATION,
                remediation="Set the missing value in the project .env or configured secret provider.",
                repair_action=StartupRepairAction.MANUAL_REPAIR_REQUIRED,
            )
        )


def _add_worker_role_checks(checks: list[StartupCheck], settings: PlatformSettings) -> None:
    roles = settings.workers.roles
    if not roles:
        checks.append(
            StartupCheck(
                "workers.roles",
                False,
                "At least one worker role must be configured.",
                category=StartupDiagnosticCategory.ROLE_BOOTSTRAP,
                remediation="Set WORKER_ROLES to one or more supported role ids.",
            )
        )
        return

    allowed_roles = {role.value for role in AgentRole}
    invalid_roles = tuple(role for role in roles if role not in allowed_roles)
    if invalid_roles:
        checks.append(
            StartupCheck(
                "workers.roles",
                False,
                "Configured worker roles include unsupported values.",
                category=StartupDiagnosticCategory.ROLE_BOOTSTRAP,
                remediation="Remove unsupported role ids from WORKER_ROLES.",
            )
        )
        return

    checks.append(
        StartupCheck(
            "workers.roles",
            True,
            "Configured worker roles are supported.",
            category=StartupDiagnosticCategory.ROLE_BOOTSTRAP,
        )
    )


def _add_documentation_provider_checks(checks: list[StartupCheck], settings: PlatformSettings) -> None:
    provider = settings.documentation.provider
    if provider == "github_pages":
        checks.append(
            StartupCheck(
                "documentation.provider",
                True,
                "GitHub Pages is the default documentation publication provider.",
                category=StartupDiagnosticCategory.CONFIGURATION,
            )
        )
    elif provider == "confluence":
        checks.append(
            StartupCheck(
                "documentation.provider",
                True,
                "Confluence is selected as the documentation provider.",
                category=StartupDiagnosticCategory.CONFIGURATION,
            )
        )
    elif provider == "both":
        checks.append(
            StartupCheck(
                "documentation.provider",
                True,
                "GitHub Pages and Confluence are both selected for documentation publication.",
                category=StartupDiagnosticCategory.CONFIGURATION,
            )
        )
    elif provider == "offline":
        checks.append(
            StartupCheck(
                "documentation.provider",
                True,
                "Documentation publication is offline/local-only.",
                category=StartupDiagnosticCategory.CONFIGURATION,
            )
        )
    else:
        checks.append(
            StartupCheck(
                "documentation.provider",
                False,
                "Unsupported documentation provider.",
                category=StartupDiagnosticCategory.CONFIGURATION,
                remediation="Use github_pages, confluence, both, or offline.",
            )
        )
        return

    if settings.documentation.uses_github_pages:
        checks.append(
            StartupCheck(
                "documentation.github_pages.url",
                True,
                "GitHub Pages URL is configured."
                if settings.documentation.github_pages_url
                else "GitHub Pages URL is not configured yet; first deployment may create it.",
                category=StartupDiagnosticCategory.CONFIGURATION,
                severity=StartupDiagnosticSeverity.INFO,
            )
        )
        checks.append(
            StartupCheck(
                "documentation.github_pages.source",
                bool(settings.documentation.github_pages_source_dir.strip()),
                "GitHub Pages source directory is configured.",
                category=StartupDiagnosticCategory.CONFIGURATION,
                remediation="Set GITHUB_PAGES_SOURCE_DIR when GitHub Pages publication is enabled.",
            )
        )
    if settings.documentation.uses_confluence:
        configured = bool(
            settings.confluence.base_url
            and settings.confluence.space_key
            and settings.confluence.parent_page_id
            and settings.confluence.email
            and settings.confluence.api_token
        )
        checks.append(
            StartupCheck(
                "documentation.confluence.required",
                configured,
                "Confluence settings are configured for selected documentation provider."
                if configured
                else "Confluence settings are required because the selected documentation provider includes Confluence.",
                category=StartupDiagnosticCategory.CONFIGURATION,
                remediation="Set Confluence base URL, space, parent page, email, and token or switch documentation provider.",
            )
        )


def _add_codex_gateway_checks(checks: list[StartupCheck], settings: PlatformSettings) -> None:
    sentinel = settings.codex_limit_sentinel
    if not sentinel.enabled:
        checks.append(
            StartupCheck(
                "codex.gateway.enabled",
                True,
                "Codex limit sentinel is disabled; durable limit records remain the required worker gate.",
                category=StartupDiagnosticCategory.CODEX_GATEWAY,
                severity=StartupDiagnosticSeverity.INFO,
            )
        )
        return

    checks.append(
        StartupCheck(
            "codex.gateway.mode",
            sentinel.mode == "host_app_server",
            "Codex gateway uses host App Server mode."
            if sentinel.mode == "host_app_server"
            else "Unsupported Codex gateway mode.",
            category=StartupDiagnosticCategory.CODEX_GATEWAY,
            remediation="Set CODEX_LIMIT_SENTINEL_MODE=host_app_server for subscription-backed execution.",
        )
    )
    checks.append(
        StartupCheck(
            "codex.gateway.transport",
            sentinel.app_server_transport == "stdio",
            "Codex App Server transport is stdio."
            if sentinel.app_server_transport == "stdio"
            else "Unsupported Codex App Server transport.",
            category=StartupDiagnosticCategory.CODEX_GATEWAY,
            remediation="Set CODEX_LIMIT_APP_SERVER_TRANSPORT=stdio.",
        )
    )
    checks.append(
        StartupCheck(
            "codex.gateway.command",
            bool(sentinel.app_server_command.strip()),
            "Codex App Server command is configured.",
            category=StartupDiagnosticCategory.CODEX_GATEWAY,
            remediation="Set CODEX_LIMIT_APP_SERVER_COMMAND, usually `codex app-server`.",
        )
    )
    checks.append(
        StartupCheck(
            "codex.auth_mode",
            not bool(sentinel.access_token.strip()),
            "Codex execution is configured for ChatGPT subscription authentication."
            if not sentinel.access_token.strip()
            else "Codex API access token is configured where subscription authentication is required.",
            category=StartupDiagnosticCategory.AUTHENTICATION,
            remediation="Remove CODEX_ACCESS_TOKEN and run codex login on the host account used for subscription execution.",
        )
    )


def _add_git_auth_checks(checks: list[StartupCheck], settings: PlatformSettings) -> None:
    config = git_ssh_auth_config_from_settings(settings)
    issues = validate_git_ssh_auth(config)
    if not issues:
        checks.append(
            StartupCheck(
                "github.git_auth",
                True,
                "Git authentication settings are valid.",
                category=StartupDiagnosticCategory.AUTHENTICATION,
            )
        )
        return
    for issue in issues:
        checks.append(
            StartupCheck(
                f"configuration.{issue.field}",
                False,
                issue.message,
                category=StartupDiagnosticCategory.AUTHENTICATION,
                remediation="Fix GitHub auth mode, token, SSH key path, or SSH key value in .env without exposing secret values.",
            )
        )


def _add_target_project_path_checks(checks: list[StartupCheck], settings: PlatformSettings) -> None:
    target_project_path = settings.workers.target_project_path.strip()
    if not target_project_path:
        checks.append(
            StartupCheck(
                "workers.target_project_path",
                False,
                "TARGET_PROJECT_PATH must point to the target project checkout before workers start.",
                category=StartupDiagnosticCategory.PATH,
                remediation="Set TARGET_PROJECT_PATH to the target repository checkout or mounted /workspace/project path.",
                repair_action=StartupRepairAction.MANUAL_REPAIR_REQUIRED,
            )
        )
        return

    target_path = Path(target_project_path)
    if not target_path.is_dir():
        checks.append(
            StartupCheck(
                "workers.target_project_path",
                False,
                "TARGET_PROJECT_PATH does not resolve to an existing directory.",
                category=StartupDiagnosticCategory.PATH,
                remediation="Create or mount the target project checkout before starting workers.",
                repair_action=StartupRepairAction.MANUAL_REPAIR_REQUIRED,
            )
        )
        return

    checks.append(
        StartupCheck(
            "workers.target_project_path",
            True,
            "Target project path exists.",
            category=StartupDiagnosticCategory.PATH,
        )
    )
    git_metadata = target_path / ".git"
    checks.append(
        StartupCheck(
            "workers.target_project_path.git_metadata",
            git_metadata.exists(),
            "Target project path contains Git metadata."
            if git_metadata.exists()
            else "Target project path is not a Git checkout.",
            category=StartupDiagnosticCategory.REPOSITORY,
            remediation="Clone or mount the target repository checkout before workers claim assignments.",
            repair_action=(
                StartupRepairAction.NONE if git_metadata.exists() else StartupRepairAction.MANUAL_REPAIR_REQUIRED
            ),
        )
    )


def _add_runtime_state_store_checks(checks: list[StartupCheck], settings: PlatformSettings) -> None:
    stores = (
        ("agent_assignment_store", lambda: FileAgentAssignmentStore(settings.paths.agent_state).ensure_directories()),
        ("assignment_lock_store", lambda: FileAssignmentLockStore(settings.paths.agent_state).ensure_directories()),
        ("codex_limit_store", lambda: FileCodexLimitAvailabilityStore(settings.paths.codex_limits).ensure_directory()),
    )
    for name, ensure in stores:
        try:
            ensure()
        except OSError as exc:
            checks.append(
                StartupCheck(
                    f"runtime.{name}",
                    False,
                    f"Runtime store directories could not be prepared: {exc.__class__.__name__}.",
                    category=StartupDiagnosticCategory.SCHEMA_MIGRATION,
                    remediation="Verify durable volume permissions and run approved migrations before restarting the worker.",
                )
            )
            continue
        checks.append(
            StartupCheck(
                f"runtime.{name}",
                True,
                "Runtime store directories are available.",
                category=StartupDiagnosticCategory.SCHEMA_MIGRATION,
                repair_action=StartupRepairAction.ENSURE_RUNTIME_STORE_DIRECTORIES,
            )
        )


def _add_durable_directory_checks(checks: list[StartupCheck], settings: PlatformSettings) -> None:
    contract = durable_directories(settings.paths)
    missing_before = {directory.name for directory in contract if not directory.path.exists()}
    for directory in contract:
        if directory.path.is_symlink():
            checks.append(
                StartupCheck(
                    f"paths.{directory.name}.symlink",
                    False,
                    "Durable path is a symlink and cannot be auto-repaired safely.",
                    category=StartupDiagnosticCategory.PATH,
                    remediation="Replace the symlink with an approved mounted directory under the configured durable root.",
                    repair_action=StartupRepairAction.MANUAL_REPAIR_REQUIRED,
                )
            )
            return

    try:
        directories = initialize_durable_directories(settings)
    except OSError as exc:
        checks.append(
            StartupCheck(
                "paths.create",
                False,
                f"Durable directories could not be created: {exc.__class__.__name__}.",
                category=StartupDiagnosticCategory.PATH,
                remediation="Fix durable volume permissions or configured paths. Authentication and arbitrary host paths are not auto-repaired.",
            )
        )
        return

    for directory in directories:
        created = directory.name in missing_before and directory.path.is_dir()
        checks.append(
            StartupCheck(
                f"paths.{directory.name}.exists",
                directory.path.is_dir(),
                "Durable directory exists."
                if not created
                else "Durable directory was created by allowlisted startup repair.",
                category=StartupDiagnosticCategory.PATH,
                repair_action=StartupRepairAction.CREATE_DIRECTORY if created else StartupRepairAction.NONE,
            )
        )
        checks.append(_write_check(directory.name, directory.path))
        if directory.name == "po_inbox":
            _add_po_inbox_status_directory_checks(checks, directory.path)


def _add_po_inbox_status_directory_checks(checks: list[StartupCheck], root: Path) -> None:
    store = FilePOInboxStore(root)
    try:
        status_directories = store.ensure_directories()
    except OSError as exc:
        checks.append(
            StartupCheck(
                "paths.po_inbox.status_directories",
                False,
                f"PO inbox status directories could not be created: {exc.__class__.__name__}.",
                category=StartupDiagnosticCategory.PATH,
                remediation="Fix durable PO inbox volume permissions. Do not move project-specific inboxes into target repos.",
            )
        )
        return

    for status_directory in status_directories:
        status_name = status_directory.name
        checks.append(
            StartupCheck(
                f"paths.po_inbox.{status_name}.exists",
                status_directory.is_dir(),
                "PO inbox status directory exists."
                if status_directory.is_dir()
                else "PO inbox status path is not a directory.",
                category=StartupDiagnosticCategory.PATH,
                repair_action=StartupRepairAction.ENSURE_PO_INBOX_STATUS_DIRECTORIES,
            )
        )
        checks.append(_write_check(f"po_inbox.{status_name}", status_directory))


def _write_check(name: str, path: Path) -> StartupCheck:
    probe_path = path / ".startup-validation-write-check"
    try:
        probe_path.write_text("ok", encoding="utf-8")
        if probe_path.read_text(encoding="utf-8") != "ok":
            return StartupCheck(
                f"paths.{name}.writable",
                False,
                "Durable write check could not be read back.",
                category=StartupDiagnosticCategory.PATH,
                remediation="Verify durable volume write permissions.",
            )
    except OSError as exc:
        return StartupCheck(
            f"paths.{name}.writable",
            False,
            f"Durable write check failed: {exc.__class__.__name__}.",
            category=StartupDiagnosticCategory.PATH,
            remediation="Verify durable volume write permissions.",
        )
    finally:
        try:
            probe_path.unlink(missing_ok=True)
        except OSError:
            pass

    return StartupCheck(f"paths.{name}.writable", True, "Durable directory is writable.", category=StartupDiagnosticCategory.PATH)


def _add_integration_checks(
    checks: list[StartupCheck],
    settings: PlatformSettings,
    probes: Mapping[str, IntegrationProbe],
) -> None:
    configured_integrations = {
        "github": bool(settings.github.token and settings.github.repository),
        "jira": bool(settings.jira.base_url and settings.jira.email and settings.jira.api_token),
        "confluence": bool(
            settings.confluence.base_url
            and settings.confluence.space_key
            and settings.confluence.email
            and settings.confluence.api_token
        ),
    }

    for name, configured in configured_integrations.items():
        if not configured:
            checks.append(
                StartupCheck(
                    f"integrations.{name}",
                    True,
                    "Integration credentials are not configured.",
                    category=StartupDiagnosticCategory.CONFIGURATION,
                    severity=StartupDiagnosticSeverity.INFO,
                )
            )
            continue

        probe = probes.get(name)
        if probe is None:
            checks.append(
                StartupCheck(
                    f"integrations.{name}",
                    True,
                    "Integration access check was skipped.",
                    category=StartupDiagnosticCategory.CONNECTOR_STATE,
                    severity=StartupDiagnosticSeverity.WARNING,
                    remediation="Run live setup diagnostics before live worker execution.",
                )
            )
            continue

        try:
            passed = probe()
        except Exception as exc:  # pragma: no cover - defensive against adapter failures.
            category = _integration_failure_category(exc)
            checks.append(
                StartupCheck(
                    f"integrations.{name}",
                    False,
                    f"Integration access check failed: {exc.__class__.__name__}.",
                    category=category,
                    remediation=_integration_remediation(category, name),
                    repair_action=StartupRepairAction.MANUAL_REPAIR_REQUIRED,
                )
            )
            continue

        checks.append(
            StartupCheck(
                f"integrations.{name}",
                bool(passed),
                "Integration access check passed." if passed else "Integration access check failed.",
                category=StartupDiagnosticCategory.SERVICE_HEALTH if passed else StartupDiagnosticCategory.CONNECTOR_STATE,
                remediation="Reinstall or reconnect the connector, then verify token scopes and organization SSO access."
                if not passed
                else "",
                repair_action=StartupRepairAction.NONE if passed else StartupRepairAction.MANUAL_REPAIR_REQUIRED,
            )
        )


def _integration_failure_category(exc: Exception) -> StartupDiagnosticCategory:
    text = str(exc).lower()
    if "401" in text or "unauthorized" in text:
        return StartupDiagnosticCategory.AUTHENTICATION
    if "403" in text or "forbidden" in text or "sso" in text:
        return StartupDiagnosticCategory.AUTHORIZATION
    if "timeout" in text or "connection" in text or "dns" in text or "network" in text:
        return StartupDiagnosticCategory.NETWORK
    if "connector" in text or "installation" in text:
        return StartupDiagnosticCategory.CONNECTOR_STATE
    return StartupDiagnosticCategory.SERVICE_HEALTH


def _integration_remediation(category: StartupDiagnosticCategory, name: str) -> str:
    if category is StartupDiagnosticCategory.AUTHENTICATION:
        return f"Refresh the {name} credential; do not attempt automatic credential repair."
    if category is StartupDiagnosticCategory.AUTHORIZATION:
        return f"Verify {name} token scopes, organization SSO, and connector authorization."
    if category is StartupDiagnosticCategory.NETWORK:
        return f"Retry {name} after bounded backoff and record the diagnostic if it remains unavailable."
    if category is StartupDiagnosticCategory.CONNECTOR_STATE:
        return f"Reconnect or reinstall the {name} connector before live assignment work."
    return f"Check {name} service health and rerun startup diagnostics."
