"""Jira and AgileTest evidence publication planning."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class EvidencePublicationError(ValueError):
    """Raised when evidence publication input is invalid."""


class EvidencePublicationMode(str, Enum):
    """Execution mode for evidence publication."""

    DRY_RUN = "dry-run"
    LIVE = "live"


class EvidencePublicationActionType(str, Enum):
    """Evidence publication action categories."""

    COMMENT = "comment"
    ATTACHMENT = "attachment"
    LINK = "link"


@dataclass(frozen=True)
class EvidenceCommentPlan:
    """Planned Jira comment that references a durable evidence file."""

    issue_key: str
    evidence_path: str
    body: str


@dataclass(frozen=True)
class EvidenceAttachmentPlan:
    """Planned evidence attachment or re-attachment."""

    issue_key: str
    evidence_path: str
    filename: str = ""
    replace_existing: bool = True


@dataclass(frozen=True)
class EvidenceLinkPlan:
    """Planned Jira/AgileTest issue link for evidence traceability."""

    source_issue_key: str
    target_issue_key: str
    link_type: str
    outward_relationship: str = ""


@dataclass(frozen=True)
class EvidencePublicationFailure:
    """Failure record that preserves the local evidence path."""

    action_type: EvidencePublicationActionType
    issue_key: str
    evidence_path: str
    message: str


@dataclass(frozen=True)
class EvidencePublicationRequest:
    """Batch of evidence publication actions for one story or regression run."""

    evidence_path: str
    mode: EvidencePublicationMode
    comments: tuple[EvidenceCommentPlan, ...] = ()
    attachments: tuple[EvidenceAttachmentPlan, ...] = ()
    links: tuple[EvidenceLinkPlan, ...] = ()


@dataclass(frozen=True)
class EvidencePublicationAction:
    """Completed or planned evidence publication action."""

    action_type: EvidencePublicationActionType
    issue_key: str
    target_key: str = ""


@dataclass(frozen=True)
class EvidencePublicationResult:
    """Result of evidence publication or dry-run planning."""

    evidence_path: str
    mode: EvidencePublicationMode
    actions: tuple[EvidencePublicationAction, ...]
    failures: tuple[EvidencePublicationFailure, ...] = ()

    @property
    def succeeded(self) -> bool:
        return not self.failures


class EvidencePublisher(Protocol):
    """Transport boundary for live Jira/AgileTest evidence updates."""

    def add_comment(self, plan: EvidenceCommentPlan) -> None:
        """Add a Jira comment."""

    def attach_evidence(self, plan: EvidenceAttachmentPlan) -> None:
        """Attach or re-attach an evidence file."""

    def link_issues(self, plan: EvidenceLinkPlan) -> None:
        """Create a Jira issue link."""


def build_evidence_comment_plan(
    *,
    issue_key: str,
    evidence_path: str,
    result_summary: str,
    details: str = "",
) -> EvidenceCommentPlan:
    """Build a Jira comment plan that references local evidence."""

    issue_key = _require_text("issue_key", issue_key)
    evidence_path = _require_text("evidence_path", evidence_path)
    result_summary = _require_text("result_summary", result_summary)
    body = f"{result_summary}\n\nEvidence file: {evidence_path}"
    if details.strip():
        body = f"{body}\n\n{details.strip()}"
    return EvidenceCommentPlan(issue_key=issue_key, evidence_path=evidence_path, body=body)


def build_evidence_attachment_plan(
    *,
    issue_key: str,
    evidence_path: str,
    filename: str = "",
    replace_existing: bool = True,
) -> EvidenceAttachmentPlan:
    """Build an attachment plan for an evidence file."""

    return EvidenceAttachmentPlan(
        issue_key=_require_text("issue_key", issue_key),
        evidence_path=_require_text("evidence_path", evidence_path),
        filename=_optional_text(filename),
        replace_existing=bool(replace_existing),
    )


def build_agiletest_evidence_link_plans(
    *,
    overview_task_key: str,
    test_execution_key: str,
    test_case_keys: tuple[str, ...],
    link_type: str = "AgileTest",
    outward_relationship: str = "tests",
) -> tuple[EvidenceLinkPlan, ...]:
    """Build links between overview Task, Test execution, and Test Cases."""

    overview_task_key = _require_text("overview_task_key", overview_task_key)
    test_execution_key = _require_text("test_execution_key", test_execution_key)
    link_type = _require_text("link_type", link_type)
    outward_relationship = _optional_text(outward_relationship)
    plans = [
        EvidenceLinkPlan(
            source_issue_key=overview_task_key,
            target_issue_key=test_execution_key,
            link_type=link_type,
            outward_relationship=outward_relationship,
        )
    ]
    for key in test_case_keys:
        plans.append(
            EvidenceLinkPlan(
                source_issue_key=test_execution_key,
                target_issue_key=_require_text("test_case_keys[]", key),
                link_type=link_type,
                outward_relationship=outward_relationship,
            )
        )
    return tuple(plans)


def build_evidence_publication_request(
    *,
    evidence_path: str,
    mode: EvidencePublicationMode = EvidencePublicationMode.DRY_RUN,
    comments: tuple[EvidenceCommentPlan, ...] = (),
    attachments: tuple[EvidenceAttachmentPlan, ...] = (),
    links: tuple[EvidenceLinkPlan, ...] = (),
) -> EvidencePublicationRequest:
    """Build a validated evidence publication request."""

    _require_text("evidence_path", evidence_path)
    if not isinstance(mode, EvidencePublicationMode):
        raise EvidencePublicationError("mode must be EvidencePublicationMode")
    if not (comments or attachments or links):
        raise EvidencePublicationError("at least one publication action is required")
    for comment in comments:
        _validate_comment(comment)
    for attachment in attachments:
        _validate_attachment(attachment)
    for link in links:
        _validate_link(link)
    return EvidencePublicationRequest(
        evidence_path=evidence_path.strip(),
        mode=mode,
        comments=comments,
        attachments=attachments,
        links=links,
    )


def evidence_publication_failure(
    *,
    action_type: EvidencePublicationActionType,
    issue_key: str,
    evidence_path: str,
    message: str,
) -> EvidencePublicationFailure:
    """Build a failure record without losing the local evidence path."""

    if not isinstance(action_type, EvidencePublicationActionType):
        raise EvidencePublicationError("action_type must be EvidencePublicationActionType")
    return EvidencePublicationFailure(
        action_type=action_type,
        issue_key=_require_text("issue_key", issue_key),
        evidence_path=_require_text("evidence_path", evidence_path),
        message=_require_text("message", message),
    )


def execute_evidence_publication_request(
    request: EvidencePublicationRequest,
    *,
    publisher: EvidencePublisher | None = None,
) -> EvidencePublicationResult:
    """Execute or dry-run evidence publication actions."""

    request = build_evidence_publication_request(
        evidence_path=request.evidence_path,
        mode=request.mode,
        comments=request.comments,
        attachments=request.attachments,
        links=request.links,
    )
    if request.mode is EvidencePublicationMode.LIVE and publisher is None:
        raise EvidencePublicationError("publisher is required for live evidence publication")
    actions: list[EvidencePublicationAction] = []
    failures: list[EvidencePublicationFailure] = []
    for comment in request.comments:
        try:
            if request.mode is EvidencePublicationMode.LIVE:
                assert publisher is not None
                publisher.add_comment(comment)
            actions.append(
                EvidencePublicationAction(
                    action_type=EvidencePublicationActionType.COMMENT,
                    issue_key=comment.issue_key,
                )
            )
        except Exception as exc:  # pragma: no cover - exact transport exceptions are integration-owned.
            failures.append(
                evidence_publication_failure(
                    action_type=EvidencePublicationActionType.COMMENT,
                    issue_key=comment.issue_key,
                    evidence_path=comment.evidence_path,
                    message=str(exc),
                )
            )
    for attachment in request.attachments:
        try:
            if request.mode is EvidencePublicationMode.LIVE:
                assert publisher is not None
                publisher.attach_evidence(attachment)
            actions.append(
                EvidencePublicationAction(
                    action_type=EvidencePublicationActionType.ATTACHMENT,
                    issue_key=attachment.issue_key,
                )
            )
        except Exception as exc:
            failures.append(
                evidence_publication_failure(
                    action_type=EvidencePublicationActionType.ATTACHMENT,
                    issue_key=attachment.issue_key,
                    evidence_path=attachment.evidence_path,
                    message=str(exc),
                )
            )
    for link in request.links:
        try:
            if request.mode is EvidencePublicationMode.LIVE:
                assert publisher is not None
                publisher.link_issues(link)
            actions.append(
                EvidencePublicationAction(
                    action_type=EvidencePublicationActionType.LINK,
                    issue_key=link.source_issue_key,
                    target_key=link.target_issue_key,
                )
            )
        except Exception as exc:
            failures.append(
                evidence_publication_failure(
                    action_type=EvidencePublicationActionType.LINK,
                    issue_key=link.source_issue_key,
                    evidence_path=request.evidence_path,
                    message=str(exc),
                )
            )
    return EvidencePublicationResult(
        evidence_path=request.evidence_path,
        mode=request.mode,
        actions=tuple(actions),
        failures=tuple(failures),
    )


def _validate_comment(plan: EvidenceCommentPlan) -> None:
    _require_text("comment.issue_key", plan.issue_key)
    _require_text("comment.evidence_path", plan.evidence_path)
    _require_text("comment.body", plan.body)


def _validate_attachment(plan: EvidenceAttachmentPlan) -> None:
    _require_text("attachment.issue_key", plan.issue_key)
    _require_text("attachment.evidence_path", plan.evidence_path)


def _validate_link(plan: EvidenceLinkPlan) -> None:
    _require_text("link.source_issue_key", plan.source_issue_key)
    _require_text("link.target_issue_key", plan.target_issue_key)
    _require_text("link.link_type", plan.link_type)


def _optional_text(value: object) -> str:
    return str(value or "").strip()


def _require_text(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidencePublicationError(f"{name} is required")
    return value.strip()
