import pytest

from agentic_boilerplate.domain.active_sprint_retro import (
    ActiveSprintRetroComment,
    ActiveSprintRetroError,
    build_active_sprint_retro_intake_plan,
    build_retro_comment_po_approval_item,
    render_active_sprint_retro_comment_template,
    render_active_sprint_retro_intake_plan,
    require_valid_active_sprint_retro_comment,
)
from agentic_boilerplate.domain.po_inbox import InboxMessageType, InboxStatus


def test_active_sprint_retro_plan_defines_creation_timing_template_and_po_rule() -> None:
    plan = build_active_sprint_retro_intake_plan(
        sprint_name="AP R1 S3 Process Tooling",
        retro_issue_key="AP-84",
        delivery_issue_keys=("AP-30", "AP-35"),
        participant_roles=("release_manager", "review"),
    )

    rendered = render_active_sprint_retro_intake_plan(plan)

    assert "before the first delivery item starts" in plan.creation_timing
    assert "For each submitted retro comment" in plan.po_approval_rule
    assert "### Airlines Project Element" in plan.comment_template
    assert "### Agent/Process Element" in plan.comment_template
    assert "`AP-30`" in rendered
    assert "`release_manager`" in rendered


def test_retro_comment_template_requires_two_problem_and_suggestion_sections() -> None:
    template = render_active_sprint_retro_comment_template("tester")

    assert "## Retro Input - tester" in template
    assert template.count("Problematic elements:") == 2
    assert template.count("Suggestions:") == 2
    assert "### Airlines Project Element" in template
    assert "### Agent/Process Element" in template


def test_retro_comment_po_approval_item_is_schema_valid_and_linked_to_retro_issue() -> None:
    comment = ActiveSprintRetroComment(
        retro_issue_key="AP-84",
        participant_role="release_manager",
        participant_name="Release Manager Agent",
        airlines_project_problematic_elements=("Release notes were assembled late.",),
        airlines_project_suggestions=("Create the retro task during sprint setup.",),
        agent_process_problematic_elements=("Agents did not know where to submit retro input.",),
        agent_process_suggestions=("Require PO inbox approval for each retro comment.",),
        submitted_comment_id="10001",
    )

    item = build_retro_comment_po_approval_item(
        comment,
        item_id="retro-ap84-comment-10001-po-approval",
        created_at="2026-07-19T01:20:00Z",
        agent_id="release-manager-test",
    )

    assert item.message_type is InboxMessageType.APPROVAL_REQUEST
    assert item.status is InboxStatus.OPEN
    assert item.jira_issue_key == "AP-84"
    assert "Airlines Project Element" in item.message
    assert "Agent/Process Element" in item.message
    assert "Approve only when both" in item.recommendation


def test_retro_comment_validation_fails_when_a_required_section_is_missing() -> None:
    comment = ActiveSprintRetroComment(
        retro_issue_key="AP-84",
        participant_role="tester",
        participant_name="Tester Agent",
        airlines_project_problematic_elements=("Regression scope was unclear.",),
        airlines_project_suggestions=("Publish the scope earlier.",),
        agent_process_problematic_elements=(),
        agent_process_suggestions=("Add a template.",),
    )

    with pytest.raises(ActiveSprintRetroError) as exc:
        require_valid_active_sprint_retro_comment(comment)

    assert "agent_process_problematic_elements" in str(exc.value)
