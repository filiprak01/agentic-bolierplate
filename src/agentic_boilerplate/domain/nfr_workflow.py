"""Architecture Agent non-functional requirement workflow."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from agentic_boilerplate.domain.documentation_governance import (
    ApprovedSharedDocumentationContent,
    DocumentationProposal,
    DocumentationProposalStatus,
    DocumentationScope,
    SharedDocumentationCategory,
    build_approved_shared_content,
)
from agentic_boilerplate.domain.po_inbox import (
    AgentRole,
    InboxMessageType,
    InboxOption,
    InboxStatus,
    POInboxItem,
    require_valid_inbox_item,
)


class NFRWorkflowError(ValueError):
    """Raised when NFR workflow input is incomplete."""


class NFRCategory(str, Enum):
    """Required non-functional requirement checklist categories."""

    PERFORMANCE = "performance"
    SECURITY = "security"
    RELIABILITY = "reliability"
    OBSERVABILITY = "observability"
    MAINTAINABILITY = "maintainability"
    COST = "cost"
    TOKEN_OPTIMIZATION = "token_optimization"
    DATA_RETENTION = "data_retention"


@dataclass(frozen=True)
class NFRChecklistItem:
    """One required Architecture Agent NFR checklist item."""

    category: NFRCategory
    title: str
    question: str
    business_impact: str
    recommendation: str


@dataclass(frozen=True)
class NFRAnswer:
    """Product Owner answer for one NFR category."""

    category: NFRCategory
    answer: str
    source_inbox_item_id: str
    answered_at: str
    affected_stories: tuple[str, ...]


@dataclass(frozen=True)
class NFRDocumentationPromotion:
    """Documentation artifacts produced from approved NFR answers."""

    proposal: DocumentationProposal
    approved_content: ApprovedSharedDocumentationContent
    answers: tuple[NFRAnswer, ...]


@dataclass(frozen=True)
class NFRStoryFollowUp:
    """Marker data used to flag stories affected by NFR decisions."""

    story_key: str
    nfr_categories: tuple[NFRCategory, ...]
    labels: tuple[str, ...]
    note: str


NFR_CHECKLIST: tuple[NFRChecklistItem, ...] = (
    NFRChecklistItem(
        category=NFRCategory.PERFORMANCE,
        title="Performance",
        question="What performance expectations or response-time limits must this work meet?",
        business_impact="Performance requirements can change architecture, caching, batching, and test scope.",
        recommendation="Define measurable limits or explicitly confirm that no special performance target exists.",
    ),
    NFRChecklistItem(
        category=NFRCategory.SECURITY,
        title="Security",
        question="What security constraints, access rules, or threat assumptions must this work respect?",
        business_impact="Missing security requirements can create unsafe data exposure or incorrect trust boundaries.",
        recommendation="Document required permissions, secret handling, and security-sensitive data paths.",
    ),
    NFRChecklistItem(
        category=NFRCategory.RELIABILITY,
        title="Reliability",
        question="What failure, retry, recovery, or durability behavior is expected?",
        business_impact="Reliability expectations affect storage, worker resume behavior, retries, and error reporting.",
        recommendation="Specify required recovery behavior and acceptable failure handling before implementation.",
    ),
    NFRChecklistItem(
        category=NFRCategory.OBSERVABILITY,
        title="Observability",
        question="What logs, evidence, metrics, or audit records should this work produce?",
        business_impact="Observability controls whether the Product Owner and agents can diagnose work safely later.",
        recommendation="Define the minimum logs, evidence files, or audit records needed for operation and review.",
    ),
    NFRChecklistItem(
        category=NFRCategory.MAINTAINABILITY,
        title="Maintainability",
        question="What maintainability, extensibility, or ownership constraints should guide the design?",
        business_impact="Maintainability choices affect future agent changes, role boundaries, and regression cost.",
        recommendation="State expected extension points, ownership boundaries, and avoided complexity.",
    ),
    NFRChecklistItem(
        category=NFRCategory.COST,
        title="Cost",
        question="What cost or quota constraints should this work optimize for?",
        business_impact="Cost constraints can affect model selection, batching, storage, and external tool usage.",
        recommendation="Document acceptable cost tradeoffs and whether cheaper execution paths are preferred.",
    ),
    NFRChecklistItem(
        category=NFRCategory.TOKEN_OPTIMIZATION,
        title="Token Optimization",
        question="What token budget or model-routing constraints should apply when AI behavior is involved?",
        business_impact="Token optimization requirements control Codex usage, context size, and model escalation.",
        recommendation="Define default model, reasoning level, context limits, and escalation conditions.",
    ),
    NFRChecklistItem(
        category=NFRCategory.DATA_RETENTION,
        title="Data Retention",
        question="What data should be retained, redacted, archived, or deleted after this work runs?",
        business_impact="Data retention requirements affect local durability, audit history, privacy, and cleanup.",
        recommendation="Document retention period, redaction expectations, and cleanup ownership.",
    ),
)


def nfr_checklist_categories() -> tuple[NFRCategory, ...]:
    """Return required NFR categories in Architecture Agent checklist order."""

    return tuple(item.category for item in NFR_CHECKLIST)


def missing_nfr_categories(answered_categories: set[NFRCategory] | frozenset[NFRCategory]) -> tuple[NFRCategory, ...]:
    """Return checklist categories that still need Product Owner input."""

    return tuple(category for category in nfr_checklist_categories() if category not in answered_categories)


def build_missing_nfr_questions(
    *,
    story_key: str,
    architecture_title: str,
    answered_categories: set[NFRCategory] | frozenset[NFRCategory],
    created_at: str,
    agent_id: str = "architecture-agent",
    context_pack_path: str = "",
) -> tuple[POInboxItem, ...]:
    """Build PO inbox blocking questions for missing NFR checklist categories."""

    _require_text("story_key", story_key)
    _require_text("architecture_title", architecture_title)
    _require_text("created_at", created_at)

    checklist_by_category = {item.category: item for item in NFR_CHECKLIST}
    questions: list[POInboxItem] = []
    for category in missing_nfr_categories(answered_categories):
        item = checklist_by_category[category]
        inbox_item = POInboxItem(
            id=f"{story_key}-nfr-{category.value}",
            message_type=InboxMessageType.BLOCKING_QUESTION,
            status=InboxStatus.OPEN,
            title=f"NFR needed: {item.title}",
            message=(
                f"{item.question}\n\n"
                f"Architecture context: {architecture_title}\n"
                f"Story: {story_key}"
            ),
            agent_role=AgentRole.ARCHITECTURE,
            created_at=created_at,
            agent_id=agent_id,
            jira_issue_key=story_key,
            context_pack_path=context_pack_path,
            business_impact=item.business_impact,
            recommendation=item.recommendation,
            options=(
                InboxOption(
                    id="provide_requirement",
                    label="Provide requirement",
                    description="Product Owner provides a concrete NFR for this category.",
                ),
                InboxOption(
                    id="not_applicable",
                    label="Not applicable",
                    description="Product Owner confirms this category does not affect the story.",
                ),
            ),
        )
        questions.append(require_valid_inbox_item(inbox_item))
    return tuple(questions)


def nfr_answer_from_inbox_item(
    *,
    category: NFRCategory,
    inbox_item: POInboxItem,
    affected_stories: tuple[str, ...] = (),
) -> NFRAnswer:
    """Create an NFR answer from an answered PO inbox item."""

    require_valid_inbox_item(inbox_item)
    if inbox_item.message_type != InboxMessageType.BLOCKING_QUESTION:
        raise NFRWorkflowError("NFR answers must come from blocking-question inbox items")
    if inbox_item.status != InboxStatus.ANSWERED:
        raise NFRWorkflowError("NFR inbox item must be answered before promotion")
    if inbox_item.agent_role != AgentRole.ARCHITECTURE:
        raise NFRWorkflowError("NFR inbox item must be created by the Architecture Agent")

    stories = affected_stories or ((inbox_item.jira_issue_key,) if inbox_item.jira_issue_key else ())
    _require_items("affected_stories", stories)
    return NFRAnswer(
        category=category,
        answer=inbox_item.answer,
        source_inbox_item_id=inbox_item.id,
        answered_at=inbox_item.answered_at,
        affected_stories=stories,
    )


def promote_nfr_answers_to_documentation(
    *,
    story_key: str,
    architecture_title: str,
    answers: tuple[NFRAnswer, ...],
    proposal_key: str,
    content_path: Path,
    confluence_page_id: str = "",
) -> NFRDocumentationPromotion:
    """Promote answered NFR decisions into approved shared documentation content."""

    _require_text("story_key", story_key)
    _require_text("architecture_title", architecture_title)
    _require_text("proposal_key", proposal_key)
    if not answers:
        raise NFRWorkflowError("at least one NFR answer is required")

    body_storage = render_nfr_answers_markdown(
        story_key=story_key,
        architecture_title=architecture_title,
        answers=answers,
    )
    proposal = DocumentationProposal(
        key=proposal_key,
        title=f"{architecture_title} NFR Decisions",
        category=SharedDocumentationCategory.REQUIREMENTS.value,
        status=DocumentationProposalStatus.APPROVED,
        content_path=content_path,
        scope=DocumentationScope.SHARED,
        confluence_page_id=confluence_page_id,
    )
    approved_content = build_approved_shared_content(proposal, body_storage=body_storage)
    return NFRDocumentationPromotion(
        proposal=proposal,
        approved_content=approved_content,
        answers=answers,
    )


def render_nfr_answers_markdown(
    *,
    story_key: str,
    architecture_title: str,
    answers: tuple[NFRAnswer, ...],
) -> str:
    """Render NFR answers as shared requirements documentation."""

    _require_text("story_key", story_key)
    _require_text("architecture_title", architecture_title)
    if not answers:
        raise NFRWorkflowError("at least one NFR answer is required")

    lines: list[str] = [
        f"# {architecture_title} NFR Decisions",
        "",
        f"story: {story_key}",
        "category: requirements",
        "scope: shared",
        "",
    ]
    checklist_by_category = {item.category: item for item in NFR_CHECKLIST}
    for answer in answers:
        _require_text("answer", answer.answer)
        _require_text("source_inbox_item_id", answer.source_inbox_item_id)
        _require_text("answered_at", answer.answered_at)
        _require_items("affected_stories", answer.affected_stories)
        title = checklist_by_category[answer.category].title
        lines.extend(
            [
                f"## {title}",
                "",
                f"source_inbox_item_id: {answer.source_inbox_item_id}",
                f"answered_at: {answer.answered_at}",
                "",
                "Affected stories:",
                *_bullet_lines(answer.affected_stories),
                "",
                answer.answer,
                "",
            ]
        )
    return "\n".join(lines)


def build_nfr_follow_up_markers(answers: tuple[NFRAnswer, ...]) -> tuple[NFRStoryFollowUp, ...]:
    """Build affected-story follow-up markers from promoted NFR answers."""

    if not answers:
        return ()

    categories_by_story: dict[str, list[NFRCategory]] = {}
    for answer in answers:
        _require_items("affected_stories", answer.affected_stories)
        for story_key in answer.affected_stories:
            categories_by_story.setdefault(story_key, []).append(answer.category)

    markers: list[NFRStoryFollowUp] = []
    for story_key in sorted(categories_by_story):
        categories = tuple(dict.fromkeys(categories_by_story[story_key]))
        labels = ("nfr-follow-up",) + tuple(f"nfr-{category.value.replace('_', '-')}" for category in categories)
        markers.append(
            NFRStoryFollowUp(
                story_key=story_key,
                nfr_categories=categories,
                labels=labels,
                note=(
                    "Review answered Architecture Agent NFR decisions before implementation: "
                    + ", ".join(category.value for category in categories)
                ),
            )
        )
    return tuple(markers)


def _require_text(field_name: str, value: str) -> None:
    if not value.strip():
        raise NFRWorkflowError(f"{field_name} is required")


def _require_items(field_name: str, value: tuple[str, ...]) -> None:
    if not value:
        raise NFRWorkflowError(f"{field_name} is required")
    for index, item in enumerate(value):
        if not item.strip():
            raise NFRWorkflowError(f"{field_name}[{index}] is required")


def _bullet_lines(items: tuple[str, ...]) -> list[str]:
    return [f"- {item}" for item in items]
