"""Sprint lifecycle synchronization policy for Jira-backed Scrum boards."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class JiraSprintLifecycleError(ValueError):
    """Raised when sprint lifecycle synchronization input is invalid."""


class JiraSprintLifecycleAction(str, Enum):
    """Supported sprint lifecycle actions."""

    NOOP = "noop"
    START = "start"
    CLOSE = "close"
    BLOCKED = "blocked"


class JiraSprintLifecycleBlockerKind(str, Enum):
    """Reasons a sprint lifecycle change is blocked."""

    MISSING_SPRINT_ID = "missing_sprint_id"
    MISSING_SPRINT_NAME = "missing_sprint_name"
    UNSUPPORTED_TRANSITION = "unsupported_transition"
    START_DATES_REQUIRED = "start_dates_required"
    DOCUMENTED_STATE_MISMATCH = "documented_state_mismatch"
    REQUIRED_SUPPORT_ISSUE_MISSING = "required_support_issue_missing"
    SPRINT_ITEMS_NOT_ACCEPTED = "sprint_items_not_accepted"
    REGRESSION_NOT_PASSED = "regression_not_passed"
    RETRO_NOT_COMPLETED = "retro_not_completed"


@dataclass(frozen=True)
class JiraSprintSupportIssue:
    """Board-visible support issue that must be aligned with sprint lifecycle."""

    issue_key: str
    summary: str
    issue_type: str
    present_in_sprint: bool
    required_for_close: bool = True


@dataclass(frozen=True)
class JiraSprintLifecycleRequest:
    """Inputs used to decide whether a sprint lifecycle sync is allowed."""

    sprint_id: str
    sprint_name: str
    current_state: str
    target_state: str
    documented_expected_state: str = ""
    start_date: str = ""
    end_date: str = ""
    support_issues: tuple[JiraSprintSupportIssue, ...] = ()
    all_sprint_items_accepted: bool = True
    regression_passed: bool = True
    retro_completed: bool = True


@dataclass(frozen=True)
class JiraSprintLifecycleBlocker:
    """Structured blocker for sprint lifecycle sync."""

    kind: JiraSprintLifecycleBlockerKind
    message: str
    issue_key: str = ""


@dataclass(frozen=True)
class JiraSprintLifecycleDecision:
    """Inspectable sprint lifecycle decision."""

    sprint_id: str
    sprint_name: str
    current_state: str
    target_state: str
    action: JiraSprintLifecycleAction
    allowed: bool
    blockers: tuple[JiraSprintLifecycleBlocker, ...]
    reasons: tuple[str, ...]
    missing_support_issue_keys: tuple[str, ...] = ()
    po_question: str = ""

    @property
    def should_record_change(self) -> bool:
        return self.allowed and self.current_state.casefold() != self.target_state.casefold()


def evaluate_jira_sprint_lifecycle_sync(
    request: JiraSprintLifecycleRequest,
) -> JiraSprintLifecycleDecision:
    """Evaluate sprint lifecycle alignment before Jira state is changed."""

    blockers: list[JiraSprintLifecycleBlocker] = []
    sprint_id = request.sprint_id.strip()
    sprint_name = request.sprint_name.strip()
    if not sprint_id:
        blockers.append(
            JiraSprintLifecycleBlocker(
                kind=JiraSprintLifecycleBlockerKind.MISSING_SPRINT_ID,
                message="Sprint id is required.",
            )
        )
    if not sprint_name:
        blockers.append(
            JiraSprintLifecycleBlocker(
                kind=JiraSprintLifecycleBlockerKind.MISSING_SPRINT_NAME,
                message="Sprint name is required.",
            )
        )

    current = _normalize_state(request.current_state)
    target = _normalize_state(request.target_state)
    documented = _normalize_state(request.documented_expected_state)
    if documented and current != documented:
        blockers.append(
            JiraSprintLifecycleBlocker(
                kind=JiraSprintLifecycleBlockerKind.DOCUMENTED_STATE_MISMATCH,
                message=(
                    f"Jira sprint state is {request.current_state}, but shared process context expects "
                    f"{request.documented_expected_state}."
                ),
            )
        )

    action = _determine_action(current, target, blockers, request)
    missing_support = _missing_support_issues_for_target(target, request.support_issues)
    blockers.extend(
        JiraSprintLifecycleBlocker(
            kind=JiraSprintLifecycleBlockerKind.REQUIRED_SUPPORT_ISSUE_MISSING,
            issue_key=issue.issue_key,
            message=(
                f"{issue.issue_key} ({issue.issue_type}) must be assigned to the sprint before it can close."
            ),
        )
        for issue in missing_support
    )
    if target == "closed":
        blockers.extend(_close_readiness_blockers(request))

    allowed = not blockers
    return JiraSprintLifecycleDecision(
        sprint_id=sprint_id,
        sprint_name=sprint_name,
        current_state=request.current_state,
        target_state=request.target_state,
        action=action if allowed else JiraSprintLifecycleAction.BLOCKED,
        allowed=allowed,
        blockers=tuple(blockers),
        reasons=_decision_reasons(
            allowed=allowed,
            action=action,
            sprint_id=sprint_id,
            blockers=blockers,
        ),
        missing_support_issue_keys=tuple(issue.issue_key for issue in missing_support),
        po_question=_po_question_for_mismatch(request) if documented and current != documented else "",
    )


def render_jira_sprint_lifecycle_decision(decision: JiraSprintLifecycleDecision) -> str:
    """Render a durable Markdown note for sprint lifecycle sync."""

    lines = [
        f"# Jira Sprint Lifecycle Sync - {decision.sprint_name or decision.sprint_id}",
        "",
        f"- Sprint id: {decision.sprint_id}",
        f"- Current state: {decision.current_state}",
        f"- Target state: {decision.target_state}",
        f"- Action: {decision.action.value}",
        f"- Allowed: {'yes' if decision.allowed else 'no'}",
        f"- Record lifecycle change: {'yes' if decision.should_record_change else 'no'}",
        "",
        "## Reasons",
    ]
    lines.extend(f"- {reason}" for reason in decision.reasons)
    lines.extend(["", "## Missing Sprint Support Issues"])
    if decision.missing_support_issue_keys:
        lines.extend(f"- {issue_key}" for issue_key in decision.missing_support_issue_keys)
    else:
        lines.append("- None")
    lines.extend(["", "## Blockers"])
    if decision.blockers:
        for blocker in decision.blockers:
            target = f" {blocker.issue_key}" if blocker.issue_key else ""
            lines.append(f"- {blocker.kind.value}{target}: {blocker.message}")
    else:
        lines.append("- None")
    if decision.po_question:
        lines.extend(["", "## Product Owner Question", f"- {decision.po_question}"])
    return "\n".join(lines) + "\n"


def _determine_action(
    current: str,
    target: str,
    blockers: list[JiraSprintLifecycleBlocker],
    request: JiraSprintLifecycleRequest,
) -> JiraSprintLifecycleAction:
    if current == target:
        return JiraSprintLifecycleAction.NOOP
    if current == "future" and target == "active":
        if not request.start_date.strip() or not request.end_date.strip():
            blockers.append(
                JiraSprintLifecycleBlocker(
                    kind=JiraSprintLifecycleBlockerKind.START_DATES_REQUIRED,
                    message="Sprint start requires start_date and end_date.",
                )
            )
        return JiraSprintLifecycleAction.START
    if current == "active" and target == "closed":
        return JiraSprintLifecycleAction.CLOSE
    blockers.append(
        JiraSprintLifecycleBlocker(
            kind=JiraSprintLifecycleBlockerKind.UNSUPPORTED_TRANSITION,
            message=f"Unsupported Jira sprint transition: {request.current_state} -> {request.target_state}.",
        )
    )
    return JiraSprintLifecycleAction.BLOCKED


def _missing_support_issues_for_target(
    target: str,
    support_issues: tuple[JiraSprintSupportIssue, ...],
) -> tuple[JiraSprintSupportIssue, ...]:
    if target != "closed":
        return ()
    return tuple(
        issue
        for issue in support_issues
        if issue.required_for_close and not issue.present_in_sprint
    )


def _close_readiness_blockers(request: JiraSprintLifecycleRequest) -> tuple[JiraSprintLifecycleBlocker, ...]:
    blockers: list[JiraSprintLifecycleBlocker] = []
    if not request.all_sprint_items_accepted:
        blockers.append(
            JiraSprintLifecycleBlocker(
                kind=JiraSprintLifecycleBlockerKind.SPRINT_ITEMS_NOT_ACCEPTED,
                message="All sprint items must be ACCEPTED/DONE before sprint closure.",
            )
        )
    if not request.regression_passed:
        blockers.append(
            JiraSprintLifecycleBlocker(
                kind=JiraSprintLifecycleBlockerKind.REGRESSION_NOT_PASSED,
                message="Sprint regression must pass before sprint closure.",
            )
        )
    if not request.retro_completed:
        blockers.append(
            JiraSprintLifecycleBlocker(
                kind=JiraSprintLifecycleBlockerKind.RETRO_NOT_COMPLETED,
                message="Sprint retro and closure task must be completed before sprint closure.",
            )
        )
    return tuple(blockers)


def _decision_reasons(
    *,
    allowed: bool,
    action: JiraSprintLifecycleAction,
    sprint_id: str,
    blockers: list[JiraSprintLifecycleBlocker],
) -> tuple[str, ...]:
    if not allowed:
        return tuple(blocker.message for blocker in blockers)
    if action == JiraSprintLifecycleAction.NOOP:
        return (f"{sprint_id} already matches the target lifecycle state.",)
    if action == JiraSprintLifecycleAction.START:
        return (f"{sprint_id} can be activated in Jira.",)
    if action == JiraSprintLifecycleAction.CLOSE:
        return (f"{sprint_id} can be closed after required regression and retro items are present.",)
    return (f"{sprint_id} is blocked.",)


def _po_question_for_mismatch(request: JiraSprintLifecycleRequest) -> str:
    return (
        f"Should sprint {request.sprint_name or request.sprint_id} stay in Jira state "
        f"'{request.current_state}' or should the shared sprint documentation be updated to match it?"
    )


def _normalize_state(value: str) -> str:
    return str(value or "").strip().casefold()
