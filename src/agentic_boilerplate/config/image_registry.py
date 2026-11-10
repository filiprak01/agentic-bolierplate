"""Container image registry naming and publish-mode helpers."""

from __future__ import annotations

from dataclasses import dataclass

from agentic_boilerplate.config.settings import ImageRegistrySettings

IMAGE_COMPONENTS: tuple[str, ...] = (
    "operator-api",
    "operator-ui",
    "worker-platform",
    "worker-product-planning",
    "worker-architecture",
    "worker-developer",
    "worker-review",
    "worker-tester",
    "worker-release-manager",
    "worker-scheduler",
    "worker-frontend",
    "worker-ui-ux",
    "worker-security",
    "worker-docs-confluence",
    "worker-devops-platform",
    "worker-data-persistence",
)


@dataclass(frozen=True)
class ContainerImageReference:
    """Resolved image reference for one platform component."""

    component: str
    repository: str
    tag: str

    @property
    def reference(self) -> str:
        return f"{self.repository}:{self.tag}"


def build_container_image_references(settings: ImageRegistrySettings) -> tuple[ContainerImageReference, ...]:
    """Build deterministic OCI image references for every platform image family."""

    return tuple(
        ContainerImageReference(
            component=component,
            repository=_repository_for_component(settings, component),
            tag=settings.image_tag,
        )
        for component in IMAGE_COMPONENTS
    )


def validate_image_registry_publish_settings(settings: ImageRegistrySettings) -> tuple[str, ...]:
    """Return redacted publish-mode validation issues."""

    issues: list[str] = []
    if not settings.namespace.strip():
        issues.append("AGENTIC_IMAGE_NAMESPACE is required for image naming.")
    if not settings.image_tag.strip():
        issues.append("AGENTIC_IMAGE_TAG is required for image naming.")
    if settings.push_enabled:
        if not settings.host.strip():
            issues.append("AGENTIC_IMAGE_REGISTRY_HOST is required when image push is enabled.")
        has_inline_credentials = bool(settings.username.strip() and settings.token.strip())
        has_credential_ref = bool(settings.credential_ref.strip())
        if not has_inline_credentials and not has_credential_ref:
            issues.append(
                "AGENTIC_IMAGE_REGISTRY_CREDENTIAL_REF or username/token credentials are required "
                "when image push is enabled."
            )
    return tuple(issues)


def _repository_for_component(settings: ImageRegistrySettings, component: str) -> str:
    prefix_parts = [part.strip("/") for part in (settings.host, settings.namespace) if part.strip("/")]
    prefix = "/".join(prefix_parts)
    return f"{prefix}/{component}" if prefix else component
