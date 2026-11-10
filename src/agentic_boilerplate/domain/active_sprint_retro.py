"""Active-sprint retro intake workflow."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from agentic_boilerplate.domain.po_inbox import (
    AgentRole,
    InboxMessageType,
    InboxStatus,
    POInboxItem,
    require_valid_inbox_item,
)


ACTIVE_SPRINT_RETRO_CREATION_TIMING = (
    "Create one board-visible retro intake Task during sprint setup, add it to "
    "the active sprint before the first delivery item starts, and keep it open "
    "until every participating role has submitted or explicitly skipped retro input."
)

ACTIVE_SPRINT_RETRO_PO_APPROVAL_RULE = (
    "For each submitted retro comment, Release Manager creates a PO inbox "
    "approval_request linked to the active sprint retro issue before treating "
    "the comment as accepted retro input. Rejected comments remain visible but "
    "are not routed into follow-up Jira work."
)


@dataclass(frozen=True)
class ActiveSprintRetroIntakePlan:
    """Reusable active-sprint retro intake contract."""

    sprint_name: str
    retro_issue_key: str
    delivery_issue_keys: tuple[str, ...]
    participant_roles: tuple[str, ...]
    creation_timing: str
    comment_template: str
    po_approval_rule: str


@dataclass(frozen=True)
class ActiveSprintRetroComment:
    """One participant's retro input for the active sprint."""

    retro_issue_key: str
    participant_role: str
    participant_name: str
    airlines_project_problematic_elements: tuple[str, ...]
    airlines_project_suggestions: tuple[str, ...]
    agent_process_problematic_elements: tuple[str, ...]
    agent_process_suggestions: tuple[str, ...]
    submitted_comment_id: str = ""


@dataclass(frozen=True)
class ActiveSprintRetroIssue:
    """Validation issue for active-sprint retro intake."""

    field: str
    message: str


class ActiveSprintRetroError(ValueError):
    """Raised when retro intake input is incomplete."""

    def __init__(self, issues: Sequence[ActiveSprintRetroIssue]) -> None:
        self.issues = tuple(issues)
        super().__init__(format_active_sprint_retro_issues(self.issues))


def build_active_sprint_retro_intake_plan(
    *,
    sprint_name: str,
    retro_issue_key: str,
    delivery_issue_keys: tuple[str, ...],
    participant_roles: tuple[str, ...],
) -> ActiveSprintRetroIntakePlan:
    """Build the active-sprint retro intake setup contract."""

    return ActiveSprintRetroIntakePlan(
        sprint_name=_require_text("sprint_name", sprint_name),
        retro_issue_key=_require_text("retro_issue_key", retro_issue_key),
        delivery_issue_keys=_clean_required_tuple("delivery_issue_keys", delivery_issue_keys),
        participant_roles=_clean_required_tuple("participant_roles", participant_roles),
        creation_timing=ACTIVE_SPRINT_RETRO_CREATION_TIMING,
        comment_template=render_active_sprint_retro_comment_template(),
        po_approval_rule=ACTIVE_SPRINT_RETRO_PO_APPROVAL_RULE,
    )


def render_active_sprint_retro_comment_template(participant_role: str = "<agent-role>") -> str:
    """Render the required Jira comment template for retro participants."""

    role = _require_text("participant_role", participant_role)
    return "\n".join(
        (
            f"## Retro Input - {role}",
            "",
            "### Airlines Project Element",
            "",
            "Problematic elements:",
            "- ",
            "",
            "Suggestions:",
            "- ",
            "",
            "### Agent/Process Element",
            "",
            "Problematic elements:",
            "- ",
            "",
            "Suggestions:",
            "- ",
        )
    )


def validate_active_sprint_retro_comment(comment: ActiveSprintRetroComment) -> tuple[ActiveSprintRetroIssue, ...]:
    """Validate that one retro comment contains both required sections."""

    issues: list[ActiveSprintRetroIssue] = []
    _collect_required_text(issues, "retro_issue_key", comment.retro_issue_key)
    _collect_required_text(issues, "participant_role", comment.participant_role)
    _collect_required_text(issues, "participant_name", comment.participant_name)
    _collect_required_items(
        issues,
        "airlines_project_problematic_elements",
        comment.airlines_project_problematic_elements,
    )
    _collect_required_items(issues, "airlines_project_suggestions", comment.airlines_project_suggestions)
    _collect_required_items(
        issues,
        "agent_process_problematic_elements",
        comment.agent_process_problematic_elements,
    )
    _collect_required_items(issues, "agent_process_suggestions", comment.agent_process_suggestions)
    return tuple(issues)


def require_valid_active_sprint_retro_comment(comment: ActiveSprintRetroComment) -> ActiveSprintRetroComment:
    """Return a retro comment or raise with visible validation issues."""

    issues = validate_active_sprint_retro_comment(comment)
    if issues:
        raise ActiveSprintRetroError(issues)
    return comment


def render_active_sprint_retro_comment(comment: ActiveSprintRetroComment) -> str:
    """Render one validated retro comment for Jira or evidence."""

    require_valid_active_sprint_retro_comment(comment)
    return "\n".join(
        (
            f"## Retro Input - {comment.participant_role.strip()}",
            "",
            f"Participant: {comment.participant_name.strip()}",
            f"Retro issue: {comment.retro_issue_key.strip()}",
            "",
            "### Airlines Project Element",
            "",
            "Problematic elements:",
            *_bullet_lines(comment.airlines_project_problematic_elements),
            "",
            "Suggestions:",
            *_bullet_lines(comment.airlines_project_suggestions),
            "",
            "### Agent/Process Element",
            "",
            "Problematic elements:",
            *_bullet_lines(comment.agent_process_problematic_elements),
            "",
            "Suggestions:",
            *_bullet_lines(comment.agent_process_suggestions),
        )
    )


def build_retro_comment_po_approval_item(
    comment: ActiveSprintRetroComment,
    *,
    item_id: str,
    created_at: str,
    agent_id: str = "release-manager",
) -> POInboxItem:
    """Build a PO inbox approval request for one submitted retro comment."""

    require_valid_active_sprint_retro_comment(comment)
    item = POInboxItem(
        id=_require_text("item_id", item_id),
        message_type=InboxMessageType.APPROVAL_REQUEST,
        status=InboxStatus.OPEN,
        title=(
            f"Approve retro input from {comment.participant_role.strip()} "
            f"for {comment.retro_issue_key.strip()}"
        ),
        message=(
            "Please verify whether this retro input is valid for sprint routing.\n\n"
            + render_active_sprint_retro_comment(comment)
        ),
        agent_role=AgentRole.RELEASE_MANAGER,
        created_at=_require_text("created_at", created_at),
        agent_id=agent_id.strip(),
        jira_issue_key=comment.retro_issue_key.strip(),
        business_impact=(
            "Retro comments can create follow-up stories or process changes. "
            "PO approval prevents invalid or misunderstood comments from changing scope."
        ),
        recommendation=(
            "Approve only when both the airlines-project element and the "
            "agent/process element are specific enough to route; reject or ask "
            "for clarification when either section is incomplete."
        ),
    )
    require_valid_inbox_item(item)
    return item


def render_active_sprint_retro_intake_plan(plan: ActiveSprintRetroIntakePlan) -> str:
    """Render the active-sprint retro intake plan for docs or Jira."""

    lines = [
        f"# Active Sprint Retro Intake - {plan.sprint_name}",
        "",
        f"Retro issue: `{plan.retro_issue_key}`",
        "",
        "## Creation Timing",
        "",
        plan.creation_timing,
        "",
        "## Delivery Scope",
        "",
        *[f"- `{key}`" for key in plan.delivery_issue_keys],
        "",
        "## Participant Roles",
        "",
        *[f"- `{role}`" for role in plan.participant_roles],
        "",
        "## PO Approval Rule",
        "",
        plan.po_approval_rule,
        "",
        "## Comment Template",
        "",
        plan.comment_template,
    ]
    return "\n".join(lines).strip() + "\n"


def format_active_sprint_retro_issues(issues: Sequence[ActiveSprintRetroIssue]) -> str:
    """Format active-sprint retro validation issues."""

    return "; ".join(f"{issue.field}: {issue.message}" for issue in issues)


def _clean_required_tuple(field: str, values: tuple[str, ...]) -> tuple[str, ...]:
    cleaned = tuple(value.strip() for value in values if value.strip())
    if not cleaned:
        raise ActiveSprintRetroError((ActiveSprintRetroIssue(field, "At least one value is required."),))
    return cleaned


def _collect_required_text(issues: list[ActiveSprintRetroIssue], field: str, value: str) -> None:
    if not value.strip():
        issues.append(ActiveSprintRetroIssue(field, "Value is required."))


def _collect_required_items(issues: list[ActiveSprintRetroIssue], field: str, values: tuple[str, ...]) -> None:
    if not any(value.strip() for value in values):
        issues.append(ActiveSprintRetroIssue(field, "At least one item is required."))


def _require_text(field: str, value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ActiveSprintRetroError((ActiveSprintRetroIssue(field, "Value is required."),))
    return normalized


def _bullet_lines(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(f"- {value.strip()}" for value in values if value.strip())
