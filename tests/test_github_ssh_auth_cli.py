import base64
import json
from pathlib import Path

from agentic_boilerplate.cli import main


def test_github_ssh_auth_diagnostic_reports_dry_run_plan_without_secrets(tmp_path: Path, capsys) -> None:
    private_key = "-----BEGIN" " OPENSSH PRIVATE KEY-----\nsecret-value\n-----END OPENSSH PRIVATE KEY-----\n"
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "GITHUB_REPOSITORY=ExampleOrg/example-repo",
                "GITHUB_AUTH_MODE=ssh",
                "GIT_REMOTE_MODE=ssh",
                f"GITHUB_SSH_PRIVATE_KEY_B64={base64.b64encode(private_key.encode()).decode()}",
            ]
        ),
        encoding="utf-8",
    )

    result = main(
        [
            "--env-file",
            str(env_file),
            "github",
            "ssh-auth-diagnostic",
            "--ssh-dir",
            str(tmp_path / "ssh"),
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert result == 0
    assert payload["configuration"]["ssh_key_source"] == "private_key_b64"
    assert payload["runtime"]["key_path"] == "<redacted>"
    assert payload["checks"][0]["name"] == "dry_run_plan"
    assert "secret-value" not in json.dumps(payload)


def test_github_ssh_auth_diagnostic_blocks_missing_key(tmp_path: Path, capsys) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "GITHUB_REPOSITORY=ExampleOrg/example-repo",
                "GITHUB_AUTH_MODE=ssh",
                "GIT_REMOTE_MODE=ssh",
            ]
        ),
        encoding="utf-8",
    )

    result = main(["--env-file", str(env_file), "github", "ssh-auth-diagnostic", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert result == 1
    assert payload["issues"][0]["field"] == "github.ssh_key"
