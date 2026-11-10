"""Git SSH authentication helpers for Docker workers."""

from __future__ import annotations

import base64
import binascii
import os
import shlex
from dataclasses import dataclass
from pathlib import Path

from agentic_boilerplate.config.settings import GitHubSettings, PlatformSettings
from agentic_boilerplate.integrations.github import GitHubAdapterError

VALID_AUTH_MODES = {"https", "ssh"}
VALID_REMOTE_MODES = {"https", "ssh"}


@dataclass(frozen=True)
class GitSSHAuthConfig:
    """Git SSH settings with secret-bearing values kept internal."""

    repository: str
    auth_mode: str = "https"
    remote_mode: str = "https"
    ssh_key_path: str = ""
    ssh_private_key: str = ""
    ssh_private_key_b64: str = ""
    ssh_known_hosts_path: str = ""
    ssh_strict_host_key_checking: bool = True


@dataclass(frozen=True)
class GitSSHValidationIssue:
    """One redacted Git SSH configuration validation issue."""

    field: str
    message: str


@dataclass(frozen=True)
class GitSSHRuntimeEnvironment:
    """Prepared Git SSH runtime data safe to expose after redaction."""

    enabled: bool
    key_source: str = ""
    key_path: Path | None = None
    known_hosts_path: Path | None = None
    git_ssh_command: str = ""
    remote_url: str = ""

    @property
    def env(self) -> dict[str, str]:
        if not self.enabled:
            return {}
        return {
            "GIT_SSH_COMMAND": self.git_ssh_command,
            "GITHUB_REMOTE_URL": self.remote_url,
        }


def git_ssh_auth_config_from_settings(settings: PlatformSettings) -> GitSSHAuthConfig:
    """Build Git SSH auth config from platform settings."""

    github = settings.github
    return GitSSHAuthConfig(
        repository=github.repository,
        auth_mode=github.auth_mode,
        remote_mode=github.remote_mode,
        ssh_key_path=github.ssh_key_path,
        ssh_private_key=github.ssh_private_key,
        ssh_private_key_b64=github.ssh_private_key_b64,
        ssh_known_hosts_path=github.ssh_known_hosts_path,
        ssh_strict_host_key_checking=github.ssh_strict_host_key_checking,
    )


def validate_git_ssh_auth(config: GitSSHAuthConfig) -> tuple[GitSSHValidationIssue, ...]:
    """Validate Git auth config without exposing secret values."""

    issues: list[GitSSHValidationIssue] = []
    if config.auth_mode not in VALID_AUTH_MODES:
        issues.append(GitSSHValidationIssue("github.auth_mode", "GITHUB_AUTH_MODE must be https or ssh."))
    if config.remote_mode not in VALID_REMOTE_MODES:
        issues.append(GitSSHValidationIssue("github.remote_mode", "GIT_REMOTE_MODE must be https or ssh."))
    if config.auth_mode != "ssh":
        return tuple(issues)
    if selected_git_ssh_key_source(config) == "":
        issues.append(
            GitSSHValidationIssue(
                "github.ssh_key",
                "Docker SSH auth requires GITHUB_SSH_KEY_PATH, GITHUB_SSH_PRIVATE_KEY, or GITHUB_SSH_PRIVATE_KEY_B64.",
            )
        )
    if selected_git_ssh_key_source(config) == "private_key_b64":
        try:
            _decode_private_key_b64(config.ssh_private_key_b64)
        except ValueError:
            issues.append(
                GitSSHValidationIssue(
                    "github.ssh_private_key_b64",
                    "GITHUB_SSH_PRIVATE_KEY_B64 must be valid base64-encoded private key material.",
                )
            )
    return tuple(issues)


def selected_git_ssh_key_source(config: GitSSHAuthConfig) -> str:
    """Select the deterministic SSH key source.

    Precedence intentionally favors mounted files over environment values,
    then base64 values over raw multiline values.
    """

    if config.auth_mode != "ssh":
        return ""
    if config.ssh_key_path.strip():
        return "path"
    if config.ssh_private_key_b64.strip():
        return "private_key_b64"
    if config.ssh_private_key.strip():
        return "private_key"
    return ""


def github_ssh_remote_url(repository: str) -> str:
    """Return the GitHub SSH remote URL for an owner/name repository."""

    owner, name = _repository_parts(repository)
    return f"git@github.com:{owner}/{name}.git"


def build_git_ssh_command(
    config: GitSSHAuthConfig,
    *,
    key_path: Path | str | None = None,
    known_hosts_path: Path | str | None = None,
) -> str:
    """Build the Git SSH command used by worker Git calls."""

    source = selected_git_ssh_key_source(config)
    if config.auth_mode != "ssh" or not source:
        return ""
    selected_key_path = Path(key_path or config.ssh_key_path or "/tmp/agentic-git-ssh/id_github")
    selected_known_hosts = Path(known_hosts_path or config.ssh_known_hosts_path) if (
        known_hosts_path or config.ssh_known_hosts_path
    ) else None
    parts = [
        "ssh",
        "-i",
        shlex.quote(str(selected_key_path)),
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "BatchMode=yes",
    ]
    if selected_known_hosts is not None:
        parts.extend(("-o", "UserKnownHostsFile=" + shlex.quote(str(selected_known_hosts))))
    strict_value = "yes" if config.ssh_strict_host_key_checking else "accept-new"
    parts.extend(("-o", f"StrictHostKeyChecking={strict_value}"))
    return " ".join(parts)


def prepare_git_ssh_runtime_environment(
    config: GitSSHAuthConfig,
    *,
    ssh_dir: Path | str,
) -> GitSSHRuntimeEnvironment:
    """Prepare SSH key material for a Docker worker.

    Mounted key files are used in place. Env-supplied key material is written to
    an ephemeral directory with 0600 permissions.
    """

    issues = validate_git_ssh_auth(config)
    if issues:
        raise ValueError("; ".join(f"{issue.field}: {issue.message}" for issue in issues))
    if config.auth_mode != "ssh":
        return GitSSHRuntimeEnvironment(enabled=False)

    key_source = selected_git_ssh_key_source(config)
    runtime_dir = Path(ssh_dir)
    runtime_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(runtime_dir, 0o700)

    if key_source == "path":
        key_path = Path(config.ssh_key_path)
    else:
        key_path = runtime_dir / "id_github"
        private_key = (
            _decode_private_key_b64(config.ssh_private_key_b64)
            if key_source == "private_key_b64"
            else config.ssh_private_key
        )
        key_path.write_text(_normalize_private_key(private_key), encoding="utf-8")
        os.chmod(key_path, 0o600)

    known_hosts_path = Path(config.ssh_known_hosts_path) if config.ssh_known_hosts_path else None
    return GitSSHRuntimeEnvironment(
        enabled=True,
        key_source=key_source,
        key_path=key_path,
        known_hosts_path=known_hosts_path,
        git_ssh_command=build_git_ssh_command(config, key_path=key_path, known_hosts_path=known_hosts_path),
        remote_url=github_ssh_remote_url(config.repository),
    )


def redacted_git_ssh_auth_summary(config: GitSSHAuthConfig) -> dict[str, object]:
    """Return operator-safe Git SSH configuration metadata."""

    return {
        "repository": config.repository,
        "auth_mode": config.auth_mode,
        "remote_mode": config.remote_mode,
        "ssh_key_source": selected_git_ssh_key_source(config),
        "ssh_key_path_configured": bool(config.ssh_key_path.strip()),
        "ssh_private_key_configured": bool(config.ssh_private_key.strip()),
        "ssh_private_key_b64_configured": bool(config.ssh_private_key_b64.strip()),
        "ssh_known_hosts_path_configured": bool(config.ssh_known_hosts_path.strip()),
        "ssh_strict_host_key_checking": config.ssh_strict_host_key_checking,
    }


def redacted_git_ssh_runtime_summary(runtime: GitSSHRuntimeEnvironment) -> dict[str, object]:
    """Return runtime metadata without secret-bearing file paths or key values."""

    return {
        "enabled": runtime.enabled,
        "key_source": runtime.key_source,
        "key_path": "<redacted>" if runtime.key_path else "",
        "known_hosts_path": "<redacted>" if runtime.known_hosts_path else "",
        "remote_url": runtime.remote_url,
        "git_ssh_command": _redact_ssh_command(runtime.git_ssh_command),
    }


def redact_git_ssh_text(text: str, config: GitSSHAuthConfig) -> str:
    """Redact configured secret values from command output."""

    redacted = text
    for value in (config.ssh_private_key, config.ssh_private_key_b64, config.ssh_key_path):
        if value:
            redacted = redacted.replace(value, "***REDACTED***")
    return redacted


def _repository_parts(repository: str) -> tuple[str, str]:
    parts = tuple(part.strip() for part in repository.split("/", maxsplit=1))
    if len(parts) != 2 or not all(parts):
        raise GitHubAdapterError("GitHub repository must use owner/name format.")
    return parts


def _decode_private_key_b64(value: str) -> str:
    try:
        return base64.b64decode(value.encode("ascii"), validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise ValueError("Invalid base64 private key.") from exc


def _normalize_private_key(value: str) -> str:
    stripped = value.strip()
    return stripped + "\n" if stripped else ""


def _redact_ssh_command(command: str) -> str:
    if not command:
        return ""
    parts = shlex.split(command)
    redacted_parts: list[str] = []
    redact_next = False
    for part in parts:
        if redact_next:
            redacted_parts.append("<redacted>")
            redact_next = False
            continue
        redacted_parts.append(part)
        if part == "-i":
            redact_next = True
    return " ".join(shlex.quote(part) for part in redacted_parts)
