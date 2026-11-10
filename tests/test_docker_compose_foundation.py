import re
from pathlib import Path


def test_docker_compose_defines_required_services(project_root: Path) -> None:
    compose = _compose_text(project_root)

    for service_name in (
        "api",
        "operator-ui",
        "worker",
        "worker-product-planning",
        "worker-architecture",
        "worker-developer",
        "worker-review",
        "worker-tester",
        "worker-release-manager",
        "worker-scheduler",
        "worker-platform",
        "worker-frontend",
        "worker-ui-ux",
        "worker-security",
        "worker-docs-confluence",
        "worker-devops-platform",
        "worker-data-persistence",
        "postgres",
        "redis",
    ):
        assert re.search(rf"^  {service_name}:\n", compose, re.MULTILINE)


def test_agentic_services_load_env_and_mount_durable_paths(project_root: Path) -> None:
    compose = _compose_text(project_root)

    assert "x-agentic-build:" in compose
    assert "env_file:\n    - .env" in compose
    assert "- .:/workspace" in compose
    assert "- ./data:/workspace/data" in compose
    assert "- ${TARGET_PROJECT_PATH:-.}:/workspace/project" in compose

    for service_name in (
        "api",
        "worker",
        "worker-product-planning",
        "worker-architecture",
        "worker-developer",
        "worker-review",
        "worker-tester",
        "worker-release-manager",
        "worker-scheduler",
        "worker-platform",
    ):
        block = _service_block(compose, service_name)

        assert "<<: *agentic-build" in block


def test_postgres_and_redis_use_named_volumes(project_root: Path) -> None:
    compose = _compose_text(project_root)
    postgres = _service_block(compose, "postgres")
    redis = _service_block(compose, "redis")

    assert "- postgres-data:/var/lib/postgresql/data" in postgres
    assert "- redis-data:/data" in redis
    assert re.search(r"^volumes:\n  postgres-data:\n  redis-data:\n", compose, re.MULTILINE)


def test_api_and_workers_start_without_live_integration_commands(project_root: Path) -> None:
    compose = _compose_text(project_root)

    api = _service_block(compose, "api")
    api_command = _command_block(api)
    assert "restart: unless-stopped" in api
    assert '${AGENTIC_API_PORT:-8000}:8000' in api
    assert "api serve --data-root /workspace/data --host 0.0.0.0 --port 8000" in api_command
    assert "--inbox-root /workspace/data/po-inbox" in api_command
    assert "--data-root /workspace/data" in api_command
    assert "while true; do sleep 3600; done" not in api_command
    assert "time.sleep(3600)" not in api_command
    assert "x-agentic-worker-command:" in compose
    assert "while true; do agentic worker run-once" in compose
    assert "AGENTIC_WORKER_POLL_INTERVAL_SECONDS" in compose

    for service_name, role in _role_worker_services().items():
        block = _service_block(compose, service_name)

        assert "command: *agentic-worker-command" in block
        assert role in block

    worker_command = _worker_command_anchor(compose)
    assert "github" not in worker_command.lower()
    assert "jira" not in worker_command.lower()
    assert "confluence" not in worker_command.lower()
    assert "codex" not in worker_command.lower()


def test_operator_profile_runs_dockerized_inbox_api_and_ui(project_root: Path) -> None:
    compose = _compose_text(project_root)
    api = _service_block(compose, "api")
    operator_ui = _service_block(compose, "operator-ui")

    assert 'profiles: ["operator"]' in api
    assert 'profiles: ["operator"]' in operator_ui
    assert "image: ${AGENTIC_OPERATOR_API_IMAGE:-agentic-boilerplate/operator-api:local}" in api
    assert "image: ${AGENTIC_OPERATOR_UI_IMAGE:-agentic-boilerplate/operator-ui:local}" in operator_ui
    assert "${AGENTIC_OPERATOR_UI_PORT:-5173}:8080" in operator_ui
    assert "condition: service_healthy" in operator_ui
    assert "/health" in api
    assert "http://127.0.0.1:8080/" in operator_ui

    assert "VITE_AGENTIC_API_BASE_URL" in operator_ui
    assert "http://localhost:8000" in operator_ui
    assert "VITE_AGENTIC_PROJECT_NAME: ${VITE_AGENTIC_PROJECT_NAME:-Agentic Boilerplate}" in operator_ui
    assert "VITE_AGENTIC_JIRA_PROJECT_KEY: ${JIRA_PROJECT_KEY:-AGENT}" in operator_ui
    assert "AP MVP Test" not in operator_ui
    assert "TOKEN" not in operator_ui
    assert "PASSWORD" not in operator_ui
    assert "SECRET" not in operator_ui


def test_role_worker_services_have_role_specific_environment(project_root: Path) -> None:
    compose = _compose_text(project_root)

    for service_name, role in _role_worker_services().items():
        block = _service_block(compose, service_name)

        assert f"AGENTIC_SERVICE_ROLE: {role}" in block
        assert "AGENTIC_WORKER_ID:" in block
        if service_name != "worker":
            assert 'profiles: ["workers",' in block


def test_dockerfile_installs_local_package_without_copying_env_or_data(project_root: Path) -> None:
    dockerfile = (project_root / "Dockerfile").read_text(encoding="utf-8")
    dockerignore = (project_root / ".dockerignore").read_text(encoding="utf-8")

    assert "python:3.11-slim" in dockerfile
    assert "python -m pip install --no-cache-dir -e ." in dockerfile
    assert ".env" in dockerignore
    assert "data" in dockerignore


def _compose_text(project_root: Path) -> str:
    return (project_root / "docker-compose.yml").read_text(encoding="utf-8")


def _service_block(compose: str, service_name: str) -> str:
    match = re.search(rf"^  {service_name}:\n(?P<body>(?:    .*\n|      .*\n|        .*\n|          .*\n)*)", compose, re.MULTILINE)
    assert match is not None
    return match.group("body")


def _command_block(service_block: str) -> str:
    match = re.search(r"^    command:\n(?P<body>(?:      .*\n)*)", service_block, re.MULTILINE)
    assert match is not None
    return match.group("body")


def _worker_command_anchor(compose: str) -> str:
    match = re.search(r"^x-agentic-worker-command: &agentic-worker-command\n(?P<body>(?:  .*\n)*)", compose, re.MULTILINE)
    assert match is not None
    return match.group("body")


def _role_worker_services() -> dict[str, str]:
    return {
        "worker": "platform",
        "worker-product-planning": "product_planning",
        "worker-architecture": "architecture",
        "worker-developer": "developer",
        "worker-review": "review",
        "worker-tester": "tester",
        "worker-release-manager": "release_manager",
        "worker-scheduler": "scheduler",
        "worker-platform": "platform",
        "worker-frontend": "frontend",
        "worker-ui-ux": "ui_ux",
        "worker-security": "security",
        "worker-docs-confluence": "docs_confluence",
        "worker-devops-platform": "devops_platform",
        "worker-data-persistence": "data_persistence",
    }
