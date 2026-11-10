"""Review record and finding tracker domain model."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from agentic_boilerplate.domain.po_inbox import AgentRole
from agentic_boilerplate.domain.story_complexity import ReasoningLevel


class ReviewScopeMode(str, Enum):
    """Supported review scope modes."""

    DIFF_FIRST = "diff-first"
    EXPANDED_CONTEXT = "expanded-context"


class ReviewFindingKind(str, Enum):
    """Finding categories recorded by the Review Agent."""

    ACCEPTANCE_CRITERIA = "acceptance-criteria"
    ARCHITECTURE = "architecture"
    CODE_QUALITY = "code-quality"
    CONFLICT = "conflict"
    MAINTAINABILITY = "maintainability"
    SECURITY = "security"
    TESTING = "testing"


class ReviewFindingSeverity(str, Enum):
    """Finding severity used for routing review decisions."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    BLOCKING = "blocking"


class ReviewFindingStatus(str, Enum):
    """Lifecycle of a review finding across review cycles."""

    OPEN = "open"
    ADDRESSED = "addressed"
    WONT_FIX = "wont-fix"


class ReviewDecision(str, Enum):
    """Final or latest review decision."""

    PENDING = "pending"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes-requested"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class ReviewScope:
    """Scope metadata explaining what the Review Agent inspected."""

    mode: ReviewScopeMode
    changed_files: tuple[str, ...]
    related_tests: tuple[str, ...] = ()
    touched_contracts: tuple[str, ...] = ()
    expanded_context_paths: tuple[str, ...] = ()
    expansion_reason: str = ""


@dataclass(frozen=True)
class ReviewModelRouting:
    """Model and reasoning metadata used for a review pass."""

    model: str
    reasoning: ReasoningLevel
    speed: str
    rationale: str


@dataclass(frozen=True)
class ReviewFinding:
    """One Review Agent finding or requested correction anchor."""

    id: str
    title: str
    description: str
    kind: ReviewFindingKind
    severity: ReviewFindingSeverity
    status: ReviewFindingStatus = ReviewFindingStatus.OPEN
    file_path: str = ""
    line: int | None = None
    fingerprint: str = ""


@dataclass(frozen=True)
class ReviewRequestedChange:
    """A concrete change request tied to a finding."""

    id: str
    finding_id: str
    request: str
    status: ReviewFindingStatus = ReviewFindingStatus.OPEN


@dataclass(frozen=True)
class DeveloperReviewResponse:
    """Developer response to a requested review change."""

    id: str
    requested_change_id: str
    actor: str
    response: str
    created_at: str


@dataclass(frozen=True)
class ReviewRecord:
    """Durable record for review state across PR review cycles."""

    id: str
    jira_issue_key: str
    pull_request_url: str
    pull_request_number: int
    head_branch: str
    base_branch: str
    head_sha: str
    reviewer: AgentRole
    scope: ReviewScope
    routing: ReviewModelRouting
    final_decision: ReviewDecision
    created_at: str
    updated_at: str
    findings: tuple[ReviewFinding, ...] = ()
    requested_changes: tuple[ReviewRequestedChange, ...] = ()
    developer_responses: tuple[DeveloperReviewResponse, ...] = ()


@dataclass(frozen=True)
class RepeatedReviewFinding:
    """A finding repeated from an earlier review record."""

    finding: ReviewFinding
    previous_record_id: str
    previous_finding_id: str
    fingerprint: str


@dataclass(frozen=True)
class ReviewRecordIssue:
    """Validation issue for review records."""

    field: str
    message: str


class ReviewRecordError(ValueError):
    """Raised when a review record violates the domain contract."""

    def __init__(self, issues: Sequence[ReviewRecordIssue]) -> None:
        self.issues = tuple(issues)
        super().__init__(format_review_record_issues(self.issues))


def validate_review_record(record: ReviewRecord) -> list[ReviewRecordIssue]:
    """Return validation issues for a review record."""

    issues: list[ReviewRecordIssue] = []
    _require_text(issues, "id", record.id)
    _require_text(issues, "jira_issue_key", record.jira_issue_key)
    _require_text(issues, "pull_request_url", record.pull_request_url)
    _require_text(issues, "head_branch", record.head_branch)
    _require_text(issues, "base_branch", record.base_branch)
    _require_text(issues, "head_sha", record.head_sha)
    _require_text(issues, "created_at", record.created_at)
    _require_text(issues, "updated_at", record.updated_at)
    if record.pull_request_number <= 0:
        issues.append(ReviewRecordIssue("pull_request_number", "Pull request number must be positive."))
    issues.extend(_validate_review_scope(record.scope))
    issues.extend(_validate_review_routing(record.routing))
    for index, finding in enumerate(record.findings):
        issues.extend(_validate_finding(finding, f"findings[{index}]"))
    finding_ids = {finding.id for finding in record.findings}
    for index, change in enumerate(record.requested_changes):
        prefix = f"requested_changes[{index}]"
        _require_text(issues, f"{prefix}.id", change.id)
        _require_text(issues, f"{prefix}.finding_id", change.finding_id)
        _require_text(issues, f"{prefix}.request", change.request)
        if change.finding_id and change.finding_id not in finding_ids:
            issues.append(ReviewRecordIssue(f"{prefix}.finding_id", "Requested change must reference a finding."))
    change_ids = {change.id for change in record.requested_changes}
    for index, response in enumerate(record.developer_responses):
        prefix = f"developer_responses[{index}]"
        _require_text(issues, f"{prefix}.id", response.id)
        _require_text(issues, f"{prefix}.requested_change_id", response.requested_change_id)
        _require_text(issues, f"{prefix}.actor", response.actor)
        _require_text(issues, f"{prefix}.response", response.response)
        _require_text(issues, f"{prefix}.created_at", response.created_at)
        if response.requested_change_id and response.requested_change_id not in change_ids:
            issues.append(
                ReviewRecordIssue(
                    f"{prefix}.requested_change_id",
                    "Developer response must reference a requested change.",
                )
            )
    return issues


def require_valid_review_record(record: ReviewRecord) -> ReviewRecord:
    """Raise when a review record violates the domain contract."""

    issues = validate_review_record(record)
    if issues:
        raise ReviewRecordError(issues)
    return record


def review_record_to_dict(record: ReviewRecord) -> dict[str, Any]:
    """Convert a review record into JSON-compatible data."""

    return {
        "id": record.id,
        "jira_issue_key": record.jira_issue_key,
        "pull_request_url": record.pull_request_url,
        "pull_request_number": record.pull_request_number,
        "head_branch": record.head_branch,
        "base_branch": record.base_branch,
        "head_sha": record.head_sha,
        "reviewer": record.reviewer.value,
        "scope": {
            "mode": record.scope.mode.value,
            "changed_files": list(record.scope.changed_files),
            "related_tests": list(record.scope.related_tests),
            "touched_contracts": list(record.scope.touched_contracts),
            "expanded_context_paths": list(record.scope.expanded_context_paths),
            "expansion_reason": record.scope.expansion_reason,
        },
        "routing": {
            "model": record.routing.model,
            "reasoning": record.routing.reasoning.value,
            "speed": record.routing.speed,
            "rationale": record.routing.rationale,
        },
        "final_decision": record.final_decision.value,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "findings": [_finding_to_dict(finding) for finding in record.findings],
        "requested_changes": [_requested_change_to_dict(change) for change in record.requested_changes],
        "developer_responses": [_developer_response_to_dict(response) for response in record.developer_responses],
    }


def review_record_from_dict(data: Mapping[str, Any]) -> ReviewRecord:
    """Build and validate a review record from JSON-compatible data."""

    scope_data = _mapping(data.get("scope"))
    routing_data = _mapping(data.get("routing"))
    record = ReviewRecord(
        id=_text(data.get("id")),
        jira_issue_key=_text(data.get("jira_issue_key")),
        pull_request_url=_text(data.get("pull_request_url")),
        pull_request_number=_int(data.get("pull_request_number")),
        head_branch=_text(data.get("head_branch")),
        base_branch=_text(data.get("base_branch")),
        head_sha=_text(data.get("head_sha")),
        reviewer=_enum(AgentRole, data.get("reviewer", "")),
        scope=ReviewScope(
            mode=_enum(ReviewScopeMode, scope_data.get("mode", "")),
            changed_files=_tuple_text(scope_data.get("changed_files")),
            related_tests=_tuple_text(scope_data.get("related_tests")),
            touched_contracts=_tuple_text(scope_data.get("touched_contracts")),
            expanded_context_paths=_tuple_text(scope_data.get("expanded_context_paths")),
            expansion_reason=_text(scope_data.get("expansion_reason")),
        ),
        routing=ReviewModelRouting(
            model=_text(routing_data.get("model")),
            reasoning=_enum(ReasoningLevel, routing_data.get("reasoning", "")),
            speed=_text(routing_data.get("speed")),
            rationale=_text(routing_data.get("rationale")),
        ),
        final_decision=_enum(ReviewDecision, data.get("final_decision", "")),
        created_at=_text(data.get("created_at")),
        updated_at=_text(data.get("updated_at")),
        findings=tuple(_finding_from_dict(item) for item in _sequence(data.get("findings"))),
        requested_changes=tuple(
            _requested_change_from_dict(item) for item in _sequence(data.get("requested_changes"))
        ),
        developer_responses=tuple(
            _developer_response_from_dict(item) for item in _sequence(data.get("developer_responses"))
        ),
    )
    return require_valid_review_record(record)


def review_finding_fingerprint(finding: ReviewFinding) -> str:
    """Return stable identity for repeated-finding detection."""

    if finding.fingerprint.strip():
        return finding.fingerprint.strip().casefold()
    parts = (
        finding.kind.value,
        finding.file_path.strip(),
        "" if finding.line is None else str(finding.line),
        finding.title.strip(),
    )
    return "|".join(part.casefold() for part in parts)


def find_repeated_review_findings(
    record: ReviewRecord,
    previous_records: Sequence[ReviewRecord],
) -> tuple[RepeatedReviewFinding, ...]:
    """Return findings in record that repeat findings from previous records."""

    previous_by_fingerprint: dict[str, tuple[str, str]] = {}
    for previous_record in previous_records:
        for previous_finding in previous_record.findings:
            if previous_finding.status == ReviewFindingStatus.WONT_FIX:
                continue
            fingerprint = review_finding_fingerprint(previous_finding)
            previous_by_fingerprint.setdefault(fingerprint, (previous_record.id, previous_finding.id))

    repeated: list[RepeatedReviewFinding] = []
    for finding in record.findings:
        fingerprint = review_finding_fingerprint(finding)
        previous = previous_by_fingerprint.get(fingerprint)
        if previous is None:
            continue
        previous_record_id, previous_finding_id = previous
        repeated.append(
            RepeatedReviewFinding(
                finding=finding,
                previous_record_id=previous_record_id,
                previous_finding_id=previous_finding_id,
                fingerprint=fingerprint,
            )
        )
    return tuple(repeated)


def is_conflict_finding(finding: ReviewFinding) -> bool:
    """Return whether the finding represents a merge conflict/change request."""

    return finding.kind == ReviewFindingKind.CONFLICT


def format_review_record_issues(issues: Sequence[ReviewRecordIssue]) -> str:
    """Format review record validation issues."""

    if not issues:
        return "Review record is valid."
    return "; ".join(f"{issue.field}: {issue.message}" for issue in issues)


def _validate_review_scope(scope: ReviewScope) -> list[ReviewRecordIssue]:
    issues: list[ReviewRecordIssue] = []
    if not scope.changed_files:
        issues.append(ReviewRecordIssue("scope.changed_files", "At least one changed file is required."))
    if scope.mode == ReviewScopeMode.EXPANDED_CONTEXT:
        _require_text(issues, "scope.expansion_reason", scope.expansion_reason)
        if not scope.expanded_context_paths:
            issues.append(
                ReviewRecordIssue(
                    "scope.expanded_context_paths",
                    "Expanded context review must list inspected context paths.",
                )
            )
    return issues


def _validate_review_routing(routing: ReviewModelRouting) -> list[ReviewRecordIssue]:
    issues: list[ReviewRecordIssue] = []
    _require_text(issues, "routing.model", routing.model)
    _require_text(issues, "routing.speed", routing.speed)
    _require_text(issues, "routing.rationale", routing.rationale)
    return issues


def _validate_finding(finding: ReviewFinding, prefix: str) -> list[ReviewRecordIssue]:
    issues: list[ReviewRecordIssue] = []
    _require_text(issues, f"{prefix}.id", finding.id)
    _require_text(issues, f"{prefix}.title", finding.title)
    _require_text(issues, f"{prefix}.description", finding.description)
    if finding.line is not None and finding.line <= 0:
        issues.append(ReviewRecordIssue(f"{prefix}.line", "Line number must be positive when provided."))
    return issues


def _finding_to_dict(finding: ReviewFinding) -> dict[str, Any]:
    return {
        "id": finding.id,
        "title": finding.title,
        "description": finding.description,
        "kind": finding.kind.value,
        "severity": finding.severity.value,
        "status": finding.status.value,
        "file_path": finding.file_path,
        "line": finding.line,
        "fingerprint": finding.fingerprint,
    }


def _finding_from_dict(data: Mapping[str, Any]) -> ReviewFinding:
    return ReviewFinding(
        id=_text(data.get("id")),
        title=_text(data.get("title")),
        description=_text(data.get("description")),
        kind=_enum(ReviewFindingKind, data.get("kind", "")),
        severity=_enum(ReviewFindingSeverity, data.get("severity", "")),
        status=_enum(ReviewFindingStatus, data.get("status", ReviewFindingStatus.OPEN.value)),
        file_path=_text(data.get("file_path")),
        line=None if data.get("line") is None else _int(data.get("line")),
        fingerprint=_text(data.get("fingerprint")),
    )


def _requested_change_to_dict(change: ReviewRequestedChange) -> dict[str, Any]:
    return {
        "id": change.id,
        "finding_id": change.finding_id,
        "request": change.request,
        "status": change.status.value,
    }


def _requested_change_from_dict(data: Mapping[str, Any]) -> ReviewRequestedChange:
    return ReviewRequestedChange(
        id=_text(data.get("id")),
        finding_id=_text(data.get("finding_id")),
        request=_text(data.get("request")),
        status=_enum(ReviewFindingStatus, data.get("status", ReviewFindingStatus.OPEN.value)),
    )


def _developer_response_to_dict(response: DeveloperReviewResponse) -> dict[str, Any]:
    return {
        "id": response.id,
        "requested_change_id": response.requested_change_id,
        "actor": response.actor,
        "response": response.response,
        "created_at": response.created_at,
    }


def _developer_response_from_dict(data: Mapping[str, Any]) -> DeveloperReviewResponse:
    return DeveloperReviewResponse(
        id=_text(data.get("id")),
        requested_change_id=_text(data.get("requested_change_id")),
        actor=_text(data.get("actor")),
        response=_text(data.get("response")),
        created_at=_text(data.get("created_at")),
    )


def _require_text(issues: list[ReviewRecordIssue], field: str, value: str) -> None:
    if not value.strip():
        issues.append(ReviewRecordIssue(field, "Value is required."))


def _mapping(value: object) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    raise ReviewRecordError([ReviewRecordIssue("mapping", "Expected object value.")])


def _sequence(value: object) -> Sequence[Mapping[str, Any]]:
    if value is None:
        return ()
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(_mapping(item) for item in value)
    raise ReviewRecordError([ReviewRecordIssue("sequence", "Expected list value.")])


def _tuple_text(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(str(item) for item in value)
    return (str(value),)


def _text(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ReviewRecordError([ReviewRecordIssue("int", "Expected integer value.")]) from exc


def _enum(enum_type: type[Enum], value: object) -> Any:
    try:
        return enum_type(str(value))
    except ValueError as exc:
        raise ReviewRecordError(
            [ReviewRecordIssue(enum_type.__name__, f"Unsupported value {str(value)!r}.")]
        ) from exc
