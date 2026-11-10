from pathlib import Path

import pytest

from agentic_boilerplate.config import (
    ConfigValidationError,
    build_container_image_references,
    load_settings,
    redacted_settings,
    require_valid_settings,
    settings_from_mapping,
    validate_required_settings,
    validate_image_registry_publish_settings,
)
from agentic_boilerplate.config.env import parse_env_file


def test_parse_env_file_supports_quotes_exports_and_comments(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "# comment",
                "export GITHUB_REPOSITORY=example-org/example",
                "JIRA_EMAIL='po@example.com'",
                'CODEX_DEFAULT_MODEL="gpt-5.5"',
                "CODEX_DEFAULT_REASONING=medium # inline comment",
                "CODEX_DEFAULT_SPEED=normal#not-a-comment",
            ]
        ),
        encoding="utf-8",
    )

    values = parse_env_file(env_file)

    assert values["GITHUB_REPOSITORY"] == "example-org/example"
    assert values["JIRA_EMAIL"] == "po@example.com"
    assert values["CODEX_DEFAULT_MODEL"] == "gpt-5.5"
    assert values["CODEX_DEFAULT_REASONING"] == "medium"
    assert values["CODEX_DEFAULT_SPEED"] == "normal#not-a-comment"


def test_load_settings_uses_env_file_and_environment_override(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "GITHUB_REPOSITORY=example-org/from-file",
                "JIRA_EMAIL=file@example.com",
                "JIRA_API_TOKEN=file-token",
            ]
        ),
        encoding="utf-8",
    )

    settings = load_settings(
        env_file,
        environ={
            "GITHUB_REPOSITORY": "example-org/from-env",
            "GITHUB_TOKEN": "github-token",
        },
    )

    assert settings.github.repository == "example-org/from-env"
    assert settings.github.token == "github-token"
    assert settings.jira.email == "file@example.com"


def test_github_token_accepts_gh_token_alias() -> None:
    settings = settings_from_mapping({"GH_TOKEN": "github-cli-token"})

    assert settings.github.token == "github-cli-token"


def test_github_token_prefers_explicit_github_token_over_alias() -> None:
    settings = settings_from_mapping(
        {
            "GITHUB_TOKEN": "preferred-token",
            "GH_TOKEN": "alias-token",
        }
    )

    assert settings.github.token == "preferred-token"


def test_github_ssh_settings_are_configurable_and_redacted() -> None:
    settings = settings_from_mapping(
        {
            "GITHUB_AUTH_MODE": "ssh",
            "GIT_REMOTE_MODE": "ssh",
            "GITHUB_SSH_KEY_PATH": "/run/secrets/github_ssh_key",
            "GITHUB_SSH_PRIVATE_KEY": "private-key-value",
            "GITHUB_SSH_PRIVATE_KEY_B64": "cHJpdmF0ZS1rZXk=",
            "GITHUB_SSH_KNOWN_HOSTS_PATH": "/run/secrets/github_known_hosts",
            "GITHUB_SSH_STRICT_HOST_KEY_CHECKING": "false",
        }
    )

    assert settings.github.auth_mode == "ssh"
    assert settings.github.remote_mode == "ssh"
    assert settings.github.ssh_key_path == "/run/secrets/github_ssh_key"
    assert settings.github.ssh_private_key == "private-key-value"
    assert settings.github.ssh_private_key_b64 == "cHJpdmF0ZS1rZXk="
    assert settings.github.ssh_known_hosts_path == "/run/secrets/github_known_hosts"
    assert settings.github.ssh_strict_host_key_checking is False
    assert redacted_settings(settings)["github"]["ssh_private_key"] == "***REDACTED***"


def test_settings_defaults_and_confluence_fallback() -> None:
    settings = settings_from_mapping(
        {
            "GITHUB_TOKEN": "github-token",
            "JIRA_EMAIL": "po@example.com",
            "JIRA_API_TOKEN": "jira-token",
        }
    )

    assert settings.github.default_branch == "main"
    assert settings.github.auth_mode == "https"
    assert settings.github.remote_mode == "https"
    assert settings.github.ssh_key_path == ""
    assert settings.github.ssh_private_key == ""
    assert settings.github.ssh_private_key_b64 == ""
    assert settings.github.ssh_known_hosts_path == ""
    assert settings.github.ssh_strict_host_key_checking is True
    assert settings.repositories.target_implementation.repository == ""
    assert settings.repositories.target_implementation.default_branch == "main"
    assert settings.repositories.target_implementation.jira_development_panel_expected is True
    assert settings.repositories.boilerplate_process.repository == "example-org/agentic-boilerplate"
    assert settings.repositories.boilerplate_process.default_branch == "main"
    assert settings.repositories.documentation.repository == ""
    assert settings.repositories.documentation.jira_development_panel_expected is False
    assert settings.repositories.automation.repository == ""
    assert settings.repositories.automation.jira_development_panel_expected is False
    assert settings.jira.project_key == "AGENT"
    assert settings.jira.board_id == "1"
    assert settings.confluence.space_key == "AGENT"
    assert settings.confluence.email == "po@example.com"
    assert settings.confluence.api_token == "jira-token"
    assert settings.documentation.provider == "github_pages"
    assert settings.documentation.github_pages_url == ""
    assert settings.documentation.github_pages_branch == "gh-pages"
    assert settings.documentation.github_pages_source_dir == "docs"
    assert settings.documentation.github_pages_deployment_mode == "github_actions"
    assert settings.documentation.uses_github_pages is True
    assert settings.documentation.uses_confluence is False
    assert settings.documentation.is_offline is False
    assert settings.agiletest.client_id == ""
    assert settings.agiletest.api_token == ""
    assert settings.figma.token == ""
    assert settings.figma.file_key == ""
    assert settings.figma.project_url == ""
    assert settings.image_registry.host == ""
    assert settings.image_registry.namespace == "agentic-boilerplate"
    assert settings.image_registry.image_tag == "local"
    assert settings.image_registry.push_enabled is False
    assert settings.image_registry.publish_dry_run is True
    assert settings.codex.default_model == "gpt-5.5"
    assert settings.codex.default_reasoning == "medium"
    assert settings.codex.default_speed == "normal"
    assert settings.codex.pause_on_limit is True
    assert settings.codex_limit_sentinel.enabled is False
    assert settings.codex_limit_sentinel.mode == "host_app_server"
    assert settings.codex_limit_sentinel.app_server_command == "codex app-server"
    assert settings.codex_limit_sentinel.account_scope_id == "default"
    assert settings.codex_limit_sentinel.guard_cutoff_percent == 90
    assert settings.codex_limit_sentinel.stale_after_seconds == 0
    assert settings.codex_limit_sentinel.future_tolerance_seconds == 30
    assert settings.database.url == "postgresql://agentic:agentic@localhost:5432/agentic"
    assert settings.database.migration_script_location == "migrations"
    assert settings.paths.po_inbox == Path("data/po-inbox")
    assert settings.paths.context_packs == Path("data/context-packs")
    assert settings.paths.codex_jobs == Path("data/codex-jobs")
    assert settings.paths.codex_results == Path("data/codex-results")
    assert settings.paths.codex_limits == Path("data/codex-limits")
    assert settings.paths.agent_state == Path("data/agent-state")
    assert settings.paths.agent_logs == Path("data/agent-logs")
    assert settings.paths.agent_workspaces == Path("data/agent-workspaces")
    assert settings.paths.po_decisions == Path("data/po-decisions")
    assert settings.paths.sprints == Path("data/sprints")
    assert settings.paths.confluence_mirror == Path("data/confluence-mirror")
    assert settings.workers.roles == (
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
    assert settings.workers.target_project_path == ""


def test_worker_roles_can_be_configured_from_csv() -> None:
    settings = settings_from_mapping(
        {
            "WORKER_ROLES": "developer, tester,release_manager",
        }
    )

    assert settings.workers.roles == ("developer", "tester", "release_manager")


def test_worker_target_project_path_can_be_configured() -> None:
    settings = settings_from_mapping(
        {
            "TARGET_PROJECT_PATH": "/workspace/projects/example",
            "AGENTIC_WORKSPACES_ROOT": "/workspace/data/agent-workspaces",
        }
    )

    assert settings.workers.target_project_path == "/workspace/projects/example"
    assert settings.paths.agent_workspaces == Path("/workspace/data/agent-workspaces")


def test_legacy_durable_agent_workspaces_path_is_supported() -> None:
    settings = settings_from_mapping(
        {
            "DURABLE_AGENT_WORKSPACES_PATH": "/durable/agent-workspaces",
        }
    )

    assert settings.paths.agent_workspaces == Path("/durable/agent-workspaces")


def test_project_repository_lanes_can_be_configured() -> None:
    settings = settings_from_mapping(
        {
            "GITHUB_REPOSITORY": "example-org/agentic-boilerplate",
            "GITHUB_DEFAULT_BRANCH": "main",
            "TARGET_IMPLEMENTATION_REPOSITORY": "example-org/ap-airline",
            "TARGET_IMPLEMENTATION_DEFAULT_BRANCH": "trunk",
            "TARGET_IMPLEMENTATION_JIRA_DEV_PANEL_EXPECTED": "true",
            "BOILERPLATE_PROCESS_REPOSITORY": "example-org/agentic-boilerplate",
            "BOILERPLATE_PROCESS_DEFAULT_BRANCH": "main",
            "DOCUMENTATION_REPOSITORY": "example-org/ap-docs",
            "DOCUMENTATION_JIRA_DEV_PANEL_EXPECTED": "false",
            "AUTOMATION_REPOSITORY": "example-org/ap-automation",
            "AUTOMATION_DEFAULT_BRANCH": "develop",
        }
    )

    assert settings.repositories.target_implementation.repository == "example-org/ap-airline"
    assert settings.repositories.target_implementation.default_branch == "trunk"
    assert settings.repositories.target_implementation.jira_development_panel_expected is True
    assert settings.repositories.boilerplate_process.repository == "example-org/agentic-boilerplate"
    assert settings.repositories.documentation.repository == "example-org/ap-docs"
    assert settings.repositories.documentation.jira_development_panel_expected is False
    assert settings.repositories.automation.repository == "example-org/ap-automation"
    assert settings.repositories.automation.default_branch == "develop"


def test_database_settings_can_be_configured() -> None:
    settings = settings_from_mapping(
        {
            "DATABASE_URL": "postgresql://agentic:agentic@postgres:5432/agentic",
            "DATABASE_MIGRATION_SCRIPT_LOCATION": "custom-migrations",
        }
    )

    assert settings.database.url == "postgresql://agentic:agentic@postgres:5432/agentic"
    assert settings.database.migration_script_location == "custom-migrations"


def test_agiletest_settings_can_be_configured_with_current_and_legacy_token_names() -> None:
    settings = settings_from_mapping(
        {
            "AGILETEST_CLIENT_ID": "client-id",
            "AGILETEST_API_TOKEN": "current-token",
            "AGILETEST_TOKEN": "legacy-token",
        }
    )

    assert settings.agiletest.client_id == "client-id"
    assert settings.agiletest.api_token == "current-token"

    legacy_settings = settings_from_mapping(
        {
            "AGILETEST_CLIENT_ID": "client-id",
            "AGILETEST_TOKEN": "legacy-token",
        }
    )

    assert legacy_settings.agiletest.api_token == "legacy-token"


def test_figma_settings_can_be_configured_for_optional_design_access() -> None:
    settings = settings_from_mapping(
        {
            "FIGMA_TOKEN": "figma-token",
            "FIGMA_FILE_KEY": "figma-file",
            "FIGMA_PROJECT_URL": "https://figma.example/file",
        }
    )

    assert settings.figma.token == "figma-token"
    assert settings.figma.file_key == "figma-file"
    assert settings.figma.project_url == "https://figma.example/file"


def test_documentation_provider_settings_are_configurable_and_redacted() -> None:
    settings = settings_from_mapping(
        {
            "DOCUMENTATION_PROVIDER": "both",
            "GITHUB_PAGES_DOCS_URL": "https://example-org.github.io/example",
            "GITHUB_PAGES_BRANCH": "docs-site",
            "GITHUB_PAGES_SOURCE_DIR": "site",
            "GITHUB_PAGES_CUSTOM_DOMAIN": "docs.example.com",
            "GITHUB_PAGES_DEPLOYMENT_MODE": "manual",
            "GITHUB_PAGES_DEPLOY_TOKEN": "pages-secret",
        }
    )

    assert settings.documentation.provider == "both"
    assert settings.documentation.github_pages_url == "https://example-org.github.io/example"
    assert settings.documentation.github_pages_branch == "docs-site"
    assert settings.documentation.github_pages_source_dir == "site"
    assert settings.documentation.github_pages_custom_domain == "docs.example.com"
    assert settings.documentation.github_pages_deployment_mode == "manual"
    assert settings.documentation.uses_github_pages is True
    assert settings.documentation.uses_confluence is True
    assert redacted_settings(settings)["documentation"]["github_pages_deploy_token"] == "***REDACTED***"


def test_image_registry_settings_build_oci_references_and_validate_push_mode() -> None:
    settings = settings_from_mapping(
        {
            "AGENTIC_IMAGE_REGISTRY_HOST": "ghcr.io",
            "AGENTIC_IMAGE_NAMESPACE": "example-org/agentic-boilerplate",
            "AGENTIC_IMAGE_TAG": "1.2.0",
            "AGENTIC_IMAGE_PUSH_ENABLED": "true",
            "AGENTIC_IMAGE_PUBLISH_DRY_RUN": "false",
            "AGENTIC_IMAGE_REGISTRY_CREDENTIAL_REF": "github-actions-secret",
        }
    )

    references = {
        image.component: image.reference
        for image in build_container_image_references(settings.image_registry)
    }

    assert references["operator-api"] == "ghcr.io/example-org/agentic-boilerplate/operator-api:1.2.0"
    assert references["operator-ui"] == "ghcr.io/example-org/agentic-boilerplate/operator-ui:1.2.0"
    assert references["worker-developer"] == (
        "ghcr.io/example-org/agentic-boilerplate/worker-developer:1.2.0"
    )
    assert settings.image_registry.push_enabled is True
    assert settings.image_registry.publish_dry_run is False
    assert validate_image_registry_publish_settings(settings.image_registry) == ()


def test_image_registry_publish_mode_requires_host_and_credentials_without_leaking_values() -> None:
    settings = settings_from_mapping(
        {
            "AGENTIC_IMAGE_PUSH_ENABLED": "true",
            "AGENTIC_IMAGE_REGISTRY_USERNAME": "registry-user",
        }
    )

    issues = validate_image_registry_publish_settings(settings.image_registry)

    assert any("AGENTIC_IMAGE_REGISTRY_HOST" in issue for issue in issues)
    assert any("credential" in issue.lower() for issue in issues)
    assert "registry-user" not in " ".join(issues)


def test_codex_limit_sentinel_settings_are_configurable_and_redacted() -> None:
    settings = settings_from_mapping(
        {
            "CODEX_LIMIT_SENTINEL_ENABLED": "true",
            "CODEX_LIMIT_SENTINEL_MODE": "host_app_server",
            "CODEX_LIMIT_APP_SERVER_COMMAND": "codex app-server --safe",
            "CODEX_LIMIT_APP_SERVER_TRANSPORT": "stdio",
            "CODEX_LIMIT_ACCOUNT_SCOPE_ID": "chatgpt-primary",
            "CODEX_LIMIT_BUCKET_ID": "codex",
            "CODEX_LIMIT_GUARD_CUTOFF_PERCENT": "85",
            "CODEX_LIMIT_STALE_AFTER_SECONDS": "300",
            "CODEX_LIMIT_FUTURE_TOLERANCE_SECONDS": "45",
            "CODEX_LIMIT_REFRESH_BEFORE_STAGE": "true",
            "CODEX_LIMIT_RECORD_SOURCE": "codex_app_server",
            "CODEX_ACCESS_TOKEN": "codex-token",
        }
    )

    assert settings.codex_limit_sentinel.enabled is True
    assert settings.codex_limit_sentinel.app_server_command == "codex app-server --safe"
    assert settings.codex_limit_sentinel.account_scope_id == "chatgpt-primary"
    assert settings.codex_limit_sentinel.bucket_id == "codex"
    assert settings.codex_limit_sentinel.guard_cutoff_percent == 85
    assert settings.codex_limit_sentinel.stale_after_seconds == 300
    assert settings.codex_limit_sentinel.future_tolerance_seconds == 45
    assert settings.codex_limit_sentinel.refresh_before_stage is True
    assert settings.codex_limit_sentinel.access_token == "codex-token"
    assert redacted_settings(settings)["codex_limit_sentinel"]["access_token"] == "***REDACTED***"


def test_empty_confluence_values_fall_back_to_jira_account(tmp_path: Path) -> None:
    env_file = tmp_path / ".env.example"
    env_file.write_text(
        "\n".join(
            [
                "CONFLUENCE_EMAIL=",
                "CONFLUENCE_API_TOKEN=",
            ]
        ),
        encoding="utf-8",
    )

    settings = load_settings(
        env_file,
        environ={
            "GITHUB_TOKEN": "github-token",
            "JIRA_EMAIL": "po@example.com",
            "JIRA_API_TOKEN": "jira-token",
        },
    )

    require_valid_settings(settings)
    assert settings.confluence.email == "po@example.com"
    assert settings.confluence.api_token == "jira-token"


def test_missing_required_values_are_reported_without_values() -> None:
    settings = settings_from_mapping({})

    issues = validate_required_settings(settings)

    assert {issue.path for issue in issues} == {
        "github.token",
        "jira.email",
        "jira.api_token",
    }
    with pytest.raises(ConfigValidationError) as exc_info:
        require_valid_settings(settings)

    message = str(exc_info.value)
    assert "github.token" in message
    assert "jira.api_token" in message
    assert "secret" not in message.lower()


def test_validate_required_settings_rejects_invalid_documentation_provider() -> None:
    settings = settings_from_mapping({"DOCUMENTATION_PROVIDER": "wiki"})

    issues = validate_required_settings(settings)

    assert any(issue.path == "documentation.provider" for issue in issues)
    assert "wiki" not in " ".join(issue.message for issue in issues)


def test_secret_redaction_masks_tokens() -> None:
    settings = settings_from_mapping(
        {
            "GITHUB_TOKEN": "github-secret",
            "JIRA_EMAIL": "po@example.com",
            "JIRA_API_TOKEN": "jira-secret",
            "CONFLUENCE_API_TOKEN": "confluence-secret",
            "FIGMA_TOKEN": "figma-secret",
            "AGENTIC_IMAGE_REGISTRY_TOKEN": "registry-secret",
        }
    )

    redacted = redacted_settings(settings)

    assert redacted["github"]["token"] == "***REDACTED***"
    assert redacted["jira"]["api_token"] == "***REDACTED***"
    assert redacted["confluence"]["api_token"] == "***REDACTED***"
    assert redacted["figma"]["token"] == "***REDACTED***"
    assert redacted["image_registry"]["token"] == "***REDACTED***"
    assert "github-secret" not in str(redacted)
    assert "jira-secret" not in str(redacted)
    assert "confluence-secret" not in str(redacted)
    assert "registry-secret" not in str(redacted)
