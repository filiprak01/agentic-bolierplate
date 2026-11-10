from pathlib import Path

BASELINE = Path("docs/image-registry-publishing-baseline.md")
ENV_EXAMPLE = Path(".env.example")
COMPOSE = Path("docker-compose.yml")


def test_image_registry_baseline_document_covers_release_boundary_and_targets() -> None:
    text = BASELINE.read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    assert "Release 1.2 baseline" in text
    assert "does not push images automatically by default" in normalized
    assert "OCI-compatible" in text
    assert "JFrog Artifactory" in text
    assert "build-only" in text


def test_image_registry_baseline_documents_required_image_families() -> None:
    text = BASELINE.read_text(encoding="utf-8")

    for image in (
        "agentic-boilerplate/operator-api:local",
        "agentic-boilerplate/operator-ui:local",
        "agentic-boilerplate/worker-developer:local",
        "agentic-boilerplate/worker-devops-platform:local",
    ):
        assert image in text


def test_env_example_exposes_registry_and_compose_image_variables() -> None:
    text = ENV_EXAMPLE.read_text(encoding="utf-8")

    for variable in (
        "AGENTIC_IMAGE_REGISTRY_HOST=",
        "AGENTIC_IMAGE_NAMESPACE=agentic-boilerplate",
        "AGENTIC_IMAGE_PUSH_ENABLED=false",
        "AGENTIC_OPERATOR_API_IMAGE=agentic-boilerplate/operator-api:local",
        "AGENTIC_OPERATOR_UI_IMAGE=agentic-boilerplate/operator-ui:local",
        "AGENTIC_WORKER_DEVELOPER_IMAGE=agentic-boilerplate/worker-developer:local",
    ):
        assert variable in text


def test_docker_compose_uses_explicit_image_variables_for_operator_and_workers() -> None:
    text = COMPOSE.read_text(encoding="utf-8")

    for phrase in (
        "image: ${AGENTIC_OPERATOR_API_IMAGE:-agentic-boilerplate/operator-api:local}",
        "image: ${AGENTIC_OPERATOR_UI_IMAGE:-agentic-boilerplate/operator-ui:local}",
        "image: ${AGENTIC_WORKER_DEVELOPER_IMAGE:-agentic-boilerplate/worker-developer:local}",
        "image: ${AGENTIC_WORKER_DEVOPS_PLATFORM_IMAGE:-agentic-boilerplate/worker-devops-platform:local}",
    ):
        assert phrase in text

    assert text.index(
        "image: ${AGENTIC_OPERATOR_API_IMAGE:-agentic-boilerplate/operator-api:local}"
    ) < text.index(
        "image: ${AGENTIC_WORKER_DEVELOPER_IMAGE:-agentic-boilerplate/worker-developer:local}"
    )
