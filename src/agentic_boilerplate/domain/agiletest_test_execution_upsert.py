"""AgileTest Test Execution create-or-update planning."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from agentic_boilerplate.domain.evidence_publication import (
    EvidenceLinkPlan,
    EvidencePublicationMode,
    EvidencePublicationRequest,
    build_evidence_publication_request,
)


DEFAULT_TEST_EXECUTION_PLACEHOLDER_KEY = "NEW-TEST-EXECUTION"


class AgileTestTestExecutionUpsertError(ValueError):
    """Raised when Test Execution upsert input is incomplete or ambiguous."""


class AgileTestTestExecutionOperation(str, Enum):
    """Supported Test Execution upsert operations."""

    CREATE = "create"
    UPDATE = "update"


class AgileTestTestExecutionResolutionSource(str, Enum):
    """How the helper resolved the Test Execution target."""

    NEW_EXECUTION = "new-execution"
    EXISTING_EXECUTION_KEY = "existing-execution-key"
    LOOKUP_MATCH = "lookup-match"


@dataclass(frozen=True)
class AgileTestTestExecutionConfig:
    """Project-specific configuration for Test Execution upsert planning."""

    project_key: str
    issue_type: str = "Test execution"
    labels: tuple[str, ...] = ("agiletest-test-execution",)
    overview_execution_link_type: str = "Relates"
    overview_execution_relationship: str = "relates to"
    execution_test_case_link_type: str = "AgileTest"
    execution_test_case_relationship: str = "tests"
    created_execution_key_placeholder: str = DEFAULT_TEST_EXECUTION_PLACEHOLDER_KEY


@dataclass(frozen=True)
class AgileTestTestExecutionLookupResult:
    """Result of a precomputed lookup for an existing Test Execution."""

    matched_execution_keys: tuple[str, ...] = ()
    lookup_query: str = ""


@dataclass(frozen=True)
class AgileTestTestExecutionIssueFields:
    """Issue fields required to create or update a Test Execution."""

    project_key: str
    issue_type: str
    summary: str
    description: str
    labels: tuple[str, ...]


@dataclass(frozen=True)
class AgileTestTestExecutionUpsertRequest:
    """Inputs used to build a Test Execution create-or-update plan."""

    release_key: str
    sprint_label: str
    regression_overview_key: str
    evidence_path: str
    mode: EvidencePublicationMode = EvidencePublicationMode.DRY_RUN
    test_case_keys: tuple[str, ...] = ()
    existing_execution_key: str = ""
    summary: str = ""
    description: str = ""
    lookup_result: AgileTestTestExecutionLookupResult = field(
        default_factory=AgileTestTestExecutionLookupResult
    )


@dataclass(frozen=True)
class AgileTestTestExecutionUpsertPlan:
    """Reusable create-or-update plan for one Test Execution artifact."""

    operation: AgileTestTestExecutionOperation
    resolution_source: AgileTestTestExecutionResolutionSource
    execution_issue_key: str
    issue_fields: AgileTestTestExecutionIssueFields
    publication_request: EvidencePublicationRequest
    lookup_query: str = ""


@dataclass(frozen=True)
class AgileTestTestExecutionUpsertFailure:
    """Failure that preserves the local evidence path for recovery."""

    operation: AgileTestTestExecutionOperation
    execution_issue_key: str
    evidence_path: str
    message: str


@dataclass(frozen=True)
class AgileTestTestExecutionUpsertResult:
    """Result of executing or dry-running a Test Execution upsert plan."""

    mode: EvidencePublicationMode
    operation: AgileTestTestExecutionOperation
    resolution_source: AgileTestTestExecutionResolutionSource
    execution_issue_key: str
    issue_fields: AgileTestTestExecutionIssueFields
    publication_request: EvidencePublicationRequest
    failures: tuple[AgileTestTestExecutionUpsertFailure, ...] = ()

    @property
    def succeeded(self) -> bool:
        return not self.failures


class AgileTestTestExecutionAdapter(Protocol):
    """Boundary for future live Jira or AgileTest execution updates."""

    def create_test_execution(self, fields: AgileTestTestExecutionIssueFields) -> str:
        """Create a Test Execution and return its issue key."""

    def update_test_execution(
        self,
        issue_key: str,
        fields: AgileTestTestExecutionIssueFields,
    ) -> None:
        """Update an existing Test Execution."""


def build_agiletest_test_execution_upsert_plan(
    *,
    request: AgileTestTestExecutionUpsertRequest,
    config: AgileTestTestExecutionConfig,
) -> AgileTestTestExecutionUpsertPlan:
    """Build a deterministic Test Execution create-or-update plan."""

    _validate_config(config)
    _validate_request(request)
    operation, resolution_source, execution_issue_key = _resolve_execution_target(
        existing_execution_key=request.existing_execution_key,
        lookup_result=request.lookup_result,
        placeholder_key=config.created_execution_key_placeholder,
    )
    issue_fields = AgileTestTestExecutionIssueFields(
        project_key=config.project_key.strip(),
        issue_type=config.issue_type.strip(),
        summary=_summary_for_request(request),
        description=_description_for_request(request),
        labels=_unique_texts("labels", config.labels),
    )
    publication_request = build_evidence_publication_request(
        evidence_path=request.evidence_path.strip(),
        mode=request.mode,
        links=_build_link_plans(
            config=config,
            overview_task_key=request.regression_overview_key,
            execution_issue_key=execution_issue_key,
            test_case_keys=request.test_case_keys,
        ),
    )
    return AgileTestTestExecutionUpsertPlan(
        operation=operation,
        resolution_source=resolution_source,
        execution_issue_key=execution_issue_key,
        issue_fields=issue_fields,
        publication_request=publication_request,
        lookup_query=request.lookup_result.lookup_query.strip(),
    )


def execute_agiletest_test_execution_upsert_plan(
    plan: AgileTestTestExecutionUpsertPlan,
    *,
    adapter: AgileTestTestExecutionAdapter | None = None,
) -> AgileTestTestExecutionUpsertResult:
    """Execute or dry-run a Test Execution upsert plan."""

    _validate_plan(plan)
    if plan.publication_request.mode is EvidencePublicationMode.DRY_RUN:
        return AgileTestTestExecutionUpsertResult(
            mode=plan.publication_request.mode,
            operation=plan.operation,
            resolution_source=plan.resolution_source,
            execution_issue_key=plan.execution_issue_key,
            issue_fields=plan.issue_fields,
            publication_request=plan.publication_request,
        )
    if adapter is None:
        raise AgileTestTestExecutionUpsertError("adapter is required for live Test Execution upsert")

    try:
        execution_issue_key = plan.execution_issue_key
        if plan.operation is AgileTestTestExecutionOperation.CREATE:
            execution_issue_key = _require_text(
                "created_execution_key",
                adapter.create_test_execution(plan.issue_fields),
            )
        else:
            adapter.update_test_execution(plan.execution_issue_key, plan.issue_fields)
        publication_request = build_evidence_publication_request(
            evidence_path=plan.publication_request.evidence_path,
            mode=plan.publication_request.mode,
            comments=plan.publication_request.comments,
            attachments=plan.publication_request.attachments,
            links=_replace_link_source_or_target(
                plan.publication_request.links,
                placeholder_key=plan.execution_issue_key,
                replacement_key=execution_issue_key,
            ),
        )
        return AgileTestTestExecutionUpsertResult(
            mode=plan.publication_request.mode,
            operation=plan.operation,
            resolution_source=plan.resolution_source,
            execution_issue_key=execution_issue_key,
            issue_fields=plan.issue_fields,
            publication_request=publication_request,
        )
    except Exception as exc:  # pragma: no cover - transport-specific errors stay adapter-owned.
        return AgileTestTestExecutionUpsertResult(
            mode=plan.publication_request.mode,
            operation=plan.operation,
            resolution_source=plan.resolution_source,
            execution_issue_key=plan.execution_issue_key,
            issue_fields=plan.issue_fields,
            publication_request=plan.publication_request,
            failures=(
                AgileTestTestExecutionUpsertFailure(
                    operation=plan.operation,
                    execution_issue_key=plan.execution_issue_key,
                    evidence_path=plan.publication_request.evidence_path,
                    message=str(exc),
                ),
            ),
        )


def _resolve_execution_target(
    *,
    existing_execution_key: str,
    lookup_result: AgileTestTestExecutionLookupResult,
    placeholder_key: str,
) -> tuple[
    AgileTestTestExecutionOperation,
    AgileTestTestExecutionResolutionSource,
    str,
]:
    existing_execution_key = existing_execution_key.strip()
    if existing_execution_key:
        return (
            AgileTestTestExecutionOperation.UPDATE,
            AgileTestTestExecutionResolutionSource.EXISTING_EXECUTION_KEY,
            existing_execution_key,
        )

    matches = _unique_texts(
        "lookup_result.matched_execution_keys",
        lookup_result.matched_execution_keys,
    )
    if len(matches) > 1:
        raise AgileTestTestExecutionUpsertError(
            "lookup_result.matched_execution_keys must resolve to at most one Test Execution"
        )
    if matches:
        return (
            AgileTestTestExecutionOperation.UPDATE,
            AgileTestTestExecutionResolutionSource.LOOKUP_MATCH,
            matches[0],
        )

    return (
        AgileTestTestExecutionOperation.CREATE,
        AgileTestTestExecutionResolutionSource.NEW_EXECUTION,
        _require_text("created_execution_key_placeholder", placeholder_key),
    )


def _build_link_plans(
    *,
    config: AgileTestTestExecutionConfig,
    overview_task_key: str,
    execution_issue_key: str,
    test_case_keys: tuple[str, ...],
) -> tuple[EvidenceLinkPlan, ...]:
    plans = [
        EvidenceLinkPlan(
            source_issue_key=_require_text("regression_overview_key", overview_task_key),
            target_issue_key=_require_text("execution_issue_key", execution_issue_key),
            link_type=_require_text(
                "overview_execution_link_type",
                config.overview_execution_link_type,
            ),
            outward_relationship=config.overview_execution_relationship.strip(),
        )
    ]
    for key in _unique_texts("test_case_keys", test_case_keys):
        plans.append(
            EvidenceLinkPlan(
                source_issue_key=execution_issue_key,
                target_issue_key=key,
                link_type=_require_text(
                    "execution_test_case_link_type",
                    config.execution_test_case_link_type,
                ),
                outward_relationship=config.execution_test_case_relationship.strip(),
            )
        )
    return tuple(plans)


def _replace_link_source_or_target(
    links: Sequence[EvidenceLinkPlan],
    *,
    placeholder_key: str,
    replacement_key: str,
) -> tuple[EvidenceLinkPlan, ...]:
    resolved: list[EvidenceLinkPlan] = []
    for link in links:
        source_issue_key = (
            replacement_key
            if link.source_issue_key == placeholder_key
            else link.source_issue_key
        )
        target_issue_key = (
            replacement_key
            if link.target_issue_key == placeholder_key
            else link.target_issue_key
        )
        resolved.append(
            EvidenceLinkPlan(
                source_issue_key=source_issue_key,
                target_issue_key=target_issue_key,
                link_type=link.link_type,
                outward_relationship=link.outward_relationship,
            )
        )
    return tuple(resolved)


def _summary_for_request(request: AgileTestTestExecutionUpsertRequest) -> str:
    if request.summary.strip():
        return request.summary.strip()
    return f"{request.release_key.strip()} {request.sprint_label.strip()} Test Execution"


def _description_for_request(request: AgileTestTestExecutionUpsertRequest) -> str:
    if request.description.strip():
        return request.description.strip()
    lines = [
        f"Release key: {request.release_key.strip()}",
        f"Sprint label: {request.sprint_label.strip()}",
        f"Regression overview: {request.regression_overview_key.strip()}",
        f"Evidence path: {request.evidence_path.strip()}",
    ]
    if request.test_case_keys:
        lines.extend(["", "Included Test Cases:"])
        lines.extend(
            f"- {key}"
            for key in _unique_texts("test_case_keys", request.test_case_keys)
        )
    return "\n".join(lines)


def _validate_config(config: AgileTestTestExecutionConfig) -> None:
    _require_text("project_key", config.project_key)
    _require_text("issue_type", config.issue_type)
    _require_text("overview_execution_link_type", config.overview_execution_link_type)
    _require_text("execution_test_case_link_type", config.execution_test_case_link_type)
    _require_text(
        "created_execution_key_placeholder",
        config.created_execution_key_placeholder,
    )
    if not config.labels:
        raise AgileTestTestExecutionUpsertError("labels is required")
    _unique_texts("labels", config.labels)


def _validate_request(request: AgileTestTestExecutionUpsertRequest) -> None:
    _require_text("release_key", request.release_key)
    _require_text("sprint_label", request.sprint_label)
    _require_text("regression_overview_key", request.regression_overview_key)
    _require_text("evidence_path", request.evidence_path)
    if not isinstance(request.mode, EvidencePublicationMode):
        raise AgileTestTestExecutionUpsertError("mode must be EvidencePublicationMode")
    _unique_texts("test_case_keys", request.test_case_keys)


def _validate_plan(plan: AgileTestTestExecutionUpsertPlan) -> None:
    if not isinstance(plan.operation, AgileTestTestExecutionOperation):
        raise AgileTestTestExecutionUpsertError(
            "operation must be AgileTestTestExecutionOperation"
        )
    if not isinstance(
        plan.resolution_source,
        AgileTestTestExecutionResolutionSource,
    ):
        raise AgileTestTestExecutionUpsertError(
            "resolution_source must be AgileTestTestExecutionResolutionSource"
        )
    _require_text("execution_issue_key", plan.execution_issue_key)
    _require_text("issue_fields.project_key", plan.issue_fields.project_key)
    _require_text("issue_fields.issue_type", plan.issue_fields.issue_type)
    _require_text("issue_fields.summary", plan.issue_fields.summary)
    _require_text("issue_fields.description", plan.issue_fields.description)
    if not plan.issue_fields.labels:
        raise AgileTestTestExecutionUpsertError("issue_fields.labels is required")


def _unique_texts(name: str, values: Sequence[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for index, value in enumerate(values):
        text = _require_text(f"{name}[{index}]", value)
        if text not in seen:
            normalized.append(text)
            seen.add(text)
    return tuple(normalized)


def _require_text(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AgileTestTestExecutionUpsertError(f"{name} is required")
    return value.strip()
