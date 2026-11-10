from datetime import datetime, timezone
from pathlib import Path

import pytest

from agentic_boilerplate.domain import (
    SprintClosureChangeAction,
    SprintClosureFileChange,
    SprintClosurePublicationError,
    StoryBackedChangeSurface,
    build_sprint_closure_publication_plan,
    render_sprint_closure_publication_jira_comment,
    render_sprint_closure_publication_plan,
)
from agentic_boilerplate.storage import write_sprint_closure_publication_plan


WORKFLOW_DOC = Path("docs/sprint-closure-publication-workflow.md")


def test_closure_publication_plan_captures_notes_fit_and_follow_up_stories() -> None:
    plan = build_sprint_closure_publication_plan(
        sprint_name="Sprint 11",
        publication_issue_key="AGENT-245",
        retro_note_path="docs/sprints/sprint-11-retro.md",
        closure_note_path="docs/sprints/sprint-11-closure.md",
        sprint_performance_path="docs/sprints/sprint-performance-tracking.md",
        regression_result_summary="Regression passed on merged main.",
        po_acceptance_summary="PO accepted the Sprint 11 scope as a batch.",
        sprint_fit_summary="Sprint 11 fit within the configured Codex window.",
        follow_up_story_keys=("AGENT-300", "AGENT-301"),
        changed_files=(
            SprintClosureFileChange(
                path="docs/sprints/sprint-11-closure.md",
                change_surface=StoryBackedChangeSurface.PROCESS_DOCUMENTATION,
            ),
        ),
    )

    assert plan.branch_name == "process/AGENT-245-closure-publication"
    assert plan.ready_for_publication is True
    assert plan.follow_up_story_keys == ("AGENT-300", "AGENT-301")
    assert plan.file_decisions[0].action is SprintClosureChangeAction.PUBLISH_UNDER_TASK
    assert "Sprint 11" in render_sprint_closure_publication_plan(plan)
    assert "AGENT-300" in render_sprint_closure_publication_jira_comment(plan)


def test_closure_publication_workflow_requires_workspace_readiness_when_parallel_workspaces_are_used() -> None:
    text = WORKFLOW_DOC.read_text(encoding="utf-8")

    assert "Workspace closure readiness report path" in text
    assert "can_close=true" in text
    assert "stale/dirty/" in text
    assert "workspace closure readiness report" in text


def test_closure_publication_plan_warns_when_core_summaries_are_missing() -> None:
    plan = build_sprint_closure_publication_plan(
        sprint_name="Sprint 11",
        publication_issue_key="AGENT-245",
        retro_note_path="docs/sprints/sprint-11-retro.md",
        closure_note_path="docs/sprints/sprint-11-closure.md",
        sprint_performance_path="docs/sprints/sprint-performance-tracking.md",
        regression_result_summary="",
        po_acceptance_summary="",
        sprint_fit_summary="",
    )

    assert {warning.warning_type for warning in plan.warnings} == {
        "missing-regression-result",
        "missing-po-acceptance",
        "missing-sprint-fit",
    }
    assert plan.ready_for_publication is False


def test_closure_publication_blocks_code_changes_without_story() -> None:
    plan = build_sprint_closure_publication_plan(
        sprint_name="Sprint 11",
        publication_issue_key="AGENT-245",
        retro_note_path="docs/sprints/sprint-11-retro.md",
        closure_note_path="docs/sprints/sprint-11-closure.md",
        sprint_performance_path="docs/sprints/sprint-performance-tracking.md",
        regression_result_summary="Regression passed on merged main.",
        po_acceptance_summary="PO accepted the Sprint 11 scope as a batch.",
        sprint_fit_summary="Sprint 11 fit within the configured Codex window.",
        changed_files=(
            SprintClosureFileChange(
                path="src/agentic_boilerplate/domain/new_behavior.py",
                change_surface=StoryBackedChangeSurface.CODE_CHANGE,
            ),
        ),
    )

    assert plan.file_decisions[0].action is SprintClosureChangeAction.BLOCKED
    assert plan.ready_for_publication is False


def test_closure_publication_storage_writes_timestamped_markdown(tmp_path) -> None:
    plan = build_sprint_closure_publication_plan(
        sprint_name="Sprint 11",
        publication_issue_key="AGENT-245",
        retro_note_path="docs/sprints/sprint-11-retro.md",
        closure_note_path="docs/sprints/sprint-11-closure.md",
        sprint_performance_path="docs/sprints/sprint-performance-tracking.md",
        regression_result_summary="Regression passed on merged main.",
        po_acceptance_summary="PO accepted the Sprint 11 scope as a batch.",
        sprint_fit_summary="Sprint 11 fit within the configured Codex window.",
    )

    path = write_sprint_closure_publication_plan(
        plan,
        tmp_path,
        created_at=datetime(2026, 7, 6, tzinfo=timezone.utc),
    )

    assert path.name == "sprint-closure-publication-sprint-11-20260706T000000Z.md"
    assert "Publication task: AGENT-245" in path.read_text(encoding="utf-8")


def test_closure_publication_requires_core_text_inputs() -> None:
    with pytest.raises(SprintClosurePublicationError) as exc_info:
        build_sprint_closure_publication_plan(
            sprint_name="",
            publication_issue_key="AGENT-245",
            retro_note_path="docs/sprints/sprint-11-retro.md",
            closure_note_path="docs/sprints/sprint-11-closure.md",
            sprint_performance_path="docs/sprints/sprint-performance-tracking.md",
            regression_result_summary="Regression passed on merged main.",
            po_acceptance_summary="PO accepted the Sprint 11 scope as a batch.",
            sprint_fit_summary="Sprint 11 fit within the configured Codex window.",
        )

    assert "sprint_name" in str(exc_info.value)
