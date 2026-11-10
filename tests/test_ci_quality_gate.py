import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


@pytest.fixture
def ci_workflow(project_root: Path) -> dict:
    return yaml.safe_load(
        (project_root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    )


def test_ci_runs_on_pr_updates_and_retargeting_without_branch_or_path_filters(
    ci_workflow: dict,
) -> None:
    triggers = ci_workflow["on"]
    assert set(triggers) == {"pull_request", "workflow_dispatch"}
    assert set(triggers["pull_request"]) == {"types"}
    assert {"opened", "synchronize", "reopened", "ready_for_review", "edited"} <= set(
        triggers["pull_request"]["types"]
    )


def test_ci_checks_have_stable_names_and_cannot_silently_ignore_failures(
    ci_workflow: dict,
) -> None:
    assert ci_workflow["permissions"] == {"contents": "read"}
    assert {key: job["name"] for key, job in ci_workflow["jobs"].items()} == {
        "pytest": "Pytest",
        "compose": "Docker Compose",
    }
    assert "secrets." not in json.dumps(ci_workflow)
    for job in ci_workflow["jobs"].values():
        assert job["runs-on"] == "ubuntu-latest"
        assert 0 < job["timeout-minutes"] <= 15
        assert "if" not in job
        assert "continue-on-error" not in job
        for step in job["steps"]:
            assert "continue-on-error" not in step
            if step.get("uses", "").startswith("actions/checkout@"):
                assert step["with"]["persist-credentials"] is False


def test_ci_installs_dev_extra_runs_full_suite_and_keeps_failure_output(
    ci_workflow: dict,
) -> None:
    steps = ci_workflow["jobs"]["pytest"]["steps"]
    setup = next(step for step in steps if step.get("uses", "").startswith("actions/setup-python@"))
    assert setup["with"]["python-version"] == "3.12"
    runs = [step["run"] for step in steps if "run" in step]
    assert runs == [
        'python -m pip install -e ".[dev]"',
        "python -m pytest --junitxml=data/ci/pytest.xml",
    ]
    assert all("if" not in step for step in steps if "run" in step)
    upload = next(step for step in steps if step.get("uses", "").startswith("actions/upload-artifact@"))
    assert upload["if"] == "always()"
    assert upload["with"]["path"] == "data/ci/pytest.xml"
    assert upload["with"]["name"] == "ci-pytest-results"


@pytest.fixture
def compose_workspace(project_root: Path, tmp_path: Path) -> Path:
    fixture_dir = tmp_path / ".github/ci"
    fixture_dir.mkdir(parents=True)
    shutil.copyfile(project_root / ".github/ci/compose.env", fixture_dir / "compose.env")
    # A local env file must neither be read nor overwritten by the CI command.
    (tmp_path / ".env").write_text("LOCAL_ENV_SENTINEL=keep-me\n", encoding="utf-8")
    return tmp_path


def _run_compose_step(ci_workflow: dict, workspace: Path, failure_call: int = 0) -> tuple:
    bash = shutil.which("bash")
    if bash is None or os.name != "posix":
        pytest.skip("A POSIX Bash environment is required to exercise the Ubuntu CI shell step")
    bin_dir = workspace / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(
        f"#!{sys.executable}\n"
        "import json, os, pathlib, sys\n"
        "log = pathlib.Path(os.environ['COMPOSE_TEST_LOG'])\n"
        "calls = json.loads(log.read_text()) if log.exists() else []\n"
        "args = sys.argv[1:]\n"
        "env = pathlib.Path(args[args.index('--env-file') + 1])\n"
        "calls.append({'args': args, 'env': env.read_text()})\n"
        "log.write_text(json.dumps(calls))\n"
        "sys.exit(23 if len(calls) == int(os.environ['COMPOSE_FAILURE_CALL']) else 0)\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    log = workspace / "compose-calls.json"
    temporary_root = workspace / "temporary"
    temporary_root.mkdir()
    step = next(step for step in ci_workflow["jobs"]["compose"]["steps"] if "run" in step)
    assert step["shell"] == "bash"
    assert "if" not in step
    result = subprocess.run(
        [bash, "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", step["run"]],
        cwd=workspace,
        env={
            **os.environ,
            "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"],
            "TMPDIR": str(temporary_root),
            "COMPOSE_TEST_LOG": str(log),
            "COMPOSE_FAILURE_CALL": str(failure_call),
        },
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert (workspace / ".env").read_text(encoding="utf-8") == "LOCAL_ENV_SENTINEL=keep-me\n"
    assert list(temporary_root.iterdir()) == []
    return result, json.loads(log.read_text()) if log.exists() else []


def test_compose_check_reports_not_applicable_when_compose_is_absent(
    ci_workflow: dict, compose_workspace: Path,
) -> None:
    result, calls = _run_compose_step(ci_workflow, compose_workspace)
    assert result.returncode == 0, result.stderr
    assert "not applicable" in result.stdout
    assert calls == []


@pytest.mark.parametrize("with_ssh_override", [False, True])
def test_compose_check_validates_all_profiles_with_isolated_non_secret_env(
    ci_workflow: dict, compose_workspace: Path, with_ssh_override: bool,
) -> None:
    (compose_workspace / "docker-compose.yml").touch()
    if with_ssh_override:
        (compose_workspace / "docker-compose.ssh.example.yml").touch()
    result, calls = _run_compose_step(ci_workflow, compose_workspace)
    assert result.returncode == 0, result.stderr
    assert len(calls) == (2 if with_ssh_override else 1)
    for call in calls:
        args = call["args"]
        assert args[0] == "compose"
        assert args[-2:] == ["config", "--quiet"]
        assert args[args.index("--profile") + 1] == "*"
        assert args[args.index("-f") + 1] == str(compose_workspace / "docker-compose.yml")
        isolated_root = Path(args[args.index("--project-directory") + 1])
        assert isolated_root != compose_workspace
        assert Path(args[args.index("--env-file") + 1]) == isolated_root / ".env"
        assert call["env"] == (compose_workspace / ".github/ci/compose.env").read_text(encoding="utf-8")
        assert "LOCAL_ENV_SENTINEL" not in call["env"]
    if with_ssh_override:
        assert calls[1]["args"][-4:-2] == [
            "-f", str(compose_workspace / "docker-compose.ssh.example.yml"),
        ]


@pytest.mark.parametrize("failure_call", [1, 2])
def test_compose_validation_failure_fails_the_gate(
    ci_workflow: dict, compose_workspace: Path, failure_call: int,
) -> None:
    (compose_workspace / "docker-compose.yml").touch()
    (compose_workspace / "docker-compose.ssh.example.yml").touch()
    result, calls = _run_compose_step(ci_workflow, compose_workspace, failure_call)
    assert result.returncode == 23
    assert len(calls) == failure_call
