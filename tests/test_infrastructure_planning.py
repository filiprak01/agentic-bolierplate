from pathlib import Path

from agentic_boilerplate.domain import (
    DeploymentProfile,
    InfrastructurePlanningInput,
    build_infrastructure_intake_questions,
    build_infrastructure_profile_recommendation,
    infrastructure_profile_recommendation_to_dict,
    render_infrastructure_profile_markdown,
)


def test_infrastructure_intake_questions_cover_scale_data_availability_budget_target_and_growth() -> None:
    questions = build_infrastructure_intake_questions(
        {
            "expected_scale": "",
            "data_sensitivity": "",
            "availability_needs": "",
            "budget": "",
            "deployment_target": "",
            "growth_path": "",
        }
    )

    fields = {question.field for question in questions}

    assert fields == {
        "expected_scale",
        "data_sensitivity",
        "availability_needs",
        "budget",
        "deployment_target",
        "growth_path",
    }
    assert any("monthly infrastructure budget" in question.question for question in questions)


def test_profile_recommendation_starts_small_and_adds_upgrade_path_for_public_vps_project() -> None:
    recommendation = build_infrastructure_profile_recommendation(
        InfrastructurePlanningInput(
            project_name="Airline planning app",
            expected_scale="Small public MVP with growth to multiple projects.",
            data_sensitivity="Business-sensitive booking data.",
            availability_needs="High availability eventually, basic uptime for MVP.",
            budget="Start under a small monthly budget.",
            deployment_target=DeploymentProfile.VPS,
            growth_path="Move to managed containers when traffic increases.",
            requires_public_access=True,
            requires_managed_database=True,
            requires_object_storage=True,
            requires_backup=True,
            requires_monitoring=True,
        )
    )

    assert recommendation.starting_profiles == (
        DeploymentProfile.VPS,
        DeploymentProfile.MANAGED_DATABASE,
        DeploymentProfile.OBJECT_STORAGE,
        DeploymentProfile.MONITORING,
        DeploymentProfile.BACKUP,
    )
    assert DeploymentProfile.MANAGED_CONTAINER_SERVICE in recommendation.upgrade_path
    assert DeploymentProfile.FUTURE_KUBERNETES in recommendation.upgrade_path
    assert not recommendation.live_provisioning_in_scope
    assert len(recommendation.roadmap_stories) == 3
    assert "defer live provisioning automation" in recommendation.recommendation_summary


def test_local_docker_only_project_does_not_generate_deployment_prep_stories() -> None:
    recommendation = build_infrastructure_profile_recommendation(
        InfrastructurePlanningInput(
            project_name="Local demo",
            expected_scale="One local user.",
            data_sensitivity="No sensitive data.",
            availability_needs="Best effort local usage.",
            budget="No paid infrastructure.",
            deployment_target=DeploymentProfile.LOCAL_DOCKER,
            growth_path="Revisit if public deployment is needed.",
            requires_public_access=False,
        )
    )

    assert recommendation.starting_profiles == (DeploymentProfile.LOCAL_DOCKER,)
    assert recommendation.roadmap_stories == ()
    markdown = render_infrastructure_profile_markdown(recommendation)
    assert "Live provisioning in scope: `false`" in markdown
    assert "No infrastructure preparation stories needed beyond local Docker" in markdown


def test_recommendation_payload_is_machine_readable_for_context_packs() -> None:
    recommendation = build_infrastructure_profile_recommendation(
        InfrastructurePlanningInput(
            project_name="Managed app",
            expected_scale="Public service.",
            data_sensitivity="Private data.",
            availability_needs="Critical recovery needs.",
            budget="Managed services allowed.",
            deployment_target=DeploymentProfile.MANAGED_CONTAINER_SERVICE,
            growth_path="Add Kubernetes only after multiple services.",
            requires_managed_database=True,
        )
    )

    payload = infrastructure_profile_recommendation_to_dict(recommendation)

    assert payload["project_name"] == "Managed app"
    assert "managed_container_service" in payload["starting_profiles"]
    assert payload["live_provisioning_in_scope"] is False
    assert payload["roadmap_stories"]


def test_infrastructure_planning_docs_cover_required_profiles_and_boundaries(project_root: Path) -> None:
    docs = (project_root / "docs" / "infrastructure-planning-template.md").read_text(encoding="utf-8")
    getting_started = (project_root / "docs" / "getting-started.md").read_text(encoding="utf-8")
    architecture_role = (project_root / "ai_agents" / "roles" / "architecture.md").read_text(encoding="utf-8")
    devops_role = (project_root / "ai_agents" / "roles" / "devops_platform.md").read_text(encoding="utf-8")

    for phrase in (
        "Expected scale",
        "Data sensitivity",
        "Availability needs",
        "Budget",
        "Deployment target",
        "Growth path",
        "`local_docker`",
        "`vps`",
        "`managed_container_service`",
        "`managed_database`",
        "`object_storage`",
        "`monitoring`",
        "`backup`",
        "`future_kubernetes`",
        "live cloud provisioning",
        "Roadmap story candidates",
    ):
        assert phrase in docs
    assert "does not create real cloud resources" in getting_started
    assert "docs/infrastructure-planning-template.md" in architecture_role
    assert "docs/infrastructure-planning-template.md" in devops_role
