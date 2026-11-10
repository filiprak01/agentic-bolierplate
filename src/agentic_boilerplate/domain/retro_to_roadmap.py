"""Retro follow-up routing workflow."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum


class RetroFindingStatus(str, Enum):
    """Decision status captured during retro review."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DEFERRED = "deferred"
    NEEDS_PO_CLARIFICATION = "needs-po-clarification"


class RetroRoutingTarget(str, Enum):
    """Destination for one retro finding."""

    EXISTING_STORY = "existing-story"
    NEW_BACKLOG_STORY = "new-backlog-story"
    DOCUMENTATION_UPDATE = "documentation-update"
    DEFERRED_ROADMAP = "deferred-roadmap"
    REJECTED = "rejected"
    NEEDS_PO_CLARIFICATION = "needs-po-clarification"


@dataclass(frozen=True)
class RetroFinding:
    """One sprint retro or post-mortem follow-up."""

    id: str
    title: str
    summary: str
    status: RetroFindingStatus
    rationale: str = ""
    existing_issue_key: str = ""
    proposed_story_title: str = ""
    documentation_update_path: str = ""
    roadmap_bucket: str = ""


@dataclass(frozen=True)
class RetroRoutingDecision:
    """Routing decision for one retro finding."""

    finding_id: str
    status: RetroFindingStatus
    target: RetroRoutingTarget
    existing_issue_key: str = ""
    proposed_story_title: str = ""
    documentation_update_path: str = ""
    roadmap_bucket: str = ""


@dataclass(frozen=True)
class RetroFollowUpStoryDraft:
    """Jira-ready draft metadata for one retro follow-up story."""

    summary: str
    initial_status: str
    labels: tuple[str, ...]
    recommended_sprint_label: str = ""


@dataclass(frozen=True)
class RetroCleanupDecision:
    """Decision for one uncommitted local file before sprint start."""

    path: str
    action: str


@dataclass(frozen=True)
class RetroToRoadmapPlan:
    """Retro routing plan and sprint-start cleanup gate."""

    publication_issue_key: str
    sprint_name: str
    routing_decisions: tuple[RetroRoutingDecision, ...]
    cleanup_decisions: tuple[RetroCleanupDecision, ...]
    blocked_uncommitted_files: tuple[str, ...]
    po_scope_change_required: bool


@dataclass(frozen=True)
class RetroToRoadmapIssue:
    """Validation issue for retro routing."""

    field: str
    message: str


class RetroToRoadmapError(ValueError):
    """Raised when retro routing input is incomplete."""

    def __init__(self, issues: Sequence[RetroToRoadmapIssue]) -> None:
        self.issues = tuple(issues)
        super().__init__(format_retro_to_roadmap_issues(self.issues))


def route_retro_finding(finding: RetroFinding) -> RetroRoutingDecision:
    """Route one retro finding into the proper backlog or documentation bucket."""

    _require_text("id", finding.id)
    _require_text("title", finding.title)
    _require_text("summary", finding.summary)
    if finding.status is RetroFindingStatus.ACCEPTED:
        if finding.existing_issue_key.strip():
            return RetroRoutingDecision(
                finding_id=finding.id,
                status=finding.status,
                target=RetroRoutingTarget.EXISTING_STORY,
                existing_issue_key=finding.existing_issue_key.strip(),
            )
        if finding.documentation_update_path.strip():
            return RetroRoutingDecision(
                finding_id=finding.id,
                status=finding.status,
                target=RetroRoutingTarget.DOCUMENTATION_UPDATE,
                documentation_update_path=finding.documentation_update_path.strip(),
            )
        if finding.proposed_story_title.strip():
            return RetroRoutingDecision(
                finding_id=finding.id,
                status=finding.status,
                target=RetroRoutingTarget.NEW_BACKLOG_STORY,
                proposed_story_title=finding.proposed_story_title.strip(),
            )
        raise RetroToRoadmapError(
            (
                RetroToRoadmapIssue(
                    "finding",
                    "Accepted retro findings must map to an existing story, a new backlog story, or a documentation update.",
                ),
            )
        )
    if finding.status is RetroFindingStatus.DEFERRED:
        if not finding.roadmap_bucket.strip():
            raise RetroToRoadmapError(
                (RetroToRoadmapIssue("roadmap_bucket", "Deferred findings require a roadmap bucket."),)
            )
        return RetroRoutingDecision(
            finding_id=finding.id,
            status=finding.status,
            target=RetroRoutingTarget.DEFERRED_ROADMAP,
            roadmap_bucket=finding.roadmap_bucket.strip(),
        )
    if finding.status is RetroFindingStatus.REJECTED:
        return RetroRoutingDecision(
            finding_id=finding.id,
            status=finding.status,
            target=RetroRoutingTarget.REJECTED,
        )
    return RetroRoutingDecision(
        finding_id=finding.id,
        status=finding.status,
        target=RetroRoutingTarget.NEEDS_PO_CLARIFICATION,
    )


def build_retro_to_roadmap_plan(
    *,
    publication_issue_key: str,
    sprint_name: str,
    findings: tuple[RetroFinding, ...],
    changed_local_files: tuple[str, ...] = (),
    parked_local_notes: tuple[str, ...] = (),
    explicitly_excluded_files: tuple[str, ...] = (),
) -> RetroToRoadmapPlan:
    """Build retro routing decisions and pre-sprint cleanup gating."""

    _require_text("publication_issue_key", publication_issue_key)
    _require_text("sprint_name", sprint_name)
    if not findings:
        raise RetroToRoadmapError((RetroToRoadmapIssue("findings", "At least one retro finding is required."),))

    routing_decisions = tuple(route_retro_finding(finding) for finding in findings)
    parked = {path.strip() for path in parked_local_notes if path.strip()}
    excluded = {path.strip() for path in explicitly_excluded_files if path.strip()}
    cleanup_decisions: list[RetroCleanupDecision] = []
    blocked: list[str] = []
    for path in changed_local_files:
        normalized = path.strip()
        if not normalized:
            continue
        if normalized in parked:
            cleanup_decisions.append(RetroCleanupDecision(path=normalized, action="park"))
            continue
        if normalized in excluded:
            cleanup_decisions.append(RetroCleanupDecision(path=normalized, action="exclude"))
            continue
        cleanup_decisions.append(RetroCleanupDecision(path=normalized, action="push"))
        blocked.append(normalized)

    po_scope_change_required = any(
        decision.target in (RetroRoutingTarget.NEW_BACKLOG_STORY, RetroRoutingTarget.NEEDS_PO_CLARIFICATION)
        for decision in routing_decisions
    )
    return RetroToRoadmapPlan(
        publication_issue_key=publication_issue_key.strip(),
        sprint_name=sprint_name.strip(),
        routing_decisions=routing_decisions,
        cleanup_decisions=tuple(cleanup_decisions),
        blocked_uncommitted_files=tuple(blocked),
        po_scope_change_required=po_scope_change_required,
    )


def build_retro_follow_up_story_draft(
    decision: RetroRoutingDecision,
    *,
    recommended_sprint_label: str = "",
) -> RetroFollowUpStoryDraft:
    """Build PO-reviewed Jira draft metadata for a new retro follow-up story."""

    if decision.target is not RetroRoutingTarget.NEW_BACKLOG_STORY:
        raise RetroToRoadmapError(
            (RetroToRoadmapIssue("target", "Only new backlog story decisions can create follow-up drafts."),)
        )
    _require_text("proposed_story_title", decision.proposed_story_title)
    labels = ["retro-followup", "po-review-required"]
    sprint_label = recommended_sprint_label.strip()
    if sprint_label:
        labels.append(sprint_label)
    return RetroFollowUpStoryDraft(
        summary=decision.proposed_story_title.strip(),
        initial_status="FUNNEL",
        labels=tuple(labels),
        recommended_sprint_label=sprint_label,
    )


def render_retro_to_roadmap_summary(plan: RetroToRoadmapPlan) -> str:
    """Render a concise summary for retro publication or local review."""

    lines = [
        f"Sprint: {plan.sprint_name}",
        f"Publication issue: {plan.publication_issue_key}",
        "",
        "Retro routing:",
    ]
    for decision in plan.routing_decisions:
        lines.append(f"- {decision.finding_id}: {decision.target.value}")
    if plan.cleanup_decisions:
        lines.extend(["", "Local file actions:"])
        for cleanup in plan.cleanup_decisions:
            lines.append(f"- {cleanup.path}: {cleanup.action}")
    return "\n".join(lines).strip()


def format_retro_to_roadmap_issues(issues: Sequence[RetroToRoadmapIssue]) -> str:
    return "; ".join(f"{issue.field}: {issue.message}" for issue in issues)


def _require_text(field: str, value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise RetroToRoadmapError((RetroToRoadmapIssue(field, "Value is required."),))
    return normalized
