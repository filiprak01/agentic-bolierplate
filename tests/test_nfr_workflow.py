from dataclasses import replace
from pathlib import Path

import pytest

from agentic_boilerplate import domain
from agentic_boilerplate.domain.nfr_workflow import (
    NFRAnswer,
    NFRCategory,
    NFRWorkflowError,
    build_nfr_follow_up_markers,
    build_missing_nfr_questions,
    missing_nfr_categories,
    nfr_answer_from_inbox_item,
    nfr_checklist_categories,
    promote_nfr_answers_to_documentation,
    render_nfr_answers_markdown,
)
from agentic_boilerplate.domain.po_inbox import AgentRole, InboxMessageType, InboxStatus


def test_nfr_checklist_includes_required_categories() -> None:
    assert nfr_checklist_categories() == (
        NFRCategory.PERFORMANCE,
        NFRCategory.SECURITY,
        NFRCategory.RELIABILITY,
        NFRCategory.OBSERVABILITY,
        NFRCategory.MAINTAINABILITY,
        NFRCategory.COST,
        NFRCategory.TOKEN_OPTIMIZATION,
        NFRCategory.DATA_RETENTION,
    )


def test_missing_nfr_categories_excludes_answered_categories() -> None:
    missing = missing_nfr_categories(
        {
            NFRCategory.PERFORMANCE,
            NFRCategory.SECURITY,
            NFRCategory.COST,
        }
    )

    assert NFRCategory.PERFORMANCE not in missing
    assert NFRCategory.SECURITY not in missing
    assert NFRCategory.COST not in missing
    assert NFRCategory.RELIABILITY in missing
    assert NFRCategory.DATA_RETENTION in missing


def test_missing_nfrs_create_po_inbox_blocking_questions() -> None:
    questions = build_missing_nfr_questions(
        story_key="AGENT-34",
        architecture_title="Architecture Agent NFR Workflow",
        answered_categories={NFRCategory.PERFORMANCE, NFRCategory.SECURITY},
        created_at="2026-06-21T08:00:00Z",
        context_pack_path="data/context/AGENT-34.json",
    )

    assert len(questions) == 6
    assert {question.agent_role for question in questions} == {AgentRole.ARCHITECTURE}
    assert {question.message_type for question in questions} == {InboxMessageType.BLOCKING_QUESTION}
    assert {question.status for question in questions} == {InboxStatus.OPEN}
    assert questions[0].jira_issue_key == "AGENT-34"
    assert questions[0].context_pack_path == "data/context/AGENT-34.json"
    assert questions[0].business_impact
    assert questions[0].recommendation
    assert all(question.options for question in questions)
    assert "Architecture Agent NFR Workflow" in questions[0].message


def test_missing_nfr_question_generation_requires_story_context() -> None:
    with pytest.raises(NFRWorkflowError, match="story_key is required"):
        build_missing_nfr_questions(
            story_key=" ",
            architecture_title="Architecture",
            answered_categories=set(),
            created_at="2026-06-21T08:00:00Z",
        )


def answered_security_question() -> NFRAnswer:
    question = build_missing_nfr_questions(
        story_key="AGENT-34",
        architecture_title="Architecture Agent NFR Workflow",
        answered_categories={category for category in NFRCategory if category != NFRCategory.SECURITY},
        created_at="2026-06-21T08:00:00Z",
    )[0]
    answered = replace(
        question,
        status=InboxStatus.ANSWERED,
        answer="Architecture decisions must not expose tokens or Product Owner answers in logs.",
        answered_at="2026-06-21T08:10:00Z",
    )

    return nfr_answer_from_inbox_item(
        category=NFRCategory.SECURITY,
        inbox_item=answered,
        affected_stories=("AGENT-34", "AGENT-35"),
    )


def test_answered_nfr_question_promotes_to_shared_requirements_documentation() -> None:
    answer = answered_security_question()
    promotion = promote_nfr_answers_to_documentation(
        story_key="AGENT-34",
        architecture_title="Architecture Agent NFR Workflow",
        answers=(answer,),
        proposal_key="NFR-AGENT-34",
        content_path=Path("docs/requirements/agent-34-nfr.md"),
        confluence_page_id="12345",
    )

    assert promotion.proposal.category == "requirements"
    assert promotion.proposal.status.value == "approved"
    assert promotion.approved_content.durable_subpath == Path("shared/requirements")
    assert promotion.approved_content.confluence_page_id == "12345"
    assert "Architecture Agent NFR Workflow NFR Decisions" in promotion.approved_content.body_storage
    assert "Architecture decisions must not expose tokens" in promotion.approved_content.body_storage
    assert "- AGENT-35" in promotion.approved_content.body_storage


def test_nfr_answer_promotion_requires_answered_inbox_item() -> None:
    question = build_missing_nfr_questions(
        story_key="AGENT-34",
        architecture_title="Architecture Agent NFR Workflow",
        answered_categories={category for category in NFRCategory if category != NFRCategory.COST},
        created_at="2026-06-21T08:00:00Z",
    )[0]

    with pytest.raises(NFRWorkflowError, match="must be answered before promotion"):
        nfr_answer_from_inbox_item(category=NFRCategory.COST, inbox_item=question)


def test_nfr_follow_up_markers_group_affected_stories() -> None:
    security = answered_security_question()
    token = NFRAnswer(
        category=NFRCategory.TOKEN_OPTIMIZATION,
        answer="Use medium reasoning by default and escalate only for C3 or higher.",
        source_inbox_item_id="AGENT-34-nfr-token_optimization",
        answered_at="2026-06-21T08:15:00Z",
        affected_stories=("AGENT-35",),
    )

    markers = build_nfr_follow_up_markers((security, token))

    marker_by_story = {marker.story_key: marker for marker in markers}
    assert marker_by_story["AGENT-34"].labels == ("nfr-follow-up", "nfr-security")
    assert marker_by_story["AGENT-35"].labels == (
        "nfr-follow-up",
        "nfr-security",
        "nfr-token-optimization",
    )
    assert "security" in marker_by_story["AGENT-35"].note
    assert "token_optimization" in marker_by_story["AGENT-35"].note


def test_render_nfr_answers_requires_answers() -> None:
    with pytest.raises(NFRWorkflowError, match="at least one NFR answer is required"):
        render_nfr_answers_markdown(
            story_key="AGENT-34",
            architecture_title="Architecture Agent NFR Workflow",
            answers=(),
        )


def test_nfr_workflow_public_api_exports_are_available() -> None:
    assert domain.NFRCategory.SECURITY == NFRCategory.SECURITY
    assert domain.build_missing_nfr_questions is build_missing_nfr_questions
    assert domain.nfr_answer_from_inbox_item is nfr_answer_from_inbox_item
    assert domain.promote_nfr_answers_to_documentation is promote_nfr_answers_to_documentation
    assert domain.build_nfr_follow_up_markers is build_nfr_follow_up_markers
