from pathlib import Path
import json
import subprocess

import pytest

from scripts.release.export_public_release import POLICY_PATH, export_public_release


def _commit_fixture(repo: Path) -> None:
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "fixture"], cwd=repo, check=True, capture_output=True)


def _required_fixture(repo: Path) -> tuple[str, str]:
    private_org = "SideQuests" + "Company"
    private_site = "filip-" + "space.atlassian.net"
    for path in (
        "AGENTS.md",
        "CLAUDE.md",
        "LICENSE",
        "README.md",
        "SECURITY.md",
        ".agents/skills/example/SKILL.md",
        "ai_agents/roles/developer.md",
        "ai_agents/session_starters/README.md",
        "docs/getting-started.md",
    ):
        target = repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"fixture for {path}\n", encoding="utf-8")
    policy = repo / POLICY_PATH
    policy.parent.mkdir(parents=True, exist_ok=True)
    policy.write_text(
        json.dumps(
            {
                "replacements": [
                    {"private": private_org, "public": "example-org"},
                    {"private": private_site, "public": "example.atlassian.net"},
                ]
            }
        ),
        encoding="utf-8",
    )
    return private_org, private_site


def test_export_keeps_agent_docs_and_excludes_private_runtime_data(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    private_org, private_site = _required_fixture(source)
    (source / "src").mkdir()
    (source / "src" / "example.py").write_text(
        f"repo = '{private_org}/agentic-boilerplate'\n"
        f"jira = 'https://{private_site}'\n",
        encoding="utf-8",
    )
    (source / "data" / "agent-logs").mkdir(parents=True)
    (source / "data" / "agent-logs" / "private.md").write_text("private", encoding="utf-8")
    (source / "docs" / "reports").mkdir(parents=True)
    (source / "docs" / "reports" / "internal.md").write_text("internal", encoding="utf-8")
    _commit_fixture(source)

    destination = tmp_path / "public"
    manifest = export_public_release(source, destination)

    assert (destination / "AGENTS.md").is_file()
    assert (destination / "CLAUDE.md").is_file()
    assert (destination / ".agents/skills/example/SKILL.md").is_file()
    assert (destination / "ai_agents/roles/developer.md").is_file()
    assert (destination / "ai_agents/session_starters/README.md").is_file()
    assert (destination / "docs/getting-started.md").is_file()
    assert (destination / "docs/reports/index.md").is_file()
    assert not (destination / "data").exists()
    assert not (destination / POLICY_PATH).exists()
    assert "example-org/agentic-boilerplate" in (destination / "src/example.py").read_text()
    assert "example.atlassian.net" in (destination / "src/example.py").read_text()
    assert manifest["license"] == "Apache-2.0"


def test_export_rejects_secret_outside_test_fixtures(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _required_fixture(source)
    (source / "src").mkdir()
    token = "github_" + "pat_" + "A" * 30
    (source / "src" / "unsafe.py").write_text(f"TOKEN = {token!r}\n", encoding="utf-8")
    _commit_fixture(source)

    with pytest.raises(ValueError, match="src/unsafe.py:github_token"):
        export_public_release(source, tmp_path / "public")

def test_export_neutralizes_static_test_secret_without_changing_runtime_value(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _required_fixture(source)
    (source / "tests").mkdir()
    token = "github_" + "pat_" + "B" * 30
    (source / "tests" / "test_fixture.py").write_text(
        f"TOKEN = {token!r}\n"
        "def test_value():\n"
        f"    assert TOKEN == {token!r}\n",
        encoding="utf-8",
    )
    _commit_fixture(source)

    destination = tmp_path / "public"
    export_public_release(source, destination)
    exported = (destination / "tests/test_fixture.py").read_text(encoding="utf-8")

    assert "github_pat_" not in exported
    compile(exported, "test_fixture.py", "exec")

def test_export_preserves_bytes_literal_type_when_neutralizing_fixture(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _required_fixture(source)
    (source / "tests").mkdir()
    token = ("-----BEGIN " + "OPENSSH PRIVATE KEY-----").encode()
    (source / "tests" / "test_bytes_fixture.py").write_bytes(
        b"TOKEN = b\"" + token + b"\\nfixture\"\n"
    )
    _commit_fixture(source)

    destination = tmp_path / "public"
    export_public_release(source, destination)
    exported = (destination / "tests/test_bytes_fixture.py").read_text(encoding="utf-8")

    assert "-----BEGIN" " OPENSSH PRIVATE KEY-----" not in exported
    compile(exported, "test_bytes_fixture.py", "exec")
