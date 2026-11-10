import pytest

from agentic_boilerplate.domain import (
    RetroFinding,
    RetroFindingStatus,
    RetroRoutingTarget,
    RetroToRoadmapError,
    build_retro_follow_up_story_draft,
    build_retro_to_roadmap_plan,
    render_retro_to_roadmap_summary,
    route_retro_finding,
)


def test_accepted_findings_route_to_existing_story_new_story_or_docs_update() -> None:
    existing = route_retro_finding(
        RetroFinding(
            id="finding-1",
            title="Map to existing story",
            summary="Carry through existing implementation backlog.",
            status=RetroFindingStatus.ACCEPTED,
            existing_issue_key="AGENT-201",
        )
    )
    docs = route_retro_finding(
        RetroFinding(
            id="finding-2",
            title="Docs only",
            summary="Update retro publication notes.",
            status=RetroFindingStatus.ACCEPTED,
            documentation_update_path="docs/sprints/sprint-11-retro.md",
        )
    )
    backlog = route_retro_finding(
        RetroFinding(
            id="finding-3",
            title="New story",
            summary="Create backlog story for workflow automation.",
            status=RetroFindingStatus.ACCEPTED,
            proposed_story_title="Implement retro automation follow-up",
        )
    )

    assert existing.target is RetroRoutingTarget.EXISTING_STORY
    assert docs.target is RetroRoutingTarget.DOCUMENTATION_UPDATE
    assert backlog.target is RetroRoutingTarget.NEW_BACKLOG_STORY


def test_deferred_and_rejected_findings_route_without_scope_change() -> None:
    deferred = route_retro_finding(
        RetroFinding(
            id="finding-4",
            title="Later release",
            summary="Useful but not MVP.",
            status=RetroFindingStatus.DEFERRED,
            roadmap_bucket="later-release",
        )
    )
    rejected = route_retro_finding(
        RetroFinding(
            id="finding-5",
            title="Rejected idea",
            summary="Intentionally not changing.",
            status=RetroFindingStatus.REJECTED,
        )
    )

    assert deferred.target is RetroRoutingTarget.DEFERRED_ROADMAP
    assert rejected.target is RetroRoutingTarget.REJECTED


def test_retro_follow_up_story_draft_stays_in_funnel_with_po_review_label() -> None:
    decision = route_retro_finding(
        RetroFinding(
            id="finding-8",
            title="Automate process follow-up",
            summary="Create a backlog story after retro.",
            status=RetroFindingStatus.ACCEPTED,
            proposed_story_title="Automate retro follow-up visibility",
        )
    )

    draft = build_retro_follow_up_story_draft(
        decision,
        recommended_sprint_label="r11-sprint-03",
    )

    assert draft.summary == "Automate retro follow-up visibility"
    assert draft.initial_status == "FUNNEL"
    assert "po-review-required" in draft.labels
    assert "r11-sprint-03" in draft.labels


def test_plan_flags_uncommitted_files_that_must_be_pushed_or_parked() -> None:
    plan = build_retro_to_roadmap_plan(
        publication_issue_key="AGENT-245",
        sprint_name="Sprint 11",
        findings=(
            RetroFinding(
                id="finding-6",
                title="Accepted docs update",
                summary="Update current sprint retro doc.",
                status=RetroFindingStatus.ACCEPTED,
                documentation_update_path="docs/sprints/sprint-11-retro.md",
            ),
        ),
        changed_local_files=("docs/sprints/sprint-11-retro.md", "notes/local-scratch.md"),
        parked_local_notes=("notes/local-scratch.md",),
    )

    assert plan.blocked_uncommitted_files == ("docs/sprints/sprint-11-retro.md",)
    assert plan.cleanup_decisions[0].action == "push"
    assert plan.cleanup_decisions[1].action == "park"
    assert "docs/sprints/sprint-11-retro.md: push" in render_retro_to_roadmap_summary(plan)


def test_accepted_finding_without_route_fails_validation() -> None:
    with pytest.raises(RetroToRoadmapError):
        route_retro_finding(
            RetroFinding(
                id="finding-7",
                title="Missing route",
                summary="Accepted but not mapped anywhere.",
                status=RetroFindingStatus.ACCEPTED,
            )
        )
