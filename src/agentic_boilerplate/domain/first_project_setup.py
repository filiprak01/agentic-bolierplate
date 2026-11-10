"""First-project setup validation for operator-controlled launches."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agentic_boilerplate.config import PlatformSettings
from agentic_boilerplate.domain.codex_limit_availability import (
    CodexLimitAvailabilityRecord,
    decide_codex_limit_gate,
)
from agentic_boilerplate.domain.multi_repo_traceability import (
    RepositoryTraceabilityRole,
    RepositoryTraceabilityTarget,
    build_jira_development_panel_warnings,
)
from agentic_boilerplate.domain.po_inbox_path_guard import validate_po_inbox_paths
from agentic_boilerplate.domain.worker_instruction_bundle import target_project_agents_template_path
from agentic_boilerplate.integrations.confluence import validate_confluence_mirror_readiness
from agentic_boilerplate.integrations.git_ssh_auth import (
    git_ssh_auth_config_from_settings,
    selected_git_ssh_key_source,
    validate_git_ssh_auth,
)
from agentic_boilerplate.storage import FilePOInboxStore, durable_directories


@dataclass(frozen=True)
class FirstProjectSetupCheck:
    name: str
    passed: bool
    message: str


@dataclass(frozen=True)
class FirstProjectSetupValidation:
    checks: tuple[FirstProjectSetupCheck, ...]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def failed_checks(self) -> tuple[FirstProjectSetupCheck, ...]:
        return tuple(check for check in self.checks if not check.passed)


def validate_first_project_setup(
    settings: PlatformSettings,
    *,
    project_root: Path | str = ".",
    latest_limit_record: CodexLimitAvailabilityRecord | None = None,
) -> FirstProjectSetupValidation:
    """Validate the minimum setup needed before starting project agents."""

    root = Path(project_root).resolve()
    checks: list[FirstProjectSetupCheck] = []
    checks.extend(_github_checks(settings))
    checks.extend(_docker_git_auth_checks(settings))
    checks.extend(_repository_traceability_checks(settings))
    checks.extend(_jira_checks(settings))
    checks.extend(_confluence_checks(settings))
    checks.extend(_agiletest_checks(settings))
    checks.append(_target_project_path_check(settings))
    checks.append(_target_project_agents_template_check(project_root=root))
    checks.extend(_durable_path_checks(settings, root))
    checks.append(_po_inbox_path_guard_check(settings, root))
    checks.append(
        _codex_limit_check(
            latest_limit_record,
            stale_after_seconds=settings.codex_limit_sentinel.stale_after_seconds,
            future_tolerance_seconds=settings.codex_limit_sentinel.future_tolerance_seconds,
        )
    )
    return FirstProjectSetupValidation(checks=tuple(checks))


def format_first_project_setup_validation(result: FirstProjectSetupValidation) -> str:
    """Format setup validation without printing configured secret values."""

    lines = ["First project setup validation:"]
    for check in result.checks:
        marker = "PASS" if check.passed else "FAIL"
        lines.append(f"- [{marker}] {check.name}: {check.message}")
    return "\n".join(lines)


def _github_checks(settings: PlatformSettings) -> tuple[FirstProjectSetupCheck, ...]:
    repository = settings.github.repository.strip()
    return (
        FirstProjectSetupCheck(
            "github.repository",
            _is_owner_repo(repository),
            "Repository is configured as owner/name."
            if _is_owner_repo(repository)
            else "Set GITHUB_REPOSITORY to the target repository as owner/name.",
        ),
    )


def _docker_git_auth_checks(settings: PlatformSettings) -> tuple[FirstProjectSetupCheck, ...]:
    config = git_ssh_auth_config_from_settings(settings)
    issues = validate_git_ssh_auth(config)
    checks = [
        FirstProjectSetupCheck(
            "github.auth_mode",
            not any(issue.field in {"github.auth_mode", "github.remote_mode"} for issue in issues),
            "Git auth mode is configured."
            if not any(issue.field in {"github.auth_mode", "github.remote_mode"} for issue in issues)
            else "GITHUB_AUTH_MODE and GIT_REMOTE_MODE must be https or ssh.",
        )
    ]
    if config.auth_mode == "ssh":
        missing_or_invalid_key = [issue for issue in issues if issue.field.startswith("github.ssh")]
        key_source = selected_git_ssh_key_source(config)
        checks.append(
            FirstProjectSetupCheck(
                "github.ssh_key_source",
                not missing_or_invalid_key,
                f"Docker Git SSH key source is configured as {key_source}."
                if not missing_or_invalid_key
                else "Docker Git SSH auth requires one valid key source without exposing the value.",
            )
        )
        checks.append(
            FirstProjectSetupCheck(
                "github.ssh_precedence",
                True,
                "When multiple key sources are configured, mounted key path wins, then base64 value, then raw value.",
            )
        )
    else:
        checks.append(
            FirstProjectSetupCheck(
                "github.ssh_key_source",
                True,
                "Docker Git SSH key source is not required while GITHUB_AUTH_MODE=https.",
            )
        )
    return tuple(checks)


def _repository_traceability_checks(settings: PlatformSettings) -> tuple[FirstProjectSetupCheck, ...]:
    targets = _repository_traceability_targets(settings)
    checks: list[FirstProjectSetupCheck] = []
    for target in targets:
        name = f"repositories.{target.role.value}"
        if not target.repository.strip():
            checks.append(
                FirstProjectSetupCheck(
                    name,
                    True,
                    "Repository lane is optional and not configured.",
                )
            )
            continue
        valid = _is_owner_repo(target.repository)
        checks.append(
            FirstProjectSetupCheck(
                name,
                valid,
                "Repository lane is configured as owner/name."
                if valid
                else "Repository lane must use owner/name format.",
            )
        )
    for warning in build_jira_development_panel_warnings(targets):
        role = warning.split(":", maxsplit=1)[0]
        checks.append(
            FirstProjectSetupCheck(
                f"repositories.{role}.jira_development_panel",
                True,
                f"WARNING: {warning}",
            )
        )
    return tuple(checks)


def _repository_traceability_targets(settings: PlatformSettings) -> tuple[RepositoryTraceabilityTarget, ...]:
    return (
        RepositoryTraceabilityTarget(
            role=RepositoryTraceabilityRole.TARGET_IMPLEMENTATION,
            repository=settings.repositories.target_implementation.repository,
            default_branch=settings.repositories.target_implementation.default_branch,
            jira_development_panel_expected=(
                settings.repositories.target_implementation.jira_development_panel_expected
            ),
        ),
        RepositoryTraceabilityTarget(
            role=RepositoryTraceabilityRole.BOILERPLATE_PROCESS,
            repository=settings.repositories.boilerplate_process.repository,
            default_branch=settings.repositories.boilerplate_process.default_branch,
            jira_development_panel_expected=settings.repositories.boilerplate_process.jira_development_panel_expected,
        ),
        RepositoryTraceabilityTarget(
            role=RepositoryTraceabilityRole.DOCUMENTATION,
            repository=settings.repositories.documentation.repository,
            default_branch=settings.repositories.documentation.default_branch,
            jira_development_panel_expected=settings.repositories.documentation.jira_development_panel_expected,
        ),
        RepositoryTraceabilityTarget(
            role=RepositoryTraceabilityRole.AUTOMATION,
            repository=settings.repositories.automation.repository,
            default_branch=settings.repositories.automation.default_branch,
            jira_development_panel_expected=settings.repositories.automation.jira_development_panel_expected,
        ),
    )


def _jira_checks(settings: PlatformSettings) -> tuple[FirstProjectSetupCheck, ...]:
    return (
        _present("jira.project_key", settings.jira.project_key, "Jira project key is configured."),
        _present("jira.board_id", settings.jira.board_id, "Jira board id is configured."),
    )


def _confluence_checks(settings: PlatformSettings) -> tuple[FirstProjectSetupCheck, ...]:
    return (
        _present("confluence.space_key", settings.confluence.space_key, "Confluence space key is configured."),
        _present(
            "confluence.parent_page_id",
            settings.confluence.parent_page_id,
            "Confluence parent page id is configured.",
        ),
    )


def _agiletest_checks(settings: PlatformSettings) -> tuple[FirstProjectSetupCheck, ...]:
    return (
        _present("agiletest.client_id", settings.agiletest.client_id, "AgileTest client id is configured."),
        _present("agiletest.api_token", settings.agiletest.api_token, "AgileTest token is configured."),
    )


def _target_project_path_check(settings: PlatformSettings) -> FirstProjectSetupCheck:
    configured = settings.workers.target_project_path.strip()
    if not configured:
        return FirstProjectSetupCheck(
            "workers.target_project_path",
            False,
            "Set TARGET_PROJECT_PATH to the local target project root.",
        )
    path = Path(configured).expanduser()
    if not path.is_dir():
        return FirstProjectSetupCheck(
            "workers.target_project_path",
            False,
            "TARGET_PROJECT_PATH must exist and be a directory.",
        )
    return FirstProjectSetupCheck("workers.target_project_path", True, "Target project path exists.")


def _target_project_agents_template_check(project_root: Path) -> FirstProjectSetupCheck:
    template_path = target_project_agents_template_path(project_root)
    if template_path.is_file():
        return FirstProjectSetupCheck(
            "target_project.agents_template",
            True,
            f"Target project AGENTS.md template is available at {template_path}.",
        )
    return FirstProjectSetupCheck(
        "target_project.agents_template",
        False,
        "Target project AGENTS.md template is missing from docs/templates/target-project-AGENTS.md.",
    )


def _durable_path_checks(settings: PlatformSettings, project_root: Path) -> tuple[FirstProjectSetupCheck, ...]:
    checks: list[FirstProjectSetupCheck] = []
    data_root = (project_root / "data").resolve()
    for directory in durable_directories(settings.paths):
        path = directory.path
        resolved = (project_root / path).resolve() if not path.is_absolute() else path.resolve()
        visible = _is_relative_to(resolved, data_root)
        checks.append(
            FirstProjectSetupCheck(
                f"paths.{directory.name}.docker_visible",
                visible,
                "Durable path is under the Docker-mounted data directory."
                if visible
                else "Durable path must resolve under the repository data directory mounted into Docker.",
            )
        )
        if directory.name == "po_inbox":
            checks.extend(_po_inbox_status_directory_checks(resolved))
        if directory.name == "confluence_mirror":
            checks.append(_confluence_mirror_space_directory_check(settings, resolved))
    return tuple(checks)


def _confluence_mirror_space_directory_check(
    settings: PlatformSettings,
    mirror_root: Path,
) -> FirstProjectSetupCheck:
    result = validate_confluence_mirror_readiness(
        mirror_root=mirror_root,
        space_key=settings.confluence.space_key,
    )
    return FirstProjectSetupCheck(
        f"paths.confluence_mirror.{result.space_key or 'space'}.writable",
        result.passed,
        result.message,
    )


def _po_inbox_status_directory_checks(root: Path) -> tuple[FirstProjectSetupCheck, ...]:
    try:
        status_directories = FilePOInboxStore(root).ensure_directories()
    except OSError as exc:
        return (
            FirstProjectSetupCheck(
                "paths.po_inbox.status_directories",
                False,
                (
                    f"PO inbox status directories could not be created: {exc.__class__.__name__}. "
                    "Fix durable folder ownership or container volume permissions, then rerun setup validation."
                ),
            ),
        )

    checks: list[FirstProjectSetupCheck] = []
    for directory in status_directories:
        status_name = directory.name
        checks.append(
            FirstProjectSetupCheck(
                f"paths.po_inbox.{status_name}.exists",
                directory.is_dir(),
                "PO inbox status directory exists."
                if directory.is_dir()
                else "PO inbox status path is not a directory.",
            )
        )
        checks.append(_writable_directory_check(f"paths.po_inbox.{status_name}.writable", directory))
    return tuple(checks)


def _writable_directory_check(name: str, path: Path) -> FirstProjectSetupCheck:
    probe_path = path / ".setup-validation-write-check"
    try:
        probe_path.write_text("ok", encoding="utf-8")
        if probe_path.read_text(encoding="utf-8") != "ok":
            return FirstProjectSetupCheck(name, False, "PO inbox status write check could not be read back.")
    except OSError as exc:
        return FirstProjectSetupCheck(
            name,
            False,
            (
                f"PO inbox status write check failed: {exc.__class__.__name__}. "
                "Fix durable folder ownership or container volume permissions, then rerun setup validation."
            ),
        )
    finally:
        try:
            probe_path.unlink(missing_ok=True)
        except OSError:
            pass

    return FirstProjectSetupCheck(name, True, "PO inbox status directory is writable.")
def _po_inbox_path_guard_check(settings: PlatformSettings, project_root: Path) -> FirstProjectSetupCheck:
    configured_target = settings.workers.target_project_path.strip()
    if not configured_target:
        return FirstProjectSetupCheck(
            "po_inbox.platform_boundary",
            False,
            "TARGET_PROJECT_PATH is required before validating PO inbox ownership.",
        )

    target_project = Path(configured_target).expanduser()
    platform_inbox = settings.paths.po_inbox
    resolved_platform_inbox = (project_root / platform_inbox).resolve() if not platform_inbox.is_absolute() else platform_inbox.resolve()
    result = validate_po_inbox_paths(
        platform_inbox_root=resolved_platform_inbox,
        target_project_root=target_project,
    )
    return FirstProjectSetupCheck(
        "po_inbox.platform_boundary",
        result.passed,
        " ".join(result.messages),
    )


def _codex_limit_check(
    record: CodexLimitAvailabilityRecord | None,
    *,
    stale_after_seconds: int | None,
    future_tolerance_seconds: int,
) -> FirstProjectSetupCheck:
    gate = decide_codex_limit_gate(
        record,
        stale_after_seconds=stale_after_seconds,
        future_tolerance_seconds=future_tolerance_seconds,
    )
    if gate.allowed:
        return FirstProjectSetupCheck(
            "codex_limits.latest",
            True,
            "Latest Codex limit record allows new work.",
        )
    return FirstProjectSetupCheck(
        "codex_limits.latest",
        False,
        f"{gate.reason} Recommended action: {gate.action.value}.",
    )


def _present(name: str, value: str, success_message: str) -> FirstProjectSetupCheck:
    if str(value).strip():
        return FirstProjectSetupCheck(name, True, success_message)
    return FirstProjectSetupCheck(name, False, "Required setup value is missing.")


def _is_owner_repo(value: str) -> bool:
    parts = value.split("/")
    return len(parts) == 2 and all(part.strip() for part in parts)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
