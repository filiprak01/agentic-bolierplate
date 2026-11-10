from datetime import datetime, timezone

import pytest

from agentic_boilerplate.domain import (
    SprintPublicationArtifact,
    SprintPublicationArtifactType,
    SprintPublicationChangeAction,
    SprintPublicationTaskAction,
    SprintPublicationFileChange,
    SprintPublicationWorkflowError,
    SprintRetroSetupTask,
    StoryBackedChangeSurface,
    build_sprint_publication_plan,
    render_sprint_publication_jira_comment,
    render_sprint_publication_plan,
    render_sprint_retro_setup_validation,
    validate_sprint_retro_setup,
)
from agentic_boilerplate.storage import write_sprint_publication_plan


def test_publication_plan_detects_existing_task_and_supports_sprint_artifacts() -> None:
    plan = build_sprint_publication_plan(
        sprint_name="Sprint 11",
        publication_issue_key="AGENT-245",
        artifacts=(
            SprintPublicationArtifact(
                path="docs/sprints/sprint-11-retro.md",
                artifact_type=SprintPublicationArtifactType.RETRO,
                jira_issue_keys=("AGENT-245",),
            ),
            SprintPublicationArtifact(
                path="docs/sprints/sprint-11-post-mortem.md",
                artifact_type=SprintPublicationArtifactType.POST_MORTEM,
            ),
            SprintPublicationArtifact(
                path="docs/sprints/sprint-11-closure.md",
                artifact_type=SprintPublicationArtifactType.CLOSURE,
            ),
            SprintPublicationArtifact(
                path="docs/sprints/sprint-performance-tracking.md",
                artifact_type=SprintPublicationArtifactType.SPRINT_PERFORMANCE,
            ),
            SprintPublicationArtifact(
                path="docs/sprints/sprint-11-process-note.md",
                artifact_type=SprintPublicationArtifactType.PROCESS_NOTE,
            ),
        ),
        changed_files=(
            SprintPublicationFileChange(
                path="docs/sprints/sprint-11-retro.md",
                change_surface=StoryBackedChangeSurface.PROCESS_DOCUMENTATION,
            ),
        ),
    )

    assert plan.task_action is SprintPublicationTaskAction.DETECT_EXISTING
    assert plan.branch_name == "process/AGENT-245-retro-publication"
    assert plan.next_sprint_blocked is False
    assert [artifact.artifact_type for artifact in plan.artifacts] == [
        SprintPublicationArtifactType.RETRO,
        SprintPublicationArtifactType.POST_MORTEM,
        SprintPublicationArtifactType.CLOSURE,
        SprintPublicationArtifactType.SPRINT_PERFORMANCE,
        SprintPublicationArtifactType.PROCESS_NOTE,
    ]
    assert plan.file_decisions[0].action is SprintPublicationChangeAction.PUBLISH_UNDER_TASK
    assert "markdown paths" in plan.file_decisions[0].validation_steps[0].lower()


def test_missing_publication_task_blocks_next_sprint_until_task_exists() -> None:
    plan = build_sprint_publication_plan(
        sprint_name="Sprint 11",
        artifacts=(
            SprintPublicationArtifact(
                path="docs/sprints/sprint-11-retro.md",
                artifact_type=SprintPublicationArtifactType.RETRO,
            ),
        ),
    )

    assert plan.task_action is SprintPublicationTaskAction.CREATE
    assert plan.branch_name == "docs/sprint-11-retro-publication"
    assert plan.next_sprint_blocked is True
    assert "Sprint publication Task must be created" in plan.blocked_reasons[0]


def test_retro_setup_validation_requires_intake_task_and_template_before_delivery() -> None:
    missing = validate_sprint_retro_setup(
        sprint_name="AP R1 S4",
        support_tasks=(),
        retro_template_path="",
    )
    ready = validate_sprint_retro_setup(
        sprint_name="AP R1 S4",
        support_tasks=(
            SprintRetroSetupTask(
                issue_key="AP-127",
                summary="Retro Intake and Improvement Routing",
                status="READY TO START",
                labels=("retro-intake", "support-task"),
            ),
        ),
        retro_template_path="docs/sprints/ap-r1-s4-retro-template.md",
    )
    rendered = render_sprint_retro_setup_validation(ready)

    assert missing.ready is False
    assert any("Retro intake template path is required" in issue for issue in missing.issues)
    assert any("Board-visible retro intake support task is required" in issue for issue in missing.issues)
    assert ready.ready is True
    assert ready.retro_intake_task is not None
    assert ready.retro_intake_task.issue_key == "AP-127"
    assert "Retro setup ready: yes" in rendered


def test_boilerplate_code_change_without_story_blocks_publication_branch_creation() -> None:
    plan = build_sprint_publication_plan(
        sprint_name="Sprint 11",
        publication_issue_key="AGENT-245",
        artifacts=(
            SprintPublicationArtifact(
                path="docs/sprints/sprint-11-retro.md",
                artifact_type=SprintPublicationArtifactType.RETRO,
            ),
        ),
        changed_files=(
            SprintPublicationFileChange(
                path="src/agentic_boilerplate/domain/new_behavior.py",
                change_surface=StoryBackedChangeSurface.CODE_CHANGE,
            ),
        ),
    )

    assert plan.next_sprint_blocked is True
    assert plan.file_decisions[0].action is SprintPublicationChangeAction.BLOCKED
    assert "missing a required Jira story" in plan.blocked_reasons[0]


def test_boilerplate_code_change_with_story_routes_outside_publication_task() -> None:
    plan = build_sprint_publication_plan(
        sprint_name="Sprint 11",
        publication_issue_key="AGENT-245",
        artifacts=(
            SprintPublicationArtifact(
                path="docs/sprints/sprint-11-retro.md",
                artifact_type=SprintPublicationArtifactType.RETRO,
            ),
        ),
        changed_files=(
            SprintPublicationFileChange(
                path="src/agentic_boilerplate/domain/new_behavior.py",
                change_surface=StoryBackedChangeSurface.CODE_CHANGE,
                jira_issue_key="AGENT-300",
            ),
        ),
        follow_up_story_keys=("AGENT-300",),
    )

    assert plan.next_sprint_blocked is False
    assert plan.file_decisions[0].action is SprintPublicationChangeAction.REQUIRES_STORY
    assert plan.file_decisions[0].jira_issue_key == "AGENT-300"
    assert plan.follow_up_story_keys == ("AGENT-300",)


def test_process_doc_change_must_be_included_as_artifact_or_parked_by_po() -> None:
    missing_artifact = build_sprint_publication_plan(
        sprint_name="Sprint 11",
        publication_issue_key="AGENT-245",
        artifacts=(
            SprintPublicationArtifact(
                path="docs/sprints/sprint-11-retro.md",
                artifact_type=SprintPublicationArtifactType.RETRO,
            ),
        ),
        changed_files=(
            SprintPublicationFileChange(
                path="docs/sprints/sprint-11-process-note.md",
                change_surface=StoryBackedChangeSurface.PROCESS_DOCUMENTATION,
            ),
        ),
    )
    parked = build_sprint_publication_plan(
        sprint_name="Sprint 11",
        publication_issue_key="AGENT-245",
        artifacts=(
            SprintPublicationArtifact(
                path="docs/sprints/sprint-11-retro.md",
                artifact_type=SprintPublicationArtifactType.RETRO,
            ),
        ),
        changed_files=(
            SprintPublicationFileChange(
                path="docs/sprints/sprint-11-process-note.md",
                change_surface=StoryBackedChangeSurface.PROCESS_DOCUMENTATION,
                parked_by_po=True,
            ),
        ),
    )

    assert missing_artifact.next_sprint_blocked is True
    assert "must be included as a publication artifact" in missing_artifact.blocked_reasons[0]
    assert parked.next_sprint_blocked is False
    assert parked.file_decisions[0].action is SprintPublicationChangeAction.PARK_LOCAL_NOTE


def test_rendered_plan_and_jira_comment_include_pr_evidence_and_followups() -> None:
    plan = build_sprint_publication_plan(
        sprint_name="Sprint 11",
        publication_issue_key="AGENT-245",
        artifacts=(
            SprintPublicationArtifact(
                path="docs/sprints/sprint-11-retro.md",
                artifact_type=SprintPublicationArtifactType.RETRO,
            ),
        ),
        follow_up_story_keys=("AGENT-300",),
        pull_request_urls=("https://github.com/example-org/agentic-boilerplate/pull/170",),
        evidence_paths=("data/agent-logs/AGENT-170/test-evidence.md",),
    )

    rendered = render_sprint_publication_plan(plan)
    comment = render_sprint_publication_jira_comment(plan)

    assert "Follow-up stories:" in rendered
    assert "Pull requests:" in rendered
    assert "Evidence paths:" in rendered
    assert "AGENT-300" in comment
    assert "pull/170" in comment
    assert "test-evidence.md" in comment


def test_storage_writes_timestamped_publication_plan(tmp_path) -> None:
    plan = build_sprint_publication_plan(
        sprint_name="Sprint 11",
        publication_issue_key="AGENT-245",
        artifacts=(
            SprintPublicationArtifact(
                path="docs/sprints/sprint-11-retro.md",
                artifact_type=SprintPublicationArtifactType.RETRO,
            ),
        ),
    )

    path = write_sprint_publication_plan(
        plan,
        tmp_path,
        created_at=datetime(2026, 7, 6, 10, 30, tzinfo=timezone.utc),
    )

    assert path.name == "sprint-publication-plan-sprint-11-20260706T103000Z.md"
    assert "Sprint: Sprint 11" in path.read_text(encoding="utf-8")
    assert "Publication task: AGENT-245" in path.read_text(encoding="utf-8")


def test_missing_required_inputs_fail_validation() -> None:
    with pytest.raises(SprintPublicationWorkflowError) as exc_info:
        build_sprint_publication_plan(sprint_name="", artifacts=())

    assert "sprint_name" in str(exc_info.value)
    assert "artifacts" in str(exc_info.value)
