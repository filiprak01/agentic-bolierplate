"""Typed platform configuration."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from pathlib import Path
from typing import Any

from agentic_boilerplate.config.env import load_env_values


@dataclass(frozen=True)
class GitHubSettings:
    token: str = ""
    repository: str = "example-org/agentic-boilerplate"
    default_branch: str = "main"
    auth_mode: str = "https"
    remote_mode: str = "https"
    ssh_key_path: str = ""
    ssh_private_key: str = ""
    ssh_private_key_b64: str = ""
    ssh_known_hosts_path: str = ""
    ssh_strict_host_key_checking: bool = True


@dataclass(frozen=True)
class RepositoryTraceabilitySettings:
    repository: str = ""
    default_branch: str = "main"
    jira_development_panel_expected: bool = True


@dataclass(frozen=True)
class ProjectRepositorySettings:
    target_implementation: RepositoryTraceabilitySettings
    boilerplate_process: RepositoryTraceabilitySettings
    documentation: RepositoryTraceabilitySettings
    automation: RepositoryTraceabilitySettings


@dataclass(frozen=True)
class JiraSettings:
    base_url: str = "https://example.atlassian.net"
    project_key: str = "AGENT"
    board_id: str = "1"
    email: str = ""
    api_token: str = ""


@dataclass(frozen=True)
class ConfluenceSettings:
    base_url: str = "https://example.atlassian.net/wiki"
    space_key: str = "AGENT"
    parent_page_id: str = "458864"
    space_url: str = "https://example.atlassian.net/wiki/spaces/AGENT/overview?homepageId=458864"
    email: str = ""
    api_token: str = ""


@dataclass(frozen=True)
class DocumentationSettings:
    provider: str = "github_pages"
    github_pages_url: str = ""
    github_pages_branch: str = "gh-pages"
    github_pages_source_dir: str = "docs"
    github_pages_custom_domain: str = ""
    github_pages_deployment_mode: str = "github_actions"
    github_pages_deploy_token: str = ""

    @property
    def uses_github_pages(self) -> bool:
        return self.provider in {"github_pages", "both"}

    @property
    def uses_confluence(self) -> bool:
        return self.provider in {"confluence", "both"}

    @property
    def is_offline(self) -> bool:
        return self.provider == "offline"


@dataclass(frozen=True)
class AgileTestSettings:
    client_id: str = ""
    api_token: str = ""


@dataclass(frozen=True)
class FigmaSettings:
    token: str = ""
    file_key: str = ""
    project_url: str = ""


@dataclass(frozen=True)
class ImageRegistrySettings:
    host: str = ""
    namespace: str = "agentic-boilerplate"
    image_tag: str = "local"
    push_enabled: bool = False
    publish_dry_run: bool = True
    username: str = ""
    token: str = ""
    credential_ref: str = ""


@dataclass(frozen=True)
class CodexSettings:
    default_model: str = "gpt-5.5"
    default_reasoning: str = "medium"
    default_speed: str = "normal"
    allow_high_reasoning: bool = True
    allow_xhigh_reasoning: bool = False
    pause_on_limit: bool = True
    save_failed_request: bool = True


@dataclass(frozen=True)
class CodexLimitSentinelSettings:
    enabled: bool = False
    mode: str = "host_app_server"
    app_server_command: str = "codex app-server"
    app_server_transport: str = "stdio"
    account_scope_id: str = "default"
    bucket_id: str = ""
    guard_cutoff_percent: int = 90
    stale_after_seconds: int = 0
    future_tolerance_seconds: int = 30
    refresh_before_stage: bool = False
    record_source: str = "codex_app_server"
    access_token: str = ""


@dataclass(frozen=True)
class DatabaseSettings:
    url: str = "postgresql://agentic:agentic@localhost:5432/agentic"
    migration_script_location: str = "migrations"


@dataclass(frozen=True)
class DurablePathSettings:
    po_inbox: Path = Path("data/po-inbox")
    context_packs: Path = Path("data/context-packs")
    codex_jobs: Path = Path("data/codex-jobs")
    codex_results: Path = Path("data/codex-results")
    codex_limits: Path = Path("data/codex-limits")
    agent_state: Path = Path("data/agent-state")
    agent_logs: Path = Path("data/agent-logs")
    agent_workspaces: Path = Path("data/agent-workspaces")
    po_decisions: Path = Path("data/po-decisions")
    sprints: Path = Path("data/sprints")
    confluence_mirror: Path = Path("data/confluence-mirror")


@dataclass(frozen=True)
class WorkerSettings:
    roles: tuple[str, ...] = (
        "product_planning",
        "architecture",
        "developer",
        "review",
        "tester",
        "release_manager",
        "scheduler",
        "platform",
        "frontend",
        "ui_ux",
        "security",
        "docs_confluence",
        "devops_platform",
        "data_persistence",
    )
    target_project_path: str = ""


@dataclass(frozen=True)
class PlatformSettings:
    github: GitHubSettings
    repositories: ProjectRepositorySettings
    jira: JiraSettings
    confluence: ConfluenceSettings
    documentation: DocumentationSettings
    agiletest: AgileTestSettings
    figma: FigmaSettings
    image_registry: ImageRegistrySettings
    codex: CodexSettings
    codex_limit_sentinel: CodexLimitSentinelSettings
    database: DatabaseSettings
    paths: DurablePathSettings
    workers: WorkerSettings


def load_settings(
    env_file: str | Path | None = ".env",
    *,
    environ: Mapping[str, str] | None = None,
) -> PlatformSettings:
    """Load platform settings from a dotenv file overlaid by environment."""

    values = load_env_values(env_file, environ=environ)
    return settings_from_mapping(values)


def settings_from_mapping(values: Mapping[str, str]) -> PlatformSettings:
    """Build typed settings from raw environment values."""

    github_repository = _get(values, "GITHUB_REPOSITORY", GitHubSettings.repository)
    github_default_branch = _get(values, "GITHUB_DEFAULT_BRANCH", GitHubSettings.default_branch)
    return PlatformSettings(
        github=GitHubSettings(
            token=_get(values, "GITHUB_TOKEN", _get(values, "GH_TOKEN")),
            repository=github_repository,
            default_branch=github_default_branch,
            auth_mode=_get(values, "GITHUB_AUTH_MODE", GitHubSettings.auth_mode).lower(),
            remote_mode=_get(values, "GIT_REMOTE_MODE", GitHubSettings.remote_mode).lower(),
            ssh_key_path=_get(values, "GITHUB_SSH_KEY_PATH"),
            ssh_private_key=_get(values, "GITHUB_SSH_PRIVATE_KEY"),
            ssh_private_key_b64=_get(values, "GITHUB_SSH_PRIVATE_KEY_B64"),
            ssh_known_hosts_path=_get(values, "GITHUB_SSH_KNOWN_HOSTS_PATH"),
            ssh_strict_host_key_checking=_get_bool(
                values,
                "GITHUB_SSH_STRICT_HOST_KEY_CHECKING",
                GitHubSettings.ssh_strict_host_key_checking,
            ),
        ),
        repositories=ProjectRepositorySettings(
            target_implementation=_repository_traceability_settings(
                values,
                "TARGET_IMPLEMENTATION",
                default_branch=github_default_branch,
                default_jira_development_panel_expected=True,
            ),
            boilerplate_process=_repository_traceability_settings(
                values,
                "BOILERPLATE_PROCESS",
                default_repository=github_repository,
                default_branch=github_default_branch,
                default_jira_development_panel_expected=True,
            ),
            documentation=_repository_traceability_settings(
                values,
                "DOCUMENTATION",
                default_branch=github_default_branch,
                default_jira_development_panel_expected=False,
            ),
            automation=_repository_traceability_settings(
                values,
                "AUTOMATION",
                default_branch=github_default_branch,
                default_jira_development_panel_expected=False,
            ),
        ),
        jira=JiraSettings(
            base_url=_get(values, "JIRA_BASE_URL", JiraSettings.base_url),
            project_key=_get(values, "JIRA_PROJECT_KEY", JiraSettings.project_key),
            board_id=_get(values, "JIRA_BOARD_ID", JiraSettings.board_id),
            email=_get(values, "JIRA_EMAIL"),
            api_token=_get(values, "JIRA_API_TOKEN"),
        ),
        confluence=ConfluenceSettings(
            base_url=_get(values, "CONFLUENCE_BASE_URL", ConfluenceSettings.base_url),
            space_key=_get(values, "CONFLUENCE_SPACE_KEY", ConfluenceSettings.space_key),
            parent_page_id=_get(values, "CONFLUENCE_PARENT_PAGE_ID", ConfluenceSettings.parent_page_id),
            space_url=_get(values, "CONFLUENCE_SPACE_URL", ConfluenceSettings.space_url),
            email=_get(values, "CONFLUENCE_EMAIL", _get(values, "JIRA_EMAIL")),
            api_token=_get(values, "CONFLUENCE_API_TOKEN", _get(values, "JIRA_API_TOKEN")),
        ),
        documentation=DocumentationSettings(
            provider=_get(values, "DOCUMENTATION_PROVIDER", DocumentationSettings.provider).lower(),
            github_pages_url=_get(values, "GITHUB_PAGES_DOCS_URL"),
            github_pages_branch=_get(
                values,
                "GITHUB_PAGES_BRANCH",
                DocumentationSettings.github_pages_branch,
            ),
            github_pages_source_dir=_get(
                values,
                "GITHUB_PAGES_SOURCE_DIR",
                DocumentationSettings.github_pages_source_dir,
            ),
            github_pages_custom_domain=_get(values, "GITHUB_PAGES_CUSTOM_DOMAIN"),
            github_pages_deployment_mode=_get(
                values,
                "GITHUB_PAGES_DEPLOYMENT_MODE",
                DocumentationSettings.github_pages_deployment_mode,
            ),
            github_pages_deploy_token=_get(values, "GITHUB_PAGES_DEPLOY_TOKEN"),
        ),
        agiletest=AgileTestSettings(
            client_id=_get(values, "AGILETEST_CLIENT_ID"),
            api_token=_get(values, "AGILETEST_API_TOKEN", _get(values, "AGILETEST_TOKEN")),
        ),
        figma=FigmaSettings(
            token=_get(values, "FIGMA_TOKEN"),
            file_key=_get(values, "FIGMA_FILE_KEY"),
            project_url=_get(values, "FIGMA_PROJECT_URL"),
        ),
        image_registry=ImageRegistrySettings(
            host=_get(values, "AGENTIC_IMAGE_REGISTRY_HOST", ImageRegistrySettings.host),
            namespace=_get(values, "AGENTIC_IMAGE_NAMESPACE", ImageRegistrySettings.namespace),
            image_tag=_get(values, "AGENTIC_IMAGE_TAG", ImageRegistrySettings.image_tag),
            push_enabled=_get_bool(
                values,
                "AGENTIC_IMAGE_PUSH_ENABLED",
                ImageRegistrySettings.push_enabled,
            ),
            publish_dry_run=_get_bool(
                values,
                "AGENTIC_IMAGE_PUBLISH_DRY_RUN",
                ImageRegistrySettings.publish_dry_run,
            ),
            username=_get(values, "AGENTIC_IMAGE_REGISTRY_USERNAME"),
            token=_get(values, "AGENTIC_IMAGE_REGISTRY_TOKEN"),
            credential_ref=_get(values, "AGENTIC_IMAGE_REGISTRY_CREDENTIAL_REF"),
        ),
        codex=CodexSettings(
            default_model=_get(values, "CODEX_DEFAULT_MODEL", CodexSettings.default_model),
            default_reasoning=_get(values, "CODEX_DEFAULT_REASONING", CodexSettings.default_reasoning),
            default_speed=_get(values, "CODEX_DEFAULT_SPEED", CodexSettings.default_speed),
            allow_high_reasoning=_get_bool(
                values,
                "CODEX_ALLOW_HIGH_REASONING",
                CodexSettings.allow_high_reasoning,
            ),
            allow_xhigh_reasoning=_get_bool(
                values,
                "CODEX_ALLOW_XHIGH_REASONING",
                CodexSettings.allow_xhigh_reasoning,
            ),
            pause_on_limit=_get_bool(values, "CODEX_PAUSE_ON_LIMIT", CodexSettings.pause_on_limit),
            save_failed_request=_get_bool(
                values,
                "CODEX_SAVE_FAILED_REQUEST",
                CodexSettings.save_failed_request,
            ),
        ),
        codex_limit_sentinel=CodexLimitSentinelSettings(
            enabled=_get_bool(
                values,
                "CODEX_LIMIT_SENTINEL_ENABLED",
                CodexLimitSentinelSettings.enabled,
            ),
            mode=_get(values, "CODEX_LIMIT_SENTINEL_MODE", CodexLimitSentinelSettings.mode),
            app_server_command=_get(
                values,
                "CODEX_LIMIT_APP_SERVER_COMMAND",
                CodexLimitSentinelSettings.app_server_command,
            ),
            app_server_transport=_get(
                values,
                "CODEX_LIMIT_APP_SERVER_TRANSPORT",
                CodexLimitSentinelSettings.app_server_transport,
            ),
            account_scope_id=_get(
                values,
                "CODEX_LIMIT_ACCOUNT_SCOPE_ID",
                CodexLimitSentinelSettings.account_scope_id,
            ),
            bucket_id=_get(values, "CODEX_LIMIT_BUCKET_ID"),
            guard_cutoff_percent=_get_int(
                values,
                "CODEX_LIMIT_GUARD_CUTOFF_PERCENT",
                CodexLimitSentinelSettings.guard_cutoff_percent,
            ),
            stale_after_seconds=_get_int(
                values,
                "CODEX_LIMIT_STALE_AFTER_SECONDS",
                CodexLimitSentinelSettings.stale_after_seconds,
            ),
            future_tolerance_seconds=_get_int(
                values,
                "CODEX_LIMIT_FUTURE_TOLERANCE_SECONDS",
                CodexLimitSentinelSettings.future_tolerance_seconds,
            ),
            refresh_before_stage=_get_bool(
                values,
                "CODEX_LIMIT_REFRESH_BEFORE_STAGE",
                CodexLimitSentinelSettings.refresh_before_stage,
            ),
            record_source=_get(
                values,
                "CODEX_LIMIT_RECORD_SOURCE",
                CodexLimitSentinelSettings.record_source,
            ),
            access_token=_get(values, "CODEX_ACCESS_TOKEN"),
        ),
        database=DatabaseSettings(
            url=_get(values, "DATABASE_URL", DatabaseSettings.url),
            migration_script_location=_get(
                values,
                "DATABASE_MIGRATION_SCRIPT_LOCATION",
                DatabaseSettings.migration_script_location,
            ),
        ),
        paths=DurablePathSettings(
            po_inbox=_get_path(values, "DURABLE_PO_INBOX_PATH", DurablePathSettings.po_inbox),
            context_packs=_get_path(values, "DURABLE_CONTEXT_PACKS_PATH", DurablePathSettings.context_packs),
            codex_jobs=_get_path(values, "DURABLE_CODEX_JOBS_PATH", DurablePathSettings.codex_jobs),
            codex_results=_get_path(values, "DURABLE_CODEX_RESULTS_PATH", DurablePathSettings.codex_results),
            codex_limits=_get_path(values, "DURABLE_CODEX_LIMITS_PATH", DurablePathSettings.codex_limits),
            agent_state=_get_path(values, "DURABLE_AGENT_STATE_PATH", DurablePathSettings.agent_state),
            agent_logs=_get_path(values, "DURABLE_AGENT_LOGS_PATH", DurablePathSettings.agent_logs),
            agent_workspaces=_get_path(
                values,
                "AGENTIC_WORKSPACES_ROOT",
                _get_path(values, "DURABLE_AGENT_WORKSPACES_PATH", DurablePathSettings.agent_workspaces),
            ),
            po_decisions=_get_path(values, "DURABLE_PO_DECISIONS_PATH", DurablePathSettings.po_decisions),
            sprints=_get_path(values, "DURABLE_SPRINTS_PATH", DurablePathSettings.sprints),
            confluence_mirror=_get_path(
                values,
                "DURABLE_CONFLUENCE_MIRROR_PATH",
                DurablePathSettings.confluence_mirror,
            ),
        ),
        workers=WorkerSettings(
            roles=_get_csv(values, "WORKER_ROLES", WorkerSettings.roles),
            target_project_path=_get(values, "TARGET_PROJECT_PATH", WorkerSettings.target_project_path),
        ),
    )


def settings_to_dict(settings: PlatformSettings) -> dict[str, Any]:
    """Convert settings into plain serializable values."""

    return _dataclass_to_dict(settings)


def _get(values: Mapping[str, str], key: str, default: str = "") -> str:
    value = values.get(key, default)
    if not isinstance(value, str):
        return default
    value = value.strip()
    return value if value else default


def _get_bool(values: Mapping[str, str], key: str, default: bool) -> bool:
    value = values.get(key)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(values: Mapping[str, str], key: str, default: int) -> int:
    value = values.get(key)
    if value is None or value == "":
        return default
    try:
        return int(value.strip())
    except ValueError:
        return default


def _get_path(values: Mapping[str, str], key: str, default: Path) -> Path:
    value = _get(values, key)
    return Path(value) if value else default


def _get_csv(values: Mapping[str, str], key: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = _get(values, key)
    if not value:
        return default
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _repository_traceability_settings(
    values: Mapping[str, str],
    prefix: str,
    *,
    default_repository: str = "",
    default_branch: str = "main",
    default_jira_development_panel_expected: bool = True,
) -> RepositoryTraceabilitySettings:
    return RepositoryTraceabilitySettings(
        repository=_get(values, f"{prefix}_REPOSITORY", default_repository),
        default_branch=_get(values, f"{prefix}_DEFAULT_BRANCH", default_branch),
        jira_development_panel_expected=_get_bool(
            values,
            f"{prefix}_JIRA_DEV_PANEL_EXPECTED",
            default_jira_development_panel_expected,
        ),
    )


def _dataclass_to_dict(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return {field.name: _dataclass_to_dict(getattr(value, field.name)) for field in fields(value)}
    return value
