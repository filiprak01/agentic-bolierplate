"""Infrastructure planning templates and deployment profile recommendations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class InfrastructurePlanningError(ValueError):
    """Raised when infrastructure planning input is invalid."""


class DeploymentProfile(str, Enum):
    LOCAL_DOCKER = "local_docker"
    VPS = "vps"
    MANAGED_CONTAINER_SERVICE = "managed_container_service"
    MANAGED_DATABASE = "managed_database"
    OBJECT_STORAGE = "object_storage"
    MONITORING = "monitoring"
    BACKUP = "backup"
    FUTURE_KUBERNETES = "future_kubernetes"


@dataclass(frozen=True)
class InfrastructurePlanningInput:
    project_name: str
    expected_scale: str
    data_sensitivity: str
    availability_needs: str
    budget: str
    deployment_target: DeploymentProfile
    growth_path: str
    requires_public_access: bool = False
    requires_managed_database: bool = False
    requires_object_storage: bool = False
    requires_backup: bool = False
    requires_monitoring: bool = False


@dataclass(frozen=True)
class InfrastructureIntakeQuestion:
    field: str
    question: str
    why_it_matters: str


@dataclass(frozen=True)
class InfrastructureRoadmapStory:
    title: str
    rationale: str
    recommended_role: str


@dataclass(frozen=True)
class InfrastructureProfileRecommendation:
    project_name: str
    starting_profiles: tuple[DeploymentProfile, ...]
    upgrade_path: tuple[DeploymentProfile, ...]
    roadmap_stories: tuple[InfrastructureRoadmapStory, ...]
    live_provisioning_in_scope: bool
    recommendation_summary: str


REQUIRED_INTAKE_FIELDS: tuple[InfrastructureIntakeQuestion, ...] = (
    InfrastructureIntakeQuestion(
        "expected_scale",
        "What user, traffic, data volume, and concurrency scale should the first release support?",
        "Scale determines whether local Docker, one VPS, or managed services are a reasonable starting point.",
    ),
    InfrastructureIntakeQuestion(
        "data_sensitivity",
        "What data sensitivity, privacy, compliance, and retention constraints apply?",
        "Sensitive data changes database, backup, network, and access-control recommendations.",
    ),
    InfrastructureIntakeQuestion(
        "availability_needs",
        "What uptime, recovery time, and maintenance-window expectations apply?",
        "Availability needs determine backup, monitoring, and failover requirements.",
    ),
    InfrastructureIntakeQuestion(
        "budget",
        "What monthly infrastructure budget or cost ceiling should the architecture optimize for?",
        "Budget prevents agents from over-designing expensive infrastructure too early.",
    ),
    InfrastructureIntakeQuestion(
        "deployment_target",
        "What deployment target should be planned first: local Docker, VPS, managed container service, or future Kubernetes?",
        "The target sets the initial deployment profile and roadmap split.",
    ),
    InfrastructureIntakeQuestion(
        "growth_path",
        "What growth path should the project expect when usage increases?",
        "Growth path captures when to move from the smallest reasonable footprint to managed or orchestrated services.",
    ),
)


def build_infrastructure_intake_questions(values: dict[str, object]) -> tuple[InfrastructureIntakeQuestion, ...]:
    """Return PO/Architecture questions for missing infrastructure intake fields."""

    missing: list[InfrastructureIntakeQuestion] = []
    for question in REQUIRED_INTAKE_FIELDS:
        value = values.get(question.field)
        if value is None or not str(value).strip():
            missing.append(question)
    return tuple(missing)


def build_infrastructure_profile_recommendation(
    plan_input: InfrastructurePlanningInput,
) -> InfrastructureProfileRecommendation:
    """Recommend a smallest reasonable footprint plus future upgrade path."""

    _require_text("project_name", plan_input.project_name)
    _require_text("expected_scale", plan_input.expected_scale)
    _require_text("data_sensitivity", plan_input.data_sensitivity)
    _require_text("availability_needs", plan_input.availability_needs)
    _require_text("budget", plan_input.budget)
    _require_text("growth_path", plan_input.growth_path)

    starting = _starting_profiles(plan_input)
    upgrade = _upgrade_path(plan_input, starting)
    stories = _roadmap_stories(plan_input)
    summary = (
        f"Start {plan_input.project_name} on {', '.join(profile.value for profile in starting)} "
        f"and defer live provisioning automation. Upgrade through "
        f"{', '.join(profile.value for profile in upgrade) or 'no additional profile'} as scale grows."
    )
    return InfrastructureProfileRecommendation(
        project_name=plan_input.project_name.strip(),
        starting_profiles=starting,
        upgrade_path=upgrade,
        roadmap_stories=stories,
        live_provisioning_in_scope=False,
        recommendation_summary=summary,
    )


def render_infrastructure_profile_markdown(recommendation: InfrastructureProfileRecommendation) -> str:
    """Render the recommendation for architecture docs or Jira context packs."""

    lines = [
        f"# Infrastructure Profile - {recommendation.project_name}",
        "",
        "## Starting Footprint",
        "",
        *[f"- `{profile.value}`" for profile in recommendation.starting_profiles],
        "",
        "## Upgrade Path",
        "",
    ]
    if recommendation.upgrade_path:
        lines.extend(f"- `{profile.value}`" for profile in recommendation.upgrade_path)
    else:
        lines.append("- No upgrade profile required for the current scope.")
    lines.extend(
        [
            "",
            "## Provisioning Boundary",
            "",
            f"Live provisioning in scope: `{str(recommendation.live_provisioning_in_scope).lower()}`",
            "",
            "The architecture recommendation is planning support only. Real cloud provisioning, paid service creation, DNS changes, and production credentials require separate Product Owner-approved stories.",
            "",
            "## Roadmap Story Candidates",
            "",
        ]
    )
    if recommendation.roadmap_stories:
        for story in recommendation.roadmap_stories:
            lines.append(f"- {story.title} ({story.recommended_role}): {story.rationale}")
    else:
        lines.append("- No infrastructure preparation stories needed beyond local Docker for this scope.")
    lines.extend(["", "## Summary", "", recommendation.recommendation_summary])
    return "\n".join(lines) + "\n"


def infrastructure_profile_recommendation_to_dict(
    recommendation: InfrastructureProfileRecommendation,
) -> dict[str, object]:
    return {
        "project_name": recommendation.project_name,
        "starting_profiles": [profile.value for profile in recommendation.starting_profiles],
        "upgrade_path": [profile.value for profile in recommendation.upgrade_path],
        "live_provisioning_in_scope": recommendation.live_provisioning_in_scope,
        "recommendation_summary": recommendation.recommendation_summary,
        "roadmap_stories": [
            {
                "title": story.title,
                "rationale": story.rationale,
                "recommended_role": story.recommended_role,
            }
            for story in recommendation.roadmap_stories
        ],
    }


def _starting_profiles(plan_input: InfrastructurePlanningInput) -> tuple[DeploymentProfile, ...]:
    profiles: list[DeploymentProfile] = [plan_input.deployment_target]
    if plan_input.requires_managed_database:
        profiles.append(DeploymentProfile.MANAGED_DATABASE)
    if plan_input.requires_object_storage:
        profiles.append(DeploymentProfile.OBJECT_STORAGE)
    if plan_input.requires_monitoring:
        profiles.append(DeploymentProfile.MONITORING)
    if plan_input.requires_backup:
        profiles.append(DeploymentProfile.BACKUP)
    return _dedupe_profiles(tuple(profiles))


def _upgrade_path(
    plan_input: InfrastructurePlanningInput,
    starting: tuple[DeploymentProfile, ...],
) -> tuple[DeploymentProfile, ...]:
    upgrade: list[DeploymentProfile] = []
    if plan_input.deployment_target is DeploymentProfile.LOCAL_DOCKER and plan_input.requires_public_access:
        upgrade.append(DeploymentProfile.VPS)
    if plan_input.deployment_target in {DeploymentProfile.LOCAL_DOCKER, DeploymentProfile.VPS}:
        upgrade.append(DeploymentProfile.MANAGED_CONTAINER_SERVICE)
    if DeploymentProfile.MANAGED_DATABASE not in starting:
        upgrade.append(DeploymentProfile.MANAGED_DATABASE)
    if DeploymentProfile.MONITORING not in starting:
        upgrade.append(DeploymentProfile.MONITORING)
    if DeploymentProfile.BACKUP not in starting and _sensitive_or_available(plan_input):
        upgrade.append(DeploymentProfile.BACKUP)
    upgrade.append(DeploymentProfile.FUTURE_KUBERNETES)
    return tuple(profile for profile in _dedupe_profiles(tuple(upgrade)) if profile not in starting)


def _roadmap_stories(plan_input: InfrastructurePlanningInput) -> tuple[InfrastructureRoadmapStory, ...]:
    if plan_input.deployment_target is DeploymentProfile.LOCAL_DOCKER and not plan_input.requires_public_access:
        return ()
    stories = [
        InfrastructureRoadmapStory(
            title="Prepare deployment profile for selected infrastructure target",
            rationale="Project requires deployment planning beyond local Docker.",
            recommended_role="Architecture / DevOps Platform",
        )
    ]
    if plan_input.requires_managed_database:
        stories.append(
            InfrastructureRoadmapStory(
                title="Define managed database migration and backup plan",
                rationale="Managed database is part of the recommended footprint.",
                recommended_role="Architecture / Data Persistence",
            )
        )
    if plan_input.requires_object_storage:
        stories.append(
            InfrastructureRoadmapStory(
                title="Define object storage access and retention plan",
                rationale="Object storage is part of the recommended footprint.",
                recommended_role="Architecture / Security",
            )
        )
    return tuple(stories)


def _sensitive_or_available(plan_input: InfrastructurePlanningInput) -> bool:
    text = f"{plan_input.data_sensitivity} {plan_input.availability_needs}".lower()
    return any(marker in text for marker in ("sensitive", "personal", "private", "high", "critical", "backup"))


def _dedupe_profiles(profiles: tuple[DeploymentProfile, ...]) -> tuple[DeploymentProfile, ...]:
    deduped: list[DeploymentProfile] = []
    for profile in profiles:
        if profile not in deduped:
            deduped.append(profile)
    return tuple(deduped)


def _require_text(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InfrastructurePlanningError(f"{name} is required")
    return value.strip()
