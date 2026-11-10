import base64
import stat
from pathlib import Path

from agentic_boilerplate.config import redacted_settings, settings_from_mapping
from agentic_boilerplate.integrations import (
    GitSSHAuthConfig,
    build_git_ssh_command,
    git_ssh_auth_config_from_settings,
    github_ssh_remote_url,
    prepare_git_ssh_runtime_environment,
    redacted_git_ssh_auth_summary,
    redacted_git_ssh_runtime_summary,
    selected_git_ssh_key_source,
    validate_git_ssh_auth,
)


PRIVATE_KEY = "-----BEGIN" " OPENSSH PRIVATE KEY-----\nsecret-key-material\n-----END OPENSSH PRIVATE KEY-----\n"


def test_git_ssh_auth_blocks_missing_key_when_ssh_mode_enabled() -> None:
    config = GitSSHAuthConfig(repository="ExampleOrg/example-repo", auth_mode="ssh", remote_mode="ssh")

    issues = validate_git_ssh_auth(config)

    assert any(issue.field == "github.ssh_key" for issue in issues)


def test_git_ssh_auth_accepts_key_path_and_builds_redacted_runtime() -> None:
    config = GitSSHAuthConfig(
        repository="ExampleOrg/example-repo",
        auth_mode="ssh",
        remote_mode="ssh",
        ssh_key_path="/run/secrets/github_ssh_key",
    )

    assert validate_git_ssh_auth(config) == ()
    assert selected_git_ssh_key_source(config) == "path"
    assert github_ssh_remote_url(config.repository) == "git@github.com:ExampleOrg/example-repo.git"
    command = build_git_ssh_command(config)
    runtime = prepare_git_ssh_runtime_environment(config, ssh_dir=Path("/tmp/unused-agentic-test"))
    summary = redacted_git_ssh_runtime_summary(runtime)

    assert "-i /run/secrets/github_ssh_key" in command
    assert runtime.key_path == Path("/run/secrets/github_ssh_key")
    assert summary["key_path"] == "<redacted>"
    assert "/run/secrets/github_ssh_key" not in summary["git_ssh_command"]


def test_git_ssh_auth_materializes_base64_key_with_secure_permissions(tmp_path: Path) -> None:
    encoded = base64.b64encode(PRIVATE_KEY.encode()).decode()
    config = GitSSHAuthConfig(
        repository="ExampleOrg/example-repo",
        auth_mode="ssh",
        remote_mode="ssh",
        ssh_private_key_b64=encoded,
    )

    runtime = prepare_git_ssh_runtime_environment(config, ssh_dir=tmp_path / "ssh")

    assert runtime.key_source == "private_key_b64"
    assert runtime.key_path is not None
    assert runtime.key_path.read_text(encoding="utf-8") == PRIVATE_KEY
    assert stat.S_IMODE(runtime.key_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(runtime.key_path.parent.stat().st_mode) == 0o700
    assert "secret-key-material" not in runtime.git_ssh_command


def test_git_ssh_auth_uses_deterministic_precedence_and_redacts_unused_values() -> None:
    encoded = base64.b64encode(PRIVATE_KEY.encode()).decode()
    config = GitSSHAuthConfig(
        repository="ExampleOrg/example-repo",
        auth_mode="ssh",
        remote_mode="ssh",
        ssh_key_path="/run/secrets/github_ssh_key",
        ssh_private_key=PRIVATE_KEY,
        ssh_private_key_b64=encoded,
    )

    assert selected_git_ssh_key_source(config) == "path"
    summary = redacted_git_ssh_auth_summary(config)

    assert summary["ssh_key_source"] == "path"
    assert summary["ssh_key_path_configured"] is True
    assert summary["ssh_private_key_configured"] is True
    assert summary["ssh_private_key_b64_configured"] is True
    assert "secret-key-material" not in str(summary)
    assert encoded not in str(summary)


def test_settings_load_git_ssh_auth_fields_and_redacts_secret_values() -> None:
    encoded = base64.b64encode(PRIVATE_KEY.encode()).decode()
    settings = settings_from_mapping(
        {
            "GITHUB_REPOSITORY": "ExampleOrg/example-repo",
            "GITHUB_AUTH_MODE": "ssh",
            "GIT_REMOTE_MODE": "ssh",
            "GITHUB_SSH_KEY_PATH": "/run/secrets/github_ssh_key",
            "GITHUB_SSH_PRIVATE_KEY_B64": encoded,
        }
    )

    config = git_ssh_auth_config_from_settings(settings)
    redacted = redacted_settings(settings)

    assert config.auth_mode == "ssh"
    assert config.remote_mode == "ssh"
    assert config.ssh_key_path == "/run/secrets/github_ssh_key"
    assert config.ssh_private_key_b64 == encoded
    assert redacted["github"]["ssh_key_path"] == "***REDACTED***"
    assert redacted["github"]["ssh_private_key_b64"] == "***REDACTED***"
